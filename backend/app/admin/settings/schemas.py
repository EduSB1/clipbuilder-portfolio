"""Pydantic schemas for settings endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class SettingItem(BaseModel):
    key: str
    value: str | None
    value_type: str = "string"
    description: str | None = None
    is_encrypted: bool = False


class SettingsUpdate(BaseModel):
    settings: list[dict]  # [{"category": "smtp", "key": "host", "value": "..."}]
