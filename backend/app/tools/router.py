"""FastAPI router for AI Tools & Agents — CRUD, toggle, logs, and manual execution."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.admin.dependencies import RequireAdmin
from app.auth.deps import CurrentAuthorizedUser
from app.database import get_db
from app.tools.engine import tools_engine
from app.tools.models import (
    AiToolCreate,
    AiToolListResponse,
    AiToolLogListResponse,
    AiToolLogResponse,
    AiToolResponse,
    AiToolToggle,
    AiToolUpdate,
    ToolRunRequest,
    ToolRunResponse,
    ToolRunResult,
)
from app.tools.service import (
    create_tool,
    delete_tool,
    get_tool,
    get_tool_logs,
    list_tools,
    toggle_tool,
    update_tool,
)

logger = logging.getLogger("clipbuilder")

router = APIRouter(prefix="/api/tools", tags=["tools"])


# ── Helpers ────────────────────────────────────────────────────────────


def _tool_to_response(tool) -> AiToolResponse:
    """Convert an AiTool ORM object to a Pydantic response, parsing triggers JSON."""
    triggers_raw = tool.triggers
    if isinstance(triggers_raw, str):
        try:
            triggers = json.loads(triggers_raw)
        except (json.JSONDecodeError, TypeError):
            triggers = [triggers_raw]
    elif isinstance(triggers_raw, list):
        triggers = triggers_raw
    else:
        triggers = []

    return AiToolResponse(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        prompt=tool.prompt,
        model_provider=tool.model_provider,
        model_name=tool.model_name,
        triggers=triggers,
        is_active=tool.is_active,
        is_native=tool.is_native,
        scope=tool.scope,
        project_id=tool.project_id,
        output_target=tool.output_target,
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )


def _get_gemini_key(header: str | None) -> str | None:
    """Resolve the Gemini API key: header -> env. Returns None if unavailable."""
    from app.core.config import settings

    if header and header.strip():
        return header.strip()

    if settings.gemini_api_key:
        return settings.gemini_api_key

    return None





# ── List all tools ─────────────────────────────────────────────────────


@router.get("", response_model=AiToolListResponse)
def list_all_tools(
    _user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
    scope: str = Query(default="global", pattern="^(global|project)$"),
    project_id: str | None = Query(default=None),
):
    """List all AI tools. Authenticated users can read; filtered by scope."""
    tools = list_tools(db, scope=scope, project_id=project_id)
    return AiToolListResponse(
        tools=[_tool_to_response(t) for t in tools],
        total=len(tools),
    )


# ── Get single tool ───────────────────────────────────────────────────


@router.get("/{tool_id}", response_model=AiToolResponse)
def get_single_tool(
    tool_id: str,
    _user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
):
    """Get details of a single AI tool."""
    tool = get_tool(db, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool não encontrada")
    return _tool_to_response(tool)


# ── Create tool (admin only) ──────────────────────────────────────────


@router.post("", response_model=AiToolResponse, status_code=201)
def create_new_tool(
    body: AiToolCreate,
    admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    """Create a new AI tool. Admin only."""
    tool = create_tool(db, body, created_by=admin.id)
    return _tool_to_response(tool)


# ── Update tool (admin only) ──────────────────────────────────────────


@router.patch("/{tool_id}", response_model=AiToolResponse)
def update_existing_tool(
    tool_id: str,
    body: AiToolUpdate,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    """Update an existing AI tool. Admin only."""
    tool = update_tool(db, tool_id, body)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool não encontrada")
    return _tool_to_response(tool)


# ── Delete tool (admin only, fails for native tools) ──────────────────


@router.delete("/{tool_id}")
def delete_existing_tool(
    tool_id: str,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    """Delete an AI tool. Fails if the tool is native (is_native=True). Admin only."""
    existing = get_tool(db, tool_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Tool não encontrada")
    if existing.is_native:
        raise HTTPException(
            status_code=403,
            detail="Tools nativas não podem ser excluídas. Você pode desativá-la.",
        )
    ok = delete_tool(db, tool_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao excluir tool")
    return {"detail": "Tool excluída com sucesso"}


# ── Toggle tool on/off ─────────────────────────────────────────────────


@router.patch("/{tool_id}/toggle", response_model=AiToolResponse)
def toggle_existing_tool(
    tool_id: str,
    body: AiToolToggle,
    _user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
):
    """Toggle a tool active/inactive. Any authenticated user can toggle."""
    tool = toggle_tool(db, tool_id, body.is_active)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool não encontrada")
    return _tool_to_response(tool)


# ── Get tool logs ──────────────────────────────────────────────────────


@router.get("/{tool_id}/logs", response_model=AiToolLogListResponse)
def get_logs_for_tool(
    tool_id: str,
    _user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get execution logs for a specific tool."""
    existing = get_tool(db, tool_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Tool não encontrada")

    logs = get_tool_logs(db, tool_id, limit=limit)
    return AiToolLogListResponse(
        logs=[
            AiToolLogResponse(
                id=log.id,
                tool_id=log.tool_id,
                trigger=log.trigger,
                status=log.status,
                input_summary=log.input_summary,
                output=log.output,
                error_message=log.error_message,
                duration_ms=log.duration_ms,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=len(logs),
    )


# ── Run tools manually for a trigger ──────────────────────────────────


@router.post("/run/{trigger}", response_model=ToolRunResponse)
async def run_tools_manually(
    trigger: str,
    body: ToolRunRequest,
    _user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
):
    """Manually execute all active tools for the given trigger.

    Supported triggers: on_frame_capture, on_export, on_video_upload, manual.
    """
    valid_triggers = {"on_frame_capture", "on_export", "on_video_upload", "manual"}
    if trigger not in valid_triggers:
        raise HTTPException(
            status_code=400,
            detail=f"Trigger inválido: '{trigger}'. Use um de: {', '.join(sorted(valid_triggers))}",
        )

    gemini_key = _get_gemini_key(x_gemini_key)

    if not gemini_key:
        raise HTTPException(
            status_code=401,
            detail="Nenhuma chave de API configurada (Gemini).",
        )

    # Build context
    import base64

    context: dict[str, Any] = {
        "project_id": body.project_id,
        "previous_steps": body.previous_steps or [],
        "full_document": body.full_document or "",
    }

    if body.image_base64:
        try:
            context["image_bytes"] = base64.b64decode(body.image_base64)
        except Exception:
            raise HTTPException(
                status_code=400, detail="image_base64 inválido"
            ) from None

    results = await tools_engine.run_tools_for_trigger(
        trigger=trigger,
        context=context,
        gemini_key=gemini_key,
        db=db,
    )

    return ToolRunResponse(
        results=[
            ToolRunResult(
                tool_id=tool_id,
                tool_name=info.get("tool_name", ""),
                output_target=info.get("output_target", "log_only"),
                output=info.get("output"),
                error=info.get("error"),
                status=info.get("status", "error"),
                duration_ms=info.get("duration_ms"),
            )
            for tool_id, info in results.items()
        ]
    )
