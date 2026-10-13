"""Application configuration using Pydantic BaseSettings.

All configuration is loaded from environment variables or .env.
No os.getenv elsewhere in the codebase.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import (
    DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
    DEFAULT_LOCAL_JWT_EXPIRE_MINUTES,
    DEFAULT_SMTP_PORT,
    JWKS_CACHE_TTL_SECONDS,
)

_DEFAULT_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _parse_origins_value(v: Any) -> list[str]:
    """Parse allowed_origins from env.

    Accepts:
      - a list (already parsed) → clean and return
      - a JSON array string     → ``'["https://a.com"]'``
      - a comma-separated string → ``'https://a.com,https://b.com'``
      - empty / None             → default origins

    This is used as a ``BeforeValidator`` so it runs *before* pydantic-settings
    attempts its own JSON deserialization of the raw env-var value.
    """
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()] or list(_DEFAULT_ORIGINS)
    if isinstance(v, str):
        raw = v.strip()
        if not raw:
            return list(_DEFAULT_ORIGINS)
        if raw.startswith("["):
            try:
                parsed: list[str] = json.loads(raw)
                result = [str(x).strip() for x in parsed if str(x).strip()]
                return result if result else list(_DEFAULT_ORIGINS)
            except json.JSONDecodeError:
                pass
        result = [x.strip() for x in raw.split(",") if x.strip()]
        return result if result else list(_DEFAULT_ORIGINS)
    return list(_DEFAULT_ORIGINS)


def _resolve_env_file() -> str | None:
    """Resolve .env path relative to backend root (parent of app/)."""
    backend_root = Path(__file__).resolve().parent.parent.parent
    path = backend_root / ".env"
    return str(path) if path.exists() else None


class Settings(BaseSettings):
    """ClipBuilder settings. Loaded from env and .env."""

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Clerk JWT validation
    clerk_issuer: str = ""
    """Clerk issuer URL (e.g. https://your-site.clerk.accounts.dev). Used to validate `iss` and derive JWKS URL."""

    clerk_jwks_uri: str | None = None
    """Optional. If unset, derived as {clerk_issuer}/.well-known/jwks.json.
    When using a Clerk custom domain that the VPS cannot resolve, set this to:
      https://api.clerk.com/v1/jwks   (requires CLERK_SECRET_KEY to be set)
    or the native Clerk URL:
      https://XXXX.clerk.accounts.dev/.well-known/jwks.json
    """

    clerk_secret_key: str = ""
    """Clerk Backend API secret key (sk_live_... or sk_test_...).
    Required when CLERK_JWKS_URI=https://api.clerk.com/v1/jwks because that
    endpoint requires Bearer authentication.
    Also used to fetch user email from the Clerk API when not present in JWT.
    """

    jwks_cache_ttl_seconds: int = JWKS_CACHE_TTL_SECONDS
    """TTL for in-memory JWKS cache. Avoids fetching from Clerk on every request."""

    clerk_webhook_secret: str = ""
    """Svix webhook signing secret from Clerk Dashboard (whsec_...)."""

    clerk_auto_provision_users: bool = False
    """When true, automatically creates/updates a local DB user on first login.

    This is useful for bootstrapping when the DB is empty, but it changes the
    security model (users no longer need to be pre-imported by an admin).
    Recommended: keep false in production unless you want open self-signup.
    """

    # Own JWT auth (python-jose)
    secret_key: str
    """Secret key for signing our own JWTs (required)."""
    jwt_algorithm: str = "HS256"
    """Algorithm for JWT signing."""
    access_token_expire_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES
    """Access token expiry in minutes (default 60 minutes)."""

    # Local admin JWT (/sys/token)
    local_jwt_secret: str = ""
    """Secret used to sign local HS256 admin tokens (LOCAL_JWT_SECRET). Empty disables /sys/token."""

    local_jwt_expire_minutes: int = DEFAULT_LOCAL_JWT_EXPIRE_MINUTES
    """Expiry for local HS256 admin tokens issued by /sys/token (default 8 hours)."""

    # Database (PostgreSQL)
    database_url: str
    """PostgreSQL connection string."""

    # Admin seed
    admin_email: str = "admin@clipbuilder.com"
    """Email for initial admin user seed."""
    admin_password: str
    """Password for initial admin user seed (required)."""

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from_email: str = ""
    frontend_url: str = "http://localhost:5173"

    # Mercado Pago
    mercadopago_access_token: str = ""
    """Access Token do Mercado Pago (TEST-... para testes, APP_USR-... para produção).
    Obtenha em: https://www.mercadopago.com.br/developers/panel/app"""

    mercadopago_webhook_secret: str = ""
    """Secret para validar assinatura dos webhooks do Mercado Pago (opcional mas recomendado)."""

    mercadopago_public_key: str = ""
    """Public Key do Mercado Pago — exposta ao frontend para tokenizar cartão."""

    api_base_url: str = "http://localhost:8000"
    """URL base do backend, usada para montar notification_url do webhook."""

    # CORS
    # ── NOTE ──────────────────────────────────────────────────────────────
    # Pydantic Settings v2 tries to ``json.loads()`` env-var values for
    # complex types (``list[str]``) *before* any ``field_validator`` runs.
    # A plain CSV like ``"https://a.com,https://b.com"`` is not valid JSON,
    # so the parse fails with ``SettingsError``.
    #
    # Fix: wrap the type with ``BeforeValidator`` so our own parser
    # (``_parse_origins_value``) converts the raw string into a list
    # before pydantic-settings' JSON attempt.
    # ─────────────────────────────────────────────────────────────────────
    allowed_origins: Annotated[list[str], BeforeValidator(_parse_origins_value)] = (
        _DEFAULT_ORIGINS
    )
    """Origins allowed by CORS. Also used for `azp` validation when present."""

    clerk_azp_strict: bool = False
    """When true, reject Clerk tokens whose `azp` is not in `allowed_origins`.
    When false, log a warning and accept the token.
    """

    # AI Keys & Models
    gemini_api_key: str = ""
    gemini_model: str = "models/gemini-2.5-flash"
    gemini_vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    gemini_audio_model: str = "whisper-large-v3-turbo"


def get_settings() -> Settings:
    """Return application settings. Use for FastAPI Depends if needed."""
    return Settings()


settings = get_settings()

# Sincroniza chaves com variáveis de ambiente que SDKs legados ou externos esperam
import os

if settings.gemini_api_key and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
