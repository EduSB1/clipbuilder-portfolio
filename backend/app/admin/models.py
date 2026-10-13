"""SQLAlchemy models for user management, permissions, API usage logs, groups, settings, and AI tools."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ── UserGroup (must be before User due to FK) ──────────────────────────────


class UserGroup(Base):
    """Group/department for organizing users and quotas."""

    __tablename__ = "user_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user_groups.id", ondelete="SET NULL"), nullable=True
    )
    max_storage_gb: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_monthly_ai_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1000
    )
    can_use_gemini: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_use_whisper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_export_html: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_export_docx: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_export_md: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_export_pdf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    parent_group: Mapped[UserGroup | None] = relationship(
        "UserGroup", remote_side="UserGroup.id", back_populates="children_groups"
    )
    children_groups: Mapped[list[UserGroup]] = relationship(
        "UserGroup", back_populates="parent_group"
    )


class User(Base):
    """Application user."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    clerk_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True, default=None
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user"
    )  # admin | user | premium
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free"
    )  # free | starter | pro | business
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    primary_group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user_groups.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Local password hash (bcrypt) — used ONLY for emergency admin JWT login.
    # Regular users authenticate exclusively via Clerk. This field is NULL
    # for all Clerk-only users and is never exposed via any API.
    password_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )

    @property
    def status(self) -> str:
        """Computed status: 'excluido' if soft-deleted, 'desativado' if inactive, else 'ativo'."""
        if self.deleted_at is not None:
            return "excluido"
        if not self.is_active:
            return "desativado"
        return "ativo"

    # Relationships
    permissions: Mapped[UserPermission | None] = relationship(
        "UserPermission",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    usage_logs: Mapped[list[ApiUsageLog]] = relationship(
        "ApiUsageLog", back_populates="user", cascade="all, delete-orphan"
    )
    credit_account: Mapped[CreditAccount | None] = relationship(
        "CreditAccount",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class UserPermission(Base):
    """Per-user AI feature permissions."""

    __tablename__ = "user_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    can_use_gemini: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_use_whisper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_video_size_gb: Mapped[float] = mapped_column(Float, nullable=False, default=6.0)
    can_export_html: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_export_docx: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_export_md: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_export_pdf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_templates: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON list of template IDs
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    user: Mapped[User] = relationship("User", back_populates="permissions")


class ApiUsageLog(Base):
    """Log of API / AI provider usage per user."""

    __tablename__ = "api_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    ai_provider: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # gemini | whisper
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user_groups.id", ondelete="SET NULL"), nullable=True
    )
    video_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="usage_logs")


class UserGroupMember(Base):
    """User membership in groups."""

    __tablename__ = "user_group_members"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="member")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class DailyMetrics(Base):
    """Aggregated metrics per day."""

    __tablename__ = "daily_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    total_videos_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_frames_captured: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_exports: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gemini_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    whisper_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gemini_tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_storage_gb: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0")
    )
    active_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class SystemSetting(Base):
    """Key-value system settings (smtp, ai, storage, security, features)."""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="string"
    )
    is_encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("category", "key", name="uq_system_settings_category_key"),
    )


# ── AI Tools & Agents ──────────────────────────────────────────────────


class AiTool(Base):
    """Configurable AI tool / agent that can be triggered at various points."""

    __tablename__ = "ai_tools"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "gemini"
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    triggers: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON array: ["on_frame_capture", "on_export", "on_video_upload", "manual"]
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_native: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # native tools cannot be deleted
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="global"
    )  # "global" | "project"
    project_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # set when scope == "project"
    output_target: Mapped[str] = mapped_column(
        String(50), nullable=False, default="description"
    )  # "description" | "log_only" | "context_tag" | "suggestion"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    logs: Mapped[list[AiToolLog]] = relationship(
        "AiToolLog", back_populates="tool", cascade="all, delete-orphan"
    )


# ── Credit System (Pay-as-you-go) ─────────────────────────────────────


class CreditAccount(Base):
    """User credit balance for pay-as-you-go billing."""

    __tablename__ = "credit_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    credits_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_credits_purchased: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_credits_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    user: Mapped[User] = relationship("User", back_populates="credit_account")


class CreditTransaction(Base):
    """Audit log for every credit movement (purchase, usage, refund, bonus)."""

    __tablename__ = "credit_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # positive = purchase/bonus, negative = usage
    type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "purchase" | "usage" | "refund" | "bonus"
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    endpoint: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # which endpoint consumed credits
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class AiToolLog(Base):
    """Execution log for an AI tool invocation."""

    __tablename__ = "ai_tool_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_tools.id", ondelete="CASCADE"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "success" | "error" | "cancelled"
    input_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # brief summary of the input (never the raw image)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    tool: Mapped[AiTool] = relationship("AiTool", back_populates="logs")


# ── Document Templates (persistent) ───────────────────────────────────


class DocumentTemplateDef(Base):
    """Persistent document template definition.

    Built-in templates (clipbuilder_pro,  _it, wolbito_pop) are seeded
    on startup.  Admins can import additional templates via the UI.
    """

    __tablename__ = "document_templates"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(10), nullable=False, default="📄")
    category: Mapped[str] = mapped_column(
        String(20), nullable=False, default="general"
    )  # "corporate" | "general" | "custom"
    has_logo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    logo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    header_fields: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )  # JSON array
    sections: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )  # JSON array
    footer_fields: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )  # JSON array
    config: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )  # JSON object
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

