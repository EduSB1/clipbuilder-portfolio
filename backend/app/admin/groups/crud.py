"""CRUD for groups and members."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.models import ApiUsageLog, User, UserGroup, UserGroupMember
from app.core.constants import (
    DEFAULT_GROUP_MAX_MONTHLY_AI_REQUESTS,
    DEFAULT_GROUP_MAX_STORAGE_GB,
)


def get_groups(db: Session) -> list[UserGroup]:
    """List all groups with member count."""
    groups = list(db.scalars(select(UserGroup).order_by(UserGroup.name)).all())
    for g in groups:
        cnt = (
            db.scalar(
                select(func.count())
                .select_from(UserGroupMember)
                .where(UserGroupMember.group_id == g.id)
            )
            or 0
        )
        g.member_count = cnt  # type: ignore
    return groups


def get_group(db: Session, group_id: int) -> UserGroup | None:
    return db.get(UserGroup, group_id)


def create_group(
    db: Session,
    *,
    name: str,
    description: str | None = None,
    parent_group_id: int | None = None,
    max_storage_gb: int = DEFAULT_GROUP_MAX_STORAGE_GB,
    max_monthly_ai_requests: int = DEFAULT_GROUP_MAX_MONTHLY_AI_REQUESTS,
    can_use_gemini: bool = True,
    
    can_use_whisper: bool = True,
    can_export_html: bool = True,
    can_export_docx: bool = True,
    can_export_md: bool = True,
    can_export_pdf: bool = True,
) -> UserGroup:
    g = UserGroup(
        name=name.strip(),
        description=description,
        parent_group_id=parent_group_id,
        max_storage_gb=max_storage_gb,
        max_monthly_ai_requests=max_monthly_ai_requests,
        can_use_gemini=can_use_gemini,
        
        can_use_whisper=can_use_whisper,
        can_export_html=can_export_html,
        can_export_docx=can_export_docx,
        can_export_md=can_export_md,
        can_export_pdf=can_export_pdf,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def update_group(db: Session, group: UserGroup, **kwargs) -> UserGroup:
    for k, v in kwargs.items():
        if v is not None and hasattr(group, k):
            setattr(group, k, v)
    group.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(group)
    return group


def delete_group(db: Session, group: UserGroup) -> None:
    # Clear primary_group_id for users in this group
    db.execute(
        User.__table__.update()
        .where(User.primary_group_id == group.id)
        .values(primary_group_id=None)
    )
    db.delete(group)
    db.commit()


def get_members(db: Session, group_id: int) -> list[tuple[UserGroupMember, User]]:
    """Return (member, user) for each member of the group."""
    rows = db.execute(
        select(UserGroupMember, User)
        .join(User, UserGroupMember.user_id == User.id)
        .where(UserGroupMember.group_id == group_id)
    ).all()
    return [(m, u) for m, u in rows]


def add_member(
    db: Session, group_id: int, user_id: str, role: str = "member"
) -> UserGroupMember:
    m = UserGroupMember(group_id=group_id, user_id=user_id, role=role)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def remove_member(db: Session, group_id: int, user_id: str) -> None:
    db.execute(
        UserGroupMember.__table__.delete().where(
            UserGroupMember.group_id == group_id,
            UserGroupMember.user_id == user_id,
        )
    )
    db.commit()


def get_group_usage(db: Session, group_id: int) -> dict:
    """Return usage metrics for the group (simplified: from api_usage_logs if group_id set)."""
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    monthly_requests = (
        db.scalar(
            select(func.count())
            .select_from(ApiUsageLog)
            .where(
                ApiUsageLog.group_id == group_id,
                ApiUsageLog.timestamp >= month_start,
            )
        )
        or 0
    )
    cost_usd = db.scalar(
        select(func.coalesce(func.sum(ApiUsageLog.cost_usd), 0)).where(
            ApiUsageLog.group_id == group_id,
            ApiUsageLog.timestamp >= month_start,
        )
    ) or Decimal("0")
    group = db.get(UserGroup, group_id)
    return {
        "current_storage_gb": 0.0,  # placeholder; would need video storage tracking
        "max_storage_gb": group.max_storage_gb if group else 0,
        "monthly_ai_requests": monthly_requests,
        "max_monthly_ai_requests": group.max_monthly_ai_requests if group else 0,
        "cost_this_month_usd": float(cost_usd),
    }
