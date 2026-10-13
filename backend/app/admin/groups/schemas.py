"""Pydantic schemas for groups endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    parent_group_id: int | None = None
    max_storage_gb: int = 100
    max_monthly_ai_requests: int = 1000
    can_use_gemini: bool = True
    can_use_whisper: bool = True
    can_export_html: bool = True
    can_export_docx: bool = True
    can_export_md: bool = True
    can_export_pdf: bool = True


class GroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    parent_group_id: int | None = None
    max_storage_gb: int | None = None
    max_monthly_ai_requests: int | None = None
    can_use_gemini: bool | None = None
    can_use_whisper: bool | None = None
    can_export_html: bool | None = None
    can_export_docx: bool | None = None
    can_export_md: bool | None = None
    can_export_pdf: bool | None = None


class GroupOut(BaseModel):
    id: int
    name: str
    description: str | None
    parent_group_id: int | None
    max_storage_gb: int
    max_monthly_ai_requests: int
    can_use_gemini: bool
    can_use_whisper: bool
    can_export_html: bool
    can_export_docx: bool
    can_export_md: bool
    can_export_pdf: bool
    created_at: datetime
    member_count: int = 0

    model_config = {"from_attributes": True}


class MemberAdd(BaseModel):
    user_id: str
    role: str = "member"


class MemberOut(BaseModel):
    user_id: str
    group_id: int
    role: str
    joined_at: datetime
    user_email: str | None = None
    user_full_name: str | None = None

    model_config = {"from_attributes": True}


class GroupUsageOut(BaseModel):
    current_storage_gb: float = 0.0
    max_storage_gb: int
    monthly_ai_requests: int = 0
    max_monthly_ai_requests: int
    cost_this_month_usd: float = 0.0
