"""Template service – CRUD operations for document templates.

Handles seeding of built-in templates, listing, creating, and deleting
templates from the database.  Also provides helpers for checking user
template permissions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import DocumentTemplateDef, UserPermission
from app.database import SessionLocal

logger = logging.getLogger("clipbuilder")


# ── Seeding ──────────────────────────────────────────────────────────────


def seed_builtin_templates() -> None:
    """Insert built-in templates into the DB if they don't already exist.

    Reads from template_registry.py (the source of truth for built-in
    template definitions) and upserts into the document_templates table.
    """
    from templates.template_registry import list_templates as list_registry_templates

    registry_templates = list_registry_templates()
    with SessionLocal() as db:
        for t in registry_templates:
            existing = db.get(DocumentTemplateDef, t["id"])
            if existing:
                # Update metadata for built-in templates (in case template_registry changed)
                existing.name = t["name"]
                existing.short_name = t.get("short_name", "")
                existing.description = t.get("description", "")
                existing.icon = t.get("icon", "📄")
                existing.category = t.get("category", "general")
                existing.has_logo = t.get("has_logo", False)
                existing.header_fields = json.dumps(t.get("header_fields", []))
                existing.sections = json.dumps(t.get("sections", []))
                existing.footer_fields = json.dumps(t.get("footer_fields", []))
                existing.is_builtin = True
            else:
                row = DocumentTemplateDef(
                    id=t["id"],
                    name=t["name"],
                    short_name=t.get("short_name", ""),
                    description=t.get("description", ""),
                    icon=t.get("icon", "📄"),
                    category=t.get("category", "general"),
                    has_logo=t.get("has_logo", False),
                    header_fields=json.dumps(t.get("header_fields", [])),
                    sections=json.dumps(t.get("sections", [])),
                    footer_fields=json.dumps(t.get("footer_fields", [])),
                    config="{}",
                    is_builtin=True,
                    is_active=True,
                )
                db.add(row)
        db.commit()
        logger.info("Seeded %d built-in templates", len(registry_templates))


# ── Listing ──────────────────────────────────────────────────────────────


def list_all_templates(db: Session) -> list[dict[str, Any]]:
    """Return all active templates as dicts."""
    rows = db.scalars(
        select(DocumentTemplateDef)
        .where(DocumentTemplateDef.is_active == True)  # noqa: E712
        .order_by(DocumentTemplateDef.is_builtin.desc(), DocumentTemplateDef.name)
    ).all()
    return [_row_to_dict(r) for r in rows]


def list_templates_for_user(
    db: Session, user: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return templates filtered by user permissions.

    - Admins see all active templates.
    - Users see only allowed templates.
    """
    all_templates = list_all_templates(db)

    if user.get("role") == "admin":
        return all_templates

    perms = user.get("permissions", {})
    allowed_raw = perms.get("allowed_templates")

    if not allowed_raw:
        return []

    try:
        allowed_ids = json.loads(allowed_raw) if isinstance(allowed_raw, str) else allowed_raw
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse allowed_templates for user: %s", allowed_raw)
        return []

    if not isinstance(allowed_ids, list):
        return []

    return [t for t in all_templates if t["id"] in allowed_ids]


def check_template_permission(
    user: dict[str, Any], template_id: str | None
) -> None:
    """Raise HTTPException(403) if the user is not allowed to use this template.

    Skips check for admins and when template_permissions_enabled is False.
    """
    from fastapi import HTTPException

    if not template_id:
        return  # No template specified, allow

    if user.get("role") == "admin":
        return  # Admins bypass

    perms = user.get("permissions", {})
    if not perms.get("template_permissions_enabled", False):
        return  # Restrictions not enabled for this user

    allowed_raw = perms.get("allowed_templates")
    if not allowed_raw:
        raise HTTPException(
            status_code=403,
            detail=f"Você não tem permissão para usar o template '{template_id}'. "
            "Entre em contato com o administrador.",
        )

    try:
        allowed_ids = json.loads(allowed_raw) if isinstance(allowed_raw, str) else allowed_raw
    except (json.JSONDecodeError, TypeError):
        allowed_ids = []

    if not isinstance(allowed_ids, list) or template_id not in allowed_ids:
        raise HTTPException(
            status_code=403,
            detail=f"Você não tem permissão para usar o template '{template_id}'. "
            "Entre em contato com o administrador.",
        )


# ── Admin CRUD ───────────────────────────────────────────────────────────


def create_template(db: Session, data: dict[str, Any]) -> DocumentTemplateDef:
    """Create a new custom template."""
    template_id = data.get("id", "").strip()
    if not template_id:
        import uuid
        template_id = f"custom_{uuid.uuid4().hex[:8]}"

    existing = db.get(DocumentTemplateDef, template_id)
    if existing:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Template com ID '{template_id}' já existe.",
        )

    row = DocumentTemplateDef(
        id=template_id,
        name=data.get("name", "Novo Template"),
        short_name=data.get("short_name", ""),
        description=data.get("description", ""),
        icon=data.get("icon", "📄"),
        category=data.get("category", "custom"),
        has_logo=data.get("has_logo", False),
        logo_path=data.get("logo_b64") or data.get("logo_path"),
        header_fields=json.dumps(data.get("header_fields", [])),
        sections=json.dumps(data.get("sections", [])),
        footer_fields=json.dumps(data.get("footer_fields", [])),
        config=json.dumps(data.get("config", {})),
        is_builtin=False,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_template(db: Session, template_id: str) -> None:
    """Soft-delete a template (set is_active=False). Built-in templates cannot be deleted."""
    from fastapi import HTTPException

    row = db.get(DocumentTemplateDef, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    if row.is_builtin:
        raise HTTPException(
            status_code=400,
            detail="Templates nativos não podem ser excluídos.",
        )
    row.is_active = False
    db.commit()


def get_template_with_user_count(db: Session) -> list[dict[str, Any]]:
    """Return all templates with count of users that have access."""
    templates = list_all_templates(db)

    # Get all user permissions to count access
    all_perms = db.scalars(
        select(UserPermission)
    ).all()

    for t in templates:
        t["user_count_restricted"] = 0
        t["user_count_allowed"] = 0
        for perm in all_perms:
            t["user_count_restricted"] += 1
            try:
                allowed = json.loads(perm.allowed_templates) if perm.allowed_templates else []
            except (json.JSONDecodeError, TypeError):
                allowed = []
            if t["id"] in allowed:
                t["user_count_allowed"] += 1

    return templates


# ── Helpers ──────────────────────────────────────────────────────────────


def _row_to_dict(row: DocumentTemplateDef) -> dict[str, Any]:
    """Convert a DB row to the API-compatible dict format."""
    try:
        header_fields = json.loads(row.header_fields) if row.header_fields else []
    except (json.JSONDecodeError, TypeError):
        header_fields = []

    try:
        sections = json.loads(row.sections) if row.sections else []
    except (json.JSONDecodeError, TypeError):
        sections = []

    try:
        footer_fields = json.loads(row.footer_fields) if row.footer_fields else []
    except (json.JSONDecodeError, TypeError):
        footer_fields = []

    return {
        "id": row.id,
        "name": row.name,
        "short_name": row.short_name,
        "description": row.description,
        "icon": row.icon,
        "category": row.category,
        "has_logo": row.has_logo,
        "logo_path": row.logo_path,
        "header_fields": header_fields,
        "sections": sections,
        "footer_fields": footer_fields,
        "is_builtin": row.is_builtin,
        "is_active": row.is_active,
    }
