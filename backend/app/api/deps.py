"""FastAPI dependency injection for protected routes (local JWT)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends

from app.auth.deps import get_current_user_jwt

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user_jwt)]
