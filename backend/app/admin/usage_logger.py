"""Utility helpers for logging AI API usage to the database.

This module provides:
- Cost estimation per AI provider/model
- Background-safe logging that won't break the request if it fails
- Optional user extraction from Authorization headers
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.admin.models import ApiUsageLog, User
from app.database import SessionLocal

logger = logging.getLogger("clipbuilder.usage")

# ── Cost estimation tables (USD per 1K tokens / per request) ────────────────

# Rough cost estimates per 1K tokens (input-weighted average)
_COST_PER_1K_TOKENS: dict[str, float] = {
    # Gemini models
    "gemini": 0.0001,  # ~$0.10 per 1M tokens (blended)
    "gemini-2.5-flash": 0.000075,
    "gemini-2.0-flash": 0.0001,
    "gemini-1.5-flash": 0.000075,
    "gemini-1.5-pro": 0.00125,
    "gemini-2.5-pro": 0.00125,
    # Modelos llama (legado do provedor Groq, removido; mantidos para que
    # registros antigos continuem sendo precificados na tela de custos)
    "llama-4-scout": 0.00005,
    "llama-3.3-70b": 0.0001,
    "llama-3": 0.00005,
    # Whisper
    "whisper": 0.0001,  # ~$0.006/min, rough per-request estimate
}

# Flat per-request cost estimate when tokens are unknown
_FLAT_COST_PER_REQUEST: dict[str, float] = {
    "gemini": 0.002,
    "whisper": 0.006,
}


def estimate_cost(
    ai_provider: str,
    model: str = "",
    tokens_used: int = 0,
) -> float:
    """Estimate the USD cost of an AI API call.

    Uses token-based estimation when tokens are known, otherwise falls back
    to a flat per-request estimate.

    Returns:
        Estimated cost in USD (float, 4 decimal places).
    """
    provider_lower = ai_provider.lower().strip()
    model_lower = (model or "").lower().strip()

    if tokens_used > 0:
        # Try model-specific rate first, then provider-level
        rate = None
        for key, value in _COST_PER_1K_TOKENS.items():
            if key in model_lower:
                rate = value
                break
        if rate is None:
            rate = _COST_PER_1K_TOKENS.get(provider_lower, 0.0001)
        return round((tokens_used / 1000.0) * rate, 6)

    # Flat per-request estimate
    return _FLAT_COST_PER_REQUEST.get(provider_lower, 0.001)


def try_extract_user_id(authorization: str | None) -> str | None:
    """Try to extract user_id (sub) from an Authorization Bearer token.

    Returns the user_id string if valid, or None if missing/invalid.
    Never raises – safe for optional usage.
    """
    if not authorization or not isinstance(authorization, str):
        return None

    raw = authorization.strip()
    if not raw.lower().startswith("bearer "):
        return None

    token = raw[7:].strip()
    if not token:
        return None

    try:
        from app.auth.local_jwt import verify_local_token

        payload = verify_local_token(token)
        return payload.get("sub")
    except Exception:
        return None


def try_get_user_group_id(user_id: str, db: Session) -> int | None:
    """Look up the user's primary_group_id. Returns None on any failure."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user.primary_group_id
    except Exception:
        pass
    return None


def log_ai_usage(
    *,
    user_id: str | None,
    endpoint: str,
    ai_provider: str,
    model: str = "",
    tokens_used: int = 0,
    cost_usd: float | None = None,
    group_id: int | None = None,
    video_duration_seconds: int | None = None,
) -> None:
    """Log an AI API usage record to the database.

    This function opens its own DB session so it can be called from
    background tasks or sync contexts without depending on the request's
    session lifecycle.

    If user_id is None, the log is still recorded with user_id set to
    '__anonymous__' (a sentinel value). The dashboard service query will
    still count these records.

    This function never raises – failures are logged as warnings.
    """
    try:
        # Calculate cost if not provided
        if cost_usd is None:
            cost_usd = estimate_cost(ai_provider, model, tokens_used)

        effective_user_id = user_id or "__anonymous__"

        db = SessionLocal()
        try:
            # Verify user exists if not anonymous (FK constraint)
            if effective_user_id != "__anonymous__":
                user_exists = (
                    db.query(User.id).filter(User.id == effective_user_id).first()
                    is not None
                )
                if not user_exists:
                    logger.warning(
                        "Usage log skipped: user_id=%s not found in DB",
                        effective_user_id,
                    )
                    return

                # Try to get group_id if not provided
                if group_id is None:
                    group_id = try_get_user_group_id(effective_user_id, db)
            else:
                # For anonymous, we can't insert due to FK constraint on user_id
                # Try to find a system/admin user to attribute to
                admin_user = (
                    db.query(User.id).filter(User.role == "admin").first()
                )
                if admin_user:
                    effective_user_id = admin_user[0]
                else:
                    # No admin user found and FK is required – skip logging
                    logger.debug(
                        "Usage log skipped: no user available for anonymous request"
                    )
                    return

            log_entry = ApiUsageLog(
                user_id=effective_user_id,
                endpoint=endpoint,
                ai_provider=ai_provider.lower().strip(),
                tokens_used=tokens_used,
                cost_usd=Decimal(str(round(cost_usd, 4))),
                group_id=group_id,
                video_duration_seconds=video_duration_seconds,
                timestamp=datetime.now(UTC),
            )
            db.add(log_entry)
            db.commit()
            logger.info(
                "AI usage logged: user=%s endpoint=%s provider=%s cost=$%.4f",
                effective_user_id,
                endpoint,
                ai_provider,
                cost_usd,
            )
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to log AI usage: %s", exc, exc_info=True)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to create DB session for usage logging: %s", exc)


def log_ai_usage_background(
    *,
    user_id: str | None = None,
    authorization: str | None = None,
    endpoint: str,
    ai_provider: str,
    model: str = "",
    tokens_used: int = 0,
    cost_usd: float | None = None,
    group_id: int | None = None,
    video_duration_seconds: int | None = None,
) -> None:
    """Convenience wrapper that extracts user_id from auth header if needed,
    then calls log_ai_usage.

    Designed to be used with FastAPI's BackgroundTasks:

        background_tasks.add_task(
            log_ai_usage_background,
            authorization=request.headers.get("authorization"),
            endpoint="/smart-text",
            ai_provider="gemini",
            model=model,
        )
    """
    # Resolve user_id from authorization header if not provided directly
    resolved_user_id = user_id
    if resolved_user_id is None and authorization:
        resolved_user_id = try_extract_user_id(authorization)

    log_ai_usage(
        user_id=resolved_user_id,
        endpoint=endpoint,
        ai_provider=ai_provider,
        model=model,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
        group_id=group_id,
        video_duration_seconds=video_duration_seconds,
    )
