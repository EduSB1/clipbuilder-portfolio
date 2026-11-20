"""First admin account of a new installation.

On a fresh database nobody can sign in: Clerk sign-ups arrive inactive and
only an admin can approve them. At startup, if no active admin exists, the
account named by ADMIN_EMAIL is created (or promoted and activated), with
ADMIN_PASSWORD as its local password for the emergency login.

Once any active admin exists this does nothing, so demoting or deactivating
someone in the admin panel is never undone by a restart. Further admins are
made in the panel or with ``python scripts/admin.py``.
"""

from __future__ import annotations

import logging

import bcrypt
from sqlalchemy.orm import Session

from app.admin.models import User

logger = logging.getLogger("clipbuilder")

# Local passwords are the only factor of the emergency login (/sys/token).
MIN_ADMIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def password_is_acceptable(password: str) -> bool:
    return len(password or "") >= MIN_ADMIN_PASSWORD_LENGTH


def make_admin(db: Session, email: str, password: str | None = None) -> User:
    """Create *email* as an active admin, or promote and activate the existing account.

    The local password is set only when given, and never replaces an
    existing one silently: changing it is an explicit operation.
    """
    from app.admin.crud import create_user, get_user_by_email

    email = (email or "").strip().lower()
    user = get_user_by_email(db, email)
    if user is None:
        user = create_user(db, email=email, full_name="Admin", role="admin")
    if user.deleted_at is not None:
        raise ValueError(f"A conta {email} foi removida; restaure-a no painel antes.")
    user.role = "admin"
    user.is_active = True
    if password and not user.password_hash:
        user.password_hash = hash_password(password)
    db.commit()
    db.refresh(user)
    return user


def bootstrap_admin(db: Session, email: str, password: str) -> str:
    """Make sure a new installation has one admin. Returns what happened, for the log."""
    has_admin = (
        db.query(User)
        .filter(User.role == "admin", User.is_active.is_(True), User.deleted_at.is_(None))
        .first()
    )
    if has_admin:
        return "skipped: an active admin already exists"

    email = (email or "").strip().lower()
    if not email:
        logger.error("bootstrap_admin: ADMIN_EMAIL is not set; nobody will be able to sign in")
        return "skipped: ADMIN_EMAIL is empty"

    usable_password = password if password_is_acceptable(password) else None
    if usable_password is None:
        logger.error(
            "bootstrap_admin: ADMIN_PASSWORD has fewer than %d characters; "
            "the admin was created without a local password (emergency login disabled for it)",
            MIN_ADMIN_PASSWORD_LENGTH,
        )
    make_admin(db, email, usable_password)
    return f"created admin {email}"
