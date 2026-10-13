"""Pydantic schemas for AI Tools CRUD operations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ── Request schemas ────────────────────────────────────────────────────


class AiToolCreate(BaseModel):
    """Schema for creating a new AI tool."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    model_provider: str = Field(..., pattern=r"^(gemini|gemini)$")
    model_name: str = Field(..., min_length=1, max_length=100)
    triggers: list[str] = Field(
        ...,
        min_length=1,
        description="List of trigger points: on_frame_capture, on_export, on_video_upload, manual",
    )
    is_active: bool = True
    scope: str = Field(default="global", pattern=r"^(global|project)$")
    project_id: str | None = None
    output_target: str = Field(
        default="description",
        pattern=r"^(description|log_only|context_tag|suggestion)$",
    )


class AiToolUpdate(BaseModel):
    """Schema for updating an existing AI tool. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None, min_length=1)
    model_provider: str | None = Field(default=None, pattern=r"^(gemini|gemini)$")
    model_name: str | None = Field(default=None, min_length=1, max_length=100)
    triggers: list[str] | None = Field(default=None, min_length=1)
    is_active: bool | None = None
    scope: str | None = Field(default=None, pattern=r"^(global|project)$")
    project_id: str | None = None
    output_target: str | None = Field(
        default=None,
        pattern=r"^(description|log_only|context_tag|suggestion)$",
    )


class AiToolToggle(BaseModel):
    """Schema for toggling a tool on/off."""

    is_active: bool


# ── Response schemas ───────────────────────────────────────────────────


class AiToolResponse(BaseModel):
    """Response schema for a single AI tool."""

    id: str
    name: str
    description: str
    prompt: str
    model_provider: str
    model_name: str
    triggers: list[str]
    is_active: bool
    is_native: bool
    scope: str
    project_id: str | None = None
    output_target: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AiToolLogResponse(BaseModel):
    """Response schema for a tool execution log entry."""

    id: int
    tool_id: str
    trigger: str
    status: str
    input_summary: str | None = None
    output: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AiToolListResponse(BaseModel):
    """Response schema for listing tools."""

    tools: list[AiToolResponse]
    total: int


class AiToolLogListResponse(BaseModel):
    """Response schema for listing tool logs."""

    logs: list[AiToolLogResponse]
    total: int


class ToolRunRequest(BaseModel):
    """Schema for manually running tools for a given trigger."""

    project_id: str | None = None
    image_base64: str | None = None
    previous_steps: list[str] | None = None
    full_document: str | None = None


class ToolRunResult(BaseModel):
    """Response schema for a tool execution result."""

    tool_id: str
    tool_name: str
    output_target: str
    output: str | None = None
    error: str | None = None
    status: str
    duration_ms: int | None = None


class ToolRunResponse(BaseModel):
    """Response schema for running tools."""

    results: list[ToolRunResult]
