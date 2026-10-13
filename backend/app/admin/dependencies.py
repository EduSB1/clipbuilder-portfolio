"""Admin-only dependency: verifies the current JWT user has role='admin'."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.admin.models import User
from app.auth.deps import get_current_user_jwt
from app.database import get_db


def require_admin(
    jwt_payload: dict[str, Any] = Depends(get_current_user_jwt),
    db: Session = Depends(get_db),
) -> User:
    """Dependency that ensures the caller is an active admin.

    Raises 401 if user not found / inactive, 403 if not admin.
    Returns the User ORM object.
    """
    user_id = jwt_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = db.get(User, user_id)
    if not user and user_id.startswith("user_"):
        user = db.query(User).filter(User.clerk_id == user_id).first()

    if not user:
        raise HTTPException(status_code=401, detail="Utilizador não encontrado")

    if user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="Conta removida")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Conta desativada")

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")

    return user


RequireAdmin = Annotated[User, Depends(require_admin)]
