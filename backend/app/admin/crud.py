"""CRUD operations for user management, permissions, and usage logs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.models import ApiUsageLog, User, UserPermission
from app.core.constants import (
    BUSINESS_PLAN_MAX_VIDEO_SIZE_GB,
    DEFAULT_USAGE_LOG_LIMIT,
    DEFAULT_USER_PAGE_SIZE,
    FREE_PLAN_MAX_VIDEO_SIZE_GB,
    PRO_PLAN_MAX_VIDEO_SIZE_GB,
    STARTER_PLAN_MAX_VIDEO_SIZE_GB,
)

# ── Users ─────────────────────────────────────────────────────────────


def get_users(
    db: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_USER_PAGE_SIZE,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    status: str | None = None,
) -> tuple[list[User], int]:
    """Return paginated user list and total count.

    status filter values:
        'ativos'      – is_active=True AND deleted_at IS NULL
        'desativados' – is_active=False AND deleted_at IS NULL
        'excluidos'   – deleted_at IS NOT NULL
        'todos'       – no filter at all
        None          – default: exclude soft-deleted (deleted_at IS NULL)
    """
    q = select(User)

    # ── Status filter (takes precedence over legacy is_active param) ──
    if status == "ativos":
        q = q.where(User.is_active == True, User.deleted_at.is_(None))  # noqa: E712
    elif status == "desativados":
        q = q.where(User.is_active == False, User.deleted_at.is_(None))  # noqa: E712
    elif status == "excluidos":
        q = q.where(User.deleted_at.isnot(None))
    elif status == "todos":
        pass  # no filter
    else:
        # Default behaviour: exclude soft-deleted, honour legacy is_active
        q = q.where(User.deleted_at.is_(None))
        if is_active is not None:
            q = q.where(User.is_active == is_active)

    if search:
        like = f"%{search}%"
        q = q.where(User.email.ilike(like) | User.full_name.ilike(like))
    if role:
        q = q.where(User.role == role)

    total = db.scalar(select(func.count()).select_from(q.subquery()))

    q = q.order_by(User.created_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)

    users = list(db.scalars(q).all())
    return users, total or 0


def get_user(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def create_user(
    db: Session,
    *,
    email: str,
    password: str | None = None,
    full_name: str = "",
    role: str = "user",
    clerk_id: str | None = None,
) -> User:
    """Create user with default permissions."""

    password_hash = None
    if password:
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    user = User(
        email=email.strip().lower(),
        full_name=full_name,
        role=role,
        password_hash=password_hash,
        clerk_id=clerk_id,
        is_active=(role == "admin"),
    )
    db.add(user)
    db.flush()

    perms = UserPermission(
        user_id=user.id,
        can_use_gemini=True,
        can_use_whisper=True,
        max_video_size_gb=6.0,
        can_export_html=True,
        can_export_docx=True,
        can_export_md=True,
        can_export_pdf=True,
    )
    db.add(perms)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user: User,
    *,
    email: str | None = None,
    password: str | None = None,
    full_name: str | None = None,
    clerk_id: str | None = None,
) -> User:
    if email is not None:
        user.email = email.strip().lower()
    if full_name is not None:
        user.full_name = full_name
    if password:
        user.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
    if clerk_id is not None:
        user.clerk_id = clerk_id
    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, user: User) -> User:
    """Set user status to 'desativado' (is_active = False).

    Does NOT toggle – always deactivates.
    """
    user.is_active = False
    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def reactivate_user(db: Session, user: User) -> User:
    """Re-enable a deactivated user (set is_active = True).

    Also clears deleted_at in case the user was soft-deleted,
    effectively restoring them fully.
    """
    user.is_active = True
    user.deleted_at = None
    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def soft_delete_user(db: Session, user: User) -> User:
    """Soft delete – sets deleted_at timestamp.

    The user disappears from default listings but remains in the database.
    """
    user.deleted_at = datetime.now(UTC)
    user.is_active = False
    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def restore_user(db: Session, user: User) -> User:
    """Undo soft delete – clears deleted_at and reactivates."""
    user.deleted_at = None
    user.is_active = True
    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def toggle_active(db: Session, user: User) -> User:
    """Legacy toggle – kept for backward compatibility."""
    user.is_active = not user.is_active
    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def update_role(db: Session, user: User, role: str) -> User:
    user.role = role
    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


# Plan → permission defaults
PLAN_PERMISSION_MAP: dict[str, dict[str, Any]] = {
    "free": {
        "can_use_gemini": True,
        "can_use_whisper": False,
        "max_video_size_gb": FREE_PLAN_MAX_VIDEO_SIZE_GB,
        "can_export_html": True,
        "can_export_docx": True,
        "can_export_md": True,
        "can_export_pdf": True,
    },
    "starter": {
        "can_use_gemini": True,
        "can_use_whisper": False,
        "max_video_size_gb": STARTER_PLAN_MAX_VIDEO_SIZE_GB,
        "can_export_html": True,
        "can_export_docx": True,
        "can_export_md": True,
        "can_export_pdf": True,
    },
    "pro": {
        "can_use_gemini": True,
        "can_use_whisper": True,
        "max_video_size_gb": PRO_PLAN_MAX_VIDEO_SIZE_GB,
        "can_export_html": True,
        "can_export_docx": True,
        "can_export_md": True,
        "can_export_pdf": True,
    },
    "business": {
        "can_use_gemini": True,
        "can_use_whisper": True,
        "max_video_size_gb": BUSINESS_PLAN_MAX_VIDEO_SIZE_GB,
        "can_export_html": True,
        "can_export_docx": True,
        "can_export_md": True,
        "can_export_pdf": True,
    },
}


def update_plan(db: Session, user: User, plan: str) -> User:
    """Update user plan and auto-adjust permissions based on plan tier."""
    user.plan = plan
    user.updated_at = datetime.now(UTC)

    # Auto-update permissions based on plan
    perm_defaults = PLAN_PERMISSION_MAP.get(plan)
    if perm_defaults:
        update_permissions(db, user, **perm_defaults)

    db.commit()
    db.refresh(user)
    return user


def update_permissions(
    db: Session,
    user: User,
    *,
    can_use_gemini: bool | None = None,
    
    can_use_whisper: bool | None = None,
    max_video_size_gb: float | None = None,
    can_export_html: bool | None = None,
    can_export_docx: bool | None = None,
    can_export_md: bool | None = None,
    can_export_pdf: bool | None = None,
    allowed_templates: str | None = None,
) -> UserPermission:
    perms = user.permissions
    if perms is None:
        perms = UserPermission(user_id=user.id)
        db.add(perms)

    if can_use_gemini is not None:
        perms.can_use_gemini = can_use_gemini

    if can_use_whisper is not None:
        perms.can_use_whisper = can_use_whisper

    if max_video_size_gb is not None:
        perms.max_video_size_gb = max_video_size_gb
    if can_export_html is not None:
        perms.can_export_html = can_export_html
    if can_export_docx is not None:
        perms.can_export_docx = can_export_docx
    if can_export_md is not None:
        perms.can_export_md = can_export_md
    if can_export_pdf is not None:
        perms.can_export_pdf = can_export_pdf
    if allowed_templates is not None:
        perms.allowed_templates = allowed_templates

    db.commit()
    db.refresh(perms)
    return perms


def log_api_usage(
    db: Session,
    *,
    user_id: str,
    endpoint: str,
    ai_provider: str,
    tokens_used: int = 0,
    cost_usd: float | None = None,
    group_id: int | None = None,
    video_duration_seconds: int | None = None,
) -> ApiUsageLog:
    log = ApiUsageLog(
        user_id=user_id,
        endpoint=endpoint,
        ai_provider=ai_provider,
        tokens_used=tokens_used,
    )
    if cost_usd is not None:
        from decimal import Decimal

        log.cost_usd = Decimal(str(round(cost_usd, 4)))
    if group_id is not None:
        log.group_id = group_id
    if video_duration_seconds is not None:
        log.video_duration_seconds = video_duration_seconds
    db.add(log)
    db.commit()
    return log


def get_usage_stats(
    db: Session, user_id: str, limit: int = DEFAULT_USAGE_LOG_LIMIT
) -> dict[str, Any]:
    """Return aggregated usage stats for a user."""
    total_requests = (
        db.scalar(select(func.count()).where(ApiUsageLog.user_id == user_id)) or 0
    )

    total_tokens = (
        db.scalar(
            select(func.coalesce(func.sum(ApiUsageLog.tokens_used), 0)).where(
                ApiUsageLog.user_id == user_id
            )
        )
        or 0
    )

    # Count per provider
    rows = db.execute(
        select(ApiUsageLog.ai_provider, func.count())
        .where(ApiUsageLog.user_id == user_id)
        .group_by(ApiUsageLog.ai_provider)
    ).all()
    by_provider = {row[0]: row[1] for row in rows}

    # Recent logs
    recent = list(
        db.scalars(
            select(ApiUsageLog)
            .where(ApiUsageLog.user_id == user_id)
            .order_by(ApiUsageLog.timestamp.desc())
            .limit(limit)
        ).all()
    )

    return {
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "by_provider": by_provider,
        "recent_logs": recent,
    }


def seed_admin(db: Session, email: str) -> User | None:
    """Create admin user if not exists, or promote/activate if already exists."""
    existing = get_user_by_email(db, email)
    if existing:
        changed = False
        if existing.role != "admin":
            existing.role = "admin"
            changed = True
        # Always ensure the admin account is active (not blocked by default False)
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if changed:
            db.commit()
            db.refresh(existing)
            return existing
        return None
    return create_user(db, email=email, full_name="Admin", role="admin")
