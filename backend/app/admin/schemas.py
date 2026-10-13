"""Pydantic schemas for admin endpoints (request/response validation)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# ── User ──────────────────────────────────────────────────────────────


class PermissionOut(BaseModel):
    can_use_gemini: bool = True
    can_use_whisper: bool = True
    max_video_size_gb: float = 6.0
    can_export_html: bool = False
    can_export_docx: bool = True
    can_export_md: bool = False
    can_export_pdf: bool = False
    allowed_templates: str | None = None

    model_config = {"from_attributes": True}


class CreditAccountOut(BaseModel):
    """Credit balance summary embedded in UserOut."""

    credits_balance: int = 0
    total_credits_purchased: int = 0
    total_credits_used: int = 0

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    """Public user representation."""

    id: str
    email: str
    full_name: str
    role: str
    plan: str = "free"
    is_active: bool
    status: str = "ativo"  # ativo | desativado | excluido
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    permissions: PermissionOut | None = None
    credit_account: CreditAccountOut | None = None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    """Body for POST /admin/users."""

    email: EmailStr
    password: str = Field(..., min_length=4)
    full_name: str = ""
    role: str = "user"


class UserUpdate(BaseModel):
    """Body for PUT /admin/users/{id}."""

    email: EmailStr | None = None
    password: str | None = Field(None, min_length=4)
    full_name: str | None = None


class RoleUpdate(BaseModel):
    """Body for PUT /admin/users/{id}/role."""

    role: str = Field(..., pattern="^(admin|user|premium)$")


class PlanUpdate(BaseModel):
    """Body for PUT /admin/users/{id}/plan."""

    plan: str = Field(..., pattern="^(free|starter|pro|business)$")


class PermissionUpdate(BaseModel):
    """Body for PUT /admin/users/{id}/permissions."""

    can_use_gemini: bool | None = None
    can_use_whisper: bool | None = None
    max_video_size_gb: float | None = None
    can_export_html: bool | None = None
    can_export_docx: bool | None = None
    can_export_md: bool | None = None
    can_export_pdf: bool | None = None
    allowed_templates: str | None = None


# ── Pagination ────────────────────────────────────────────────────────


class UserListResponse(BaseModel):
    users: list[UserOut]
    total: int
    page: int
    page_size: int


# ── Usage Stats ───────────────────────────────────────────────────────


class UsageLogOut(BaseModel):
    endpoint: str
    ai_provider: str
    timestamp: datetime
    tokens_used: int

    model_config = {"from_attributes": True}


class UsageStatsOut(BaseModel):
    total_requests: int
    total_tokens: int
    by_provider: dict[str, int]  # provider -> count
    recent_logs: list[UsageLogOut]


# ── Credit Management (Admin) ────────────────────────────────────────


class CreditAdjustRequest(BaseModel):
    """Body for POST /admin/users/{id}/credits."""

    amount: int = Field(..., description="Positivo para adicionar, negativo para remover")
    description: str = Field(..., min_length=1, max_length=255)
    type: str = Field("bonus", pattern="^(bonus|refund|adjustment)$")


class TransactionOut(BaseModel):
    """Single credit transaction."""

    id: str
    amount: int
    type: str
    description: str | None = None
    endpoint: str | None = None
    stripe_payment_intent_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreditInfoResponse(BaseModel):
    """Response for GET /admin/users/{id}/credits."""

    user_id: str
    credits_balance: int
    total_credits_purchased: int
    total_credits_used: int
    transactions: list[TransactionOut]


class YoutubeCookieUploadResponse(BaseModel):
    success: bool
    message: str
    lines: int
