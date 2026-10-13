"""Minimal API router: health check and protected /me."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.admin.models import User
from app.api.deps import CurrentUser
from app.auth.deps import CurrentAuthorizedUser
from app.database import get_db

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Public health check. Returns {"status": "ok"}."""
    return {"status": "ok"}


@router.get("/me")
def me(user: CurrentUser) -> dict[str, str | None]:
    """Protected route. Returns JWT payload (sub, email, role) for auth testing."""
    return {
        "sub": user.get("sub"),
        "email": user.get("email"),
        "role": user.get("role"),
    }


@router.get("/auth/me")
def auth_me(user: CurrentAuthorizedUser) -> dict[str, Any]:
    """Returns the current user from the database."""
    return user


class UserSelfUpdate(BaseModel):
    full_name: str | None = None


@router.patch("/auth/me")
def update_my_profile(
    user: CurrentAuthorizedUser,
    body: UserSelfUpdate = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update the current user's own profile data."""
    from app.auth.store import _user_to_dict
    
    # Get the actual User object from the DB since CurrentAuthorizedUser is a dict
    user_id = user.get("id")
    db_user = db.query(User).filter(User.id == user_id).first()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if body.full_name is not None:
        db_user.full_name = body.full_name.strip()
    
    db.commit()
    db.refresh(db_user)
    
    return _user_to_dict(db_user)
