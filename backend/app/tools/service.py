"""CRUD service for AI tools — listing, creation, update, deletion, toggle, logs, and seeding."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.admin.models import AiTool, AiToolLog
from app.tools.native_tools import NATIVE_TOOLS

logger = logging.getLogger("clipbuilder")


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── List / Get ─────────────────────────────────────────────────────────


def list_tools(
    db: Session,
    scope: str = "global",
    project_id: str | None = None,
) -> list[AiTool]:
    """Return all tools, optionally filtered by scope and project_id.

    When scope is "global", returns all global tools.
    When scope is "project" and project_id is given, returns global + project-specific tools.
    """
    query = db.query(AiTool)

    if scope == "project" and project_id:
        # Return both global tools and tools scoped to this specific project
        query = query.filter(
            (AiTool.scope == "global")
            | ((AiTool.scope == "project") & (AiTool.project_id == project_id))
        )
    else:
        query = query.filter(AiTool.scope == "global")

    return query.order_by(desc(AiTool.is_active), AiTool.name).all()


def get_tool(db: Session, tool_id: str) -> AiTool | None:
    """Return a single tool by ID or None."""
    return db.get(AiTool, tool_id)


def get_tools_by_trigger(
    db: Session,
    trigger: str,
    project_id: str | None = None,
) -> list[AiTool]:
    """Return all active tools whose triggers JSON array contains *trigger*.

    Since triggers are stored as a JSON string array (e.g. '["on_frame_capture"]'),
    we use a LIKE query which works for SQLite and Postgres.
    """
    pattern = f'%"{trigger}"%'
    query = (
        db.query(AiTool)
        .filter(AiTool.is_active == True)  # noqa: E712
        .filter(AiTool.triggers.like(pattern))
    )

    if project_id:
        query = query.filter(
            (AiTool.scope == "global")
            | ((AiTool.scope == "project") & (AiTool.project_id == project_id))
        )
    else:
        query = query.filter(AiTool.scope == "global")

    return query.order_by(AiTool.name).all()


# ── Create / Update / Delete ───────────────────────────────────────────


def create_tool(db: Session, data, created_by: str | None = None) -> AiTool:
    """Create a new AI tool from a Pydantic AiToolCreate schema."""
    tool = AiTool(
        name=data.name,
        description=data.description,
        prompt=data.prompt,
        model_provider=data.model_provider,
        model_name=data.model_name,
        triggers=json.dumps(data.triggers),
        is_active=data.is_active,
        is_native=False,
        scope=data.scope,
        project_id=data.project_id if data.scope == "project" else None,
        output_target=data.output_target,
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    logger.info("AI tool created: %s (id=%s, by=%s)", tool.name, tool.id, created_by)
    return tool


def update_tool(db: Session, tool_id: str, data) -> AiTool | None:
    """Update an existing AI tool. Returns None if not found."""
    tool = db.get(AiTool, tool_id)
    if not tool:
        return None

    update_fields = (
        data.model_dump(exclude_unset=True)
        if hasattr(data, "model_dump")
        else data.dict(exclude_unset=True)
    )

    for field, value in update_fields.items():
        if value is None and field != "project_id":
            continue
        if field == "triggers":
            setattr(tool, field, json.dumps(value))
        else:
            setattr(tool, field, value)

    tool.updated_at = _utcnow()
    db.commit()
    db.refresh(tool)
    logger.info("AI tool updated: %s (id=%s)", tool.name, tool.id)
    return tool


def delete_tool(db: Session, tool_id: str) -> bool:
    """Delete a tool. Returns False if not found or if the tool is native (protected)."""
    tool = db.get(AiTool, tool_id)
    if not tool:
        return False
    if tool.is_native:
        return False

    db.delete(tool)
    db.commit()
    logger.info("AI tool deleted: %s (id=%s)", tool.name, tool_id)
    return True


def toggle_tool(db: Session, tool_id: str, is_active: bool) -> AiTool | None:
    """Toggle a tool on or off. Returns None if not found."""
    tool = db.get(AiTool, tool_id)
    if not tool:
        return None

    tool.is_active = is_active
    tool.updated_at = _utcnow()
    db.commit()
    db.refresh(tool)
    logger.info(
        "AI tool toggled: %s (id=%s, is_active=%s)", tool.name, tool.id, is_active
    )
    return tool


# ── Logs ───────────────────────────────────────────────────────────────


def save_tool_log(
    db: Session,
    tool_id: str,
    trigger: str,
    status: str,
    input_summary: str | None = None,
    output: str | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
) -> AiToolLog:
    """Save an execution log entry for a tool."""
    log = AiToolLog(
        tool_id=tool_id,
        trigger=trigger,
        status=status,
        input_summary=input_summary,
        output=output[:5000] if output and len(output) > 5000 else output,
        error_message=error[:2000] if error and len(error) > 2000 else error,
        duration_ms=duration_ms,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_tool_logs(
    db: Session,
    tool_id: str,
    limit: int = 50,
) -> list[AiToolLog]:
    """Return recent execution logs for a tool, most recent first."""
    return (
        db.query(AiToolLog)
        .filter(AiToolLog.tool_id == tool_id)
        .order_by(desc(AiToolLog.created_at))
        .limit(min(limit, 200))
        .all()
    )


# ── Seed native tools ─────────────────────────────────────────────────


def seed_native_tools(db: Session) -> None:
    """Insert the native (built-in) tools if they don't already exist.

    Matching is done by name + is_native=True so we don't create duplicates.
    Existing native tools are left untouched (admin may have customized them).
    """
    existing_names = {
        t.name
        for t in db.query(AiTool.name).filter(AiTool.is_native == True).all()  # noqa: E712
    }

    created = 0
    for tdef in NATIVE_TOOLS:
        if tdef["name"] in existing_names:
            continue

        tool = AiTool(
            name=tdef["name"],
            description=tdef["description"],
            prompt=tdef["prompt"],
            model_provider=tdef["model_provider"],
            model_name=tdef["model_name"],
            triggers=json.dumps(tdef["triggers"]),
            is_active=tdef.get("is_active", True),
            is_native=True,
            scope=tdef.get("scope", "global"),
            project_id=None,
            output_target=tdef.get("output_target", "description"),
        )
        db.add(tool)
        created += 1

    if created:
        db.commit()
        logger.info("Seeded %d native AI tool(s)", created)
    else:
        logger.debug("All native AI tools already present")
