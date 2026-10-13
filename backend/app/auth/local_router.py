"""Secret admin login router — local JWT backdoor.

Mounted at a non-obvious path (/sys) to avoid enumeration.
Not linked or documented anywhere in the public UI.

Endpoints:
  POST /sys/token   — exchange email+password for a local admin JWT
  GET  /sys/ping    — health check (returns 200 only when local JWT is enabled)
"""

import logging

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from app.core.constants import (
    LOCAL_LOGIN_RATE_LIMIT_PER_MINUTE,
    LOGIN_ANTI_ENUMERATION_DELAY_SECONDS,
    MIN_TOKEN_EXPIRE_MINUTES,
)
from app.core.limiter import limiter

logger = logging.getLogger("clipbuilder")

router = APIRouter(prefix="/sys", tags=[])  # No tag = hidden from OpenAPI docs


def _mask_email(email: str) -> str:
    """Mask email to reduce PII leakage in logs."""
    raw = (email or "").strip()
    if "@" not in raw:
        return "***"
    local, domain = raw.split("@", 1)
    if not local:
        return f"***@{domain}"
    if len(local) == 1:
        return f"{local}***@{domain}"
    return f"{local[:2]}***@{domain}"


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class LocalLoginRequest(BaseModel):
    email: str
    password: str


class LocalTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/token", response_model=LocalTokenResponse, include_in_schema=False)
@limiter.limit(f"{LOCAL_LOGIN_RATE_LIMIT_PER_MINUTE}/minute")
def local_login(request: Request, body: LocalLoginRequest = Body(...)):
    """Issue a local admin JWT token.

    Only works when LOCAL_JWT_SECRET is configured in the backend .env.
    Only admin users with a valid password hash in the local DB can authenticate.

    Rate-limited to prevent brute-force attacks.
    All attempts (success and failure) are logged with IP and email.
    """
    from app.auth.local_jwt import create_local_token, is_enabled
    from app.core.config import settings

    client_ip = request.client.host if request.client else "unknown"
    masked_email = _mask_email(body.email)

    # ── Guard: feature must be explicitly enabled ──────────────────────
    if not is_enabled():
        # Return 404 instead of 403 to avoid revealing endpoint existence
        logger.warning(
            "local_login: attempt on disabled endpoint | ip=%s email=%s",
            client_ip,
            masked_email,
        )
        raise HTTPException(status_code=404, detail="Not found")

    # ── Look up user by email ──────────────────────────────────────────
    import bcrypt

    from app.admin.models import User
    from app.database import SessionLocal

    email = (body.email or "").strip().lower()
    password = (body.password or "").strip()

    if not email or not password:
        logger.warning("local_login: missing credentials | ip=%s", client_ip)
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    try:
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()

            if not user:
                logger.warning(
                    "local_login: user not found | ip=%s email=%s",
                    client_ip,
                    masked_email,
                )
                # Constant-time delay to prevent user enumeration
                import time

                time.sleep(LOGIN_ANTI_ENUMERATION_DELAY_SECONDS)
                raise HTTPException(status_code=401, detail="Credenciais inválidas")

            if user.role != "admin":
                logger.warning(
                    "local_login: non-admin attempt | ip=%s email=%s role=%s",
                    client_ip,
                    masked_email,
                    user.role,
                )
                import time

                time.sleep(LOGIN_ANTI_ENUMERATION_DELAY_SECONDS)
                raise HTTPException(status_code=401, detail="Credenciais inválidas")

            if not user.is_active or user.deleted_at is not None:
                logger.warning(
                    "local_login: inactive/deleted user | ip=%s email=%s",
                    client_ip,
                    masked_email,
                )
                raise HTTPException(status_code=403, detail="Conta desativada")

            # ── Verify password ────────────────────────────────────────
            password_hash = getattr(user, "password_hash", None) or ""
            if not password_hash:
                logger.warning(
                    "local_login: user has no password_hash | ip=%s email=%s",
                    client_ip,
                    masked_email,
                )
                raise HTTPException(
                    status_code=401,
                    detail="Este usuário não tem senha local configurada. "
                    "Use o script reset_admin.py para definir uma senha.",
                )

            try:
                valid = bcrypt.checkpw(
                    password.encode("utf-8"),
                    password_hash.encode("utf-8"),
                )
            except Exception as e:
                logger.error(
                    "local_login: bcrypt error | ip=%s email=%s err=%s",
                    client_ip,
                    masked_email,
                    e,
                )
                valid = False

            if not valid:
                logger.warning(
                    "local_login: wrong password | ip=%s email=%s",
                    client_ip,
                    masked_email,
                )
                import time

                time.sleep(LOGIN_ANTI_ENUMERATION_DELAY_SECONDS)
                raise HTTPException(status_code=401, detail="Credenciais inválidas")

            # ── Issue token ────────────────────────────────────────────
            expire_minutes = max(
                MIN_TOKEN_EXPIRE_MINUTES, settings.local_jwt_expire_minutes
            )
            token = create_local_token(
                user_id=user.id,
                email=user.email,
                role=user.role,
            )

            logger.info(
                "local_login: SUCCESS | ip=%s email=%s user_id=%s",
                client_ip,
                masked_email,
                user.id,
            )

            return LocalTokenResponse(
                access_token=token,
                token_type="bearer",
                expires_in=expire_minutes * 60,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "local_login: unexpected error | ip=%s email=%s err=%s",
            client_ip,
            masked_email,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Erro interno") from e
