"""FastAPI dependency for current user â€” local JWT only.

Accepts only HS256 tokens issued by /sys/token (issuer = 'clipbuilder-local').
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException

logger = logging.getLogger("clipbuilder")


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        logger.warning("auth_deps: Authorization header is MISSING")
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not isinstance(authorization, str):
        logger.warning("auth_deps: Authorization header is NOT a string: %s", type(authorization))
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    raw = authorization.strip()
    if not raw.lower().startswith("bearer "):
        logger.warning("auth_deps: Authorization header DOES NOT start with Bearer")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = raw[7:].strip()
    if not token:
        logger.warning("auth_deps: Bearer token is EMPTY")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return token


def get_current_user_jwt(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict[str, Any]:
    token = _extract_bearer_token(authorization)
    from app.auth.local_jwt import is_local_token, verify_local_token
    from app.core.security import verify_clerk_token

    try:
        if is_local_token(token):
            return verify_local_token(token)
        else:
            return verify_clerk_token(token)
    except ValueError as e:
        logger.warning("auth_deps: verification failed (token_is_local=%s): %s", is_local_token(token), e)
        raise HTTPException(status_code=401, detail=str(e)) from e


CurrentUserJWT = Annotated[dict[str, Any], Depends(get_current_user_jwt)]


def get_current_authorized_user(user: CurrentUserJWT) -> dict[str, Any]:
    """Return the authenticated and active user from the local DB.

    The user MUST exist in the local database AND be active to access the system.
    No on-demand sync is performed here — accounts must be pre-registered by an admin.
    Deleted or inactive users are explicitly rejected with 403.
    """
    from app.auth.store import get_user_by_clerk_id, get_user_by_id

    sub = user.get("sub", "")
    clerk_id = user.get("_clerk_id", "")

    # 1. Primary — lookup by local UUID
    u = get_user_by_id(sub) if sub else None

    # 2. Fallback — lookup by Clerk ID (sub looks like 'user_...')
    if not u and sub and sub.startswith("user_"):
        u = get_user_by_clerk_id(sub)

    # 3. Fallback — lookup by _clerk_id claim in token
    if not u and clerk_id:
        u = get_user_by_clerk_id(clerk_id)

    if not u:
        # Optional: auto-provision users from Clerk on first login (bootstrapping)
        from app.core.config import settings

        if getattr(settings, "clerk_auto_provision_users", False):
            try:
                from app.auth.clerk_store import get_or_sync_user_from_clerk

                candidate = ""
                if sub and isinstance(sub, str) and sub.startswith("user_"):
                    candidate = sub
                elif clerk_id:
                    candidate = clerk_id

                if candidate:
                    u = get_or_sync_user_from_clerk(candidate)
            except Exception as exc:
                logger.warning("get_current_authorized_user: auto-provision failed: %s", exc)

    if not u:
        logger.warning(
            "get_current_authorized_user: no DB record for sub=%s clerk_id=%s",
            sub[:20] if sub else "",
            clerk_id[:20] if clerk_id else "",
        )
        raise HTTPException(status_code=403, detail="Acesso não autorizado. Conta não cadastrada no sistema.")
    if u.get("deleted_at") is not None:
        logger.warning("get_current_authorized_user: blocked deleted user id=%s", u.get("id"))
        raise HTTPException(status_code=403, detail="Conta removida")
    if not u.get("is_active", True):
        logger.warning("get_current_authorized_user: blocked inactive user id=%s", u.get("id"))
        raise HTTPException(status_code=403, detail="Conta desativada")
    return u


CurrentAuthorizedUser = Annotated[dict[str, Any], Depends(get_current_authorized_user)]


def _check_permission(user: dict[str, Any], permission: str, provider_name: str) -> None:
    permissions = user.get("permissions", {})
    if not permissions.get(permission, True):
        raise HTTPException(
            status_code=403,
            detail=f"Você não tem permissão para usar o {provider_name}. Entre em contato com o administrador.",
        )


def require_gemini_permission(user: CurrentAuthorizedUser) -> dict[str, Any]:
    _check_permission(user, "can_use_gemini", "Gemini")
    return user


def require_whisper_permission(user: CurrentAuthorizedUser) -> dict[str, Any]:
    _check_permission(user, "can_use_whisper", "Whisper")
    return user


RequireGemini = Annotated[dict[str, Any], Depends(require_gemini_permission)]
RequireWhisper = Annotated[dict[str, Any], Depends(require_whisper_permission)]

