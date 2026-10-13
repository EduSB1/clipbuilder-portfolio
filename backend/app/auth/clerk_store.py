"""Clerk → local DB user sync (upsert).

This module is used by:
- optional on-demand provisioning (when enabled via env)
- Clerk webhooks (user.created/user.updated/user.deleted)
- maintenance scripts (scripts/sync_users.py)

Security note:
By default, the app requires users to already exist in the local DB.
On-demand provisioning must be explicitly enabled.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.admin import crud
from app.admin.models import User, UserPermission
from app.auth import clerk_client
from app.auth.store import _user_to_dict  # internal helper used across auth layer

logger = logging.getLogger("clipbuilder")


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _extract_primary_email(clerk_user: dict[str, Any]) -> str:
    emails = clerk_user.get("email_addresses") or []
    if not isinstance(emails, list):
        return ""

    primary_id = clerk_user.get("primary_email_address_id")
    if primary_id:
        for e in emails:
            if e.get("id") == primary_id and e.get("email_address"):
                return str(e.get("email_address"))

    if emails and isinstance(emails[0], dict):
        return str(emails[0].get("email_address") or "")

    return ""


def _extract_full_name(clerk_user: dict[str, Any]) -> str:
    first = (clerk_user.get("first_name") or "").strip()
    last = (clerk_user.get("last_name") or "").strip()
    return f"{first} {last}".strip()


def _ensure_permissions(db: Session, user: User) -> None:
    if user.permissions is not None:
        return

    perms = UserPermission(
        user_id=user.id,
        can_use_gemini=True,
        can_use_whisper=True,
        max_video_size_gb=6.0,
    )
    db.add(perms)


def upsert_user(
    db: Session,
    *,
    clerk_id: str,
    email: str,
    full_name: str = "",
) -> User | None:
    """Upsert a user by clerk_id (preferred) or email.

    Returns the User on success.
    Returns None when the user exists but is soft-deleted (do not auto-restore).
    """

    clerk_id = (clerk_id or "").strip()
    email_n = _normalize_email(email)
    if not clerk_id and not email_n:
        return None

    user: User | None = None

    if clerk_id:
        user = db.query(User).filter(User.clerk_id == clerk_id).first()

    if user is None and email_n:
        user = db.query(User).filter(User.email == email_n).first()

    # Existing user
    if user is not None:
        if user.deleted_at is not None:
            logger.warning("clerk_store: refusing to auto-restore soft-deleted user %s", user.id)
            return None

        from app.core.config import settings

        changed = False
        if clerk_id and not user.clerk_id:
            user.clerk_id = clerk_id
            changed = True

        # Keep email in sync when possible. If it conflicts with another user,
        # let the DB constraint raise and surface in logs.
        if email_n and user.email != email_n:
            user.email = email_n
            changed = True

        if full_name is not None and user.full_name != (full_name or ""):
            user.full_name = full_name or ""
            changed = True

        # Auto-activate the admin account if it is currently inactive.
        # This handles the case where admin_email was configured after the
        # user record was already created with is_active=False.
        if not user.is_active and email_n == settings.admin_email.strip().lower():
            user.is_active = True
            user.role = "admin"
            changed = True
            logger.info("clerk_store: auto-activated admin account %s", email_n)

        if changed:
            user.updated_at = datetime.now(UTC)

        _ensure_permissions(db, user)
        db.commit()
        db.refresh(user)
        return user

    from app.core.config import settings

    # New user
    is_admin = email_n == settings.admin_email.lower()
    user = crud.create_user(
        db,
        email=email_n,
        full_name=full_name or "",
        clerk_id=clerk_id or None,
        role="admin" if is_admin else "user",
    )
    return user


def sync_user_from_clerk_payload(clerk_user: dict[str, Any]) -> dict[str, Any] | None:
    """Sync a local user from a Clerk *user* payload (webhook 'data')."""

    from app.database import SessionLocal

    clerk_id = (clerk_user.get("id") or "").strip()
    email = _extract_primary_email(clerk_user)
    full_name = _extract_full_name(clerk_user)

    if not clerk_id:
        return None

    # Some Clerk configurations may deliver user payloads without email_addresses.
    # In that case, fallback to a direct API fetch.
    if not email:
        fetched = clerk_client.get_clerk_user(clerk_id)
        if fetched:
            email = _extract_primary_email(fetched)
            if not full_name:
                full_name = _extract_full_name(fetched)

    if not email:
        logger.warning("clerk_store: cannot sync clerk_id=%s (missing email)", clerk_id[:16])
        return None

    with SessionLocal() as db:
        user = upsert_user(db, clerk_id=clerk_id, email=email, full_name=full_name)
        if not user:
            return None
        return _user_to_dict(user)


def get_or_sync_user_from_clerk(
    clerk_id: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fetch user details from Clerk and upsert into local DB.

    Args:
        clerk_id: Clerk user id (e.g. 'user_...').
        fallback: Optional dict with keys {email, full_name} used when Clerk API
                  isn't reachable or doesn't return required fields.

    Returns:
        Local user dict (auth format) or None.
    """

    clerk_id = (clerk_id or "").strip()
    if not clerk_id:
        return None

    clerk_user = clerk_client.get_clerk_user(clerk_id)

    email = ""
    full_name = ""

    if clerk_user:
        email = _extract_primary_email(clerk_user)
        full_name = _extract_full_name(clerk_user)

    if not email and fallback:
        email = str(fallback.get("email") or "")
        full_name = str(fallback.get("full_name") or "")

    if not email:
        logger.warning("clerk_store: cannot provision clerk_id=%s (missing email)", clerk_id[:16])
        return None

    from app.database import SessionLocal

    with SessionLocal() as db:
        user = upsert_user(db, clerk_id=clerk_id, email=email, full_name=full_name)
        if not user:
            return None
        return _user_to_dict(user)


def soft_delete_user_by_clerk_id(clerk_id: str) -> bool:
    """Soft-delete a local user given a Clerk user id."""

    from app.database import SessionLocal

    clerk_id = (clerk_id or "").strip()
    if not clerk_id:
        return False

    with SessionLocal() as db:
        user = db.query(User).filter(User.clerk_id == clerk_id).first()
        if not user:
            return False
        if user.deleted_at is None:
            user.deleted_at = datetime.now(UTC)
        user.is_active = False
        user.updated_at = datetime.now(UTC)
        db.commit()
        return True
