"""Database-backed user store.

Provides read-only user lookups for the app authentication layer.
"""

from __future__ import annotations

from typing import Any

from app.admin.models import User
from app.database import SessionLocal


def _user_to_dict(user: User) -> dict[str, Any]:
    """Convert User ORM object to the dict format expected by auth deps."""
    perms = user.permissions
    permissions = {
        "can_use_gemini": perms.can_use_gemini if perms else True,
        "can_use_whisper": perms.can_use_whisper if perms else True,
        "max_video_size_gb": perms.max_video_size_gb if perms else 6.0,
        "can_export_docx": perms.can_export_docx if perms else True,
        "can_export_md": perms.can_export_md if perms else False,
        "can_export_html": perms.can_export_html if perms else False,
        "can_export_pdf": perms.can_export_pdf if perms else False,
        "allowed_templates": perms.allowed_templates if perms else None,
    }
    return {
        "id": user.id,
        "clerk_id": user.clerk_id,
        "email": user.email,
        "role": user.role,
        "plan": user.plan,
        "credits_balance": user.credit_account.credits_balance if user.credit_account else 0,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "deleted_at": user.deleted_at,
        "status": user.status,
        "permissions": permissions,
    }


def get_user_by_email(email: str) -> dict[str, Any] | None:
    """Return user dict or None."""
    if not email:
        return None
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email.strip().lower()).first()
        if user:
            return _user_to_dict(user)
    return None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    """Return user dict or None."""
    if not user_id:
        return None
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user:
            return _user_to_dict(user)
    return None


def get_user_by_clerk_id(clerk_id: str) -> dict[str, Any] | None:
    """Return user dict by clerk_id (e.g. 'user_2x...') or None.

    This is used as a fallback when ``get_user_by_id`` fails — for example
    when the Clerk sync step returned None but the user already exists in
    the database with the given clerk_id.
    """
    if not clerk_id:
        return None
    with SessionLocal() as db:
        user = db.query(User).filter(User.clerk_id == clerk_id).first()
        if user:
            return _user_to_dict(user)
    return None
