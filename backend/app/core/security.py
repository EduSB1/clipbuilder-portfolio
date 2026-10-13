"""Clerk JWT validation using JWKS.

Fetches public keys from Clerk, caches them in memory, and verifies
RS256-signed JWTs. No os.getenv; uses app.core.config.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKSet
from jwt.exceptions import PyJWKError

from app.core.config import settings

# ---------------------------------------------------------------------------
# NOTE on Clerk custom domains and JWKS resolution
# ---------------------------------------------------------------------------
# When Clerk is configured with a custom domain (e.g. clerk.example.com),
# the JWT `iss` claim contains that custom domain. However, VPS/datacenter
# environments often cannot resolve the DNS for that custom domain because
# Clerk uses a specific CDN configuration.
#
# Solution: set CLERK_JWKS_URI in backend/.env to one of:
#   a) The native Clerk JWKS URL: https://XXXX.clerk.accounts.dev/.well-known/jwks.json
#   b) The Clerk API endpoint (requires secret key): https://api.clerk.com/v1/jwks
#
# The CLERK_ISSUER must still match the `iss` claim in the JWT exactly
# (whatever Clerk puts in the token — check with CLERK_LOG_TOKEN_CLAIMS=true).
# ---------------------------------------------------------------------------

logger = logging.getLogger("clipbuilder")

# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

_JWKS_CACHE: dict[str, Any] = {}
_JWKS_LOCK = threading.Lock()


def _jwks_uri() -> str:
    """Resolve JWKS URI from config. Uses CLERK_JWKS_URI or derives from CLERK_ISSUER."""
    if settings.clerk_jwks_uri:
        return settings.clerk_jwks_uri.strip()
    base = (settings.clerk_issuer or "").strip().rstrip("/")
    if not base:
        raise ValueError(
            "CLERK_ISSUER or CLERK_JWKS_URI must be set for JWT verification"
        )
    return f"{base}/.well-known/jwks.json"


def _jwks_auth_header() -> dict[str, str]:
    """Return Authorization header for JWKS fetch if CLERK_SECRET_KEY is set.

    Needed when CLERK_JWKS_URI points to https://api.clerk.com/v1/jwks,
    which requires Bearer authentication with the Clerk secret key.
    Also used when the JWKS endpoint is the custom-domain one that requires auth.
    """
    secret_key = getattr(settings, "clerk_secret_key", "") or ""
    secret_key = secret_key.strip()
    if secret_key:
        return {"Authorization": f"Bearer {secret_key}"}
    return {}


def _get_cached_jwks() -> dict[str, Any] | None:
    """Return cached JWKS dict if still valid, else None."""
    with _JWKS_LOCK:
        entry = _JWKS_CACHE.get("data")
        expires = _JWKS_CACHE.get("expires_at", 0.0)
    if entry and expires and time.monotonic() < expires:
        return entry
    return None


def _set_cached_jwks(data: dict[str, Any]) -> None:
    """Store JWKS in cache with TTL from config."""
    ttl = max(60, settings.jwks_cache_ttl_seconds)
    with _JWKS_LOCK:
        _JWKS_CACHE["data"] = data
        _JWKS_CACHE["expires_at"] = time.monotonic() + ttl


def _fetch_jwks(uri: str) -> dict[str, Any]:
    """Fetch JWKS JSON from URI. Raises on non-2xx or invalid JSON.

    Automatically includes a Bearer token when CLERK_SECRET_KEY is configured.
    This is required for https://api.clerk.com/v1/jwks and also useful when
    the custom domain JWKS endpoint requires authentication.
    """
    headers = _jwks_auth_header()
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(uri, headers=headers)
    except httpx.ConnectError as e:
        raise ValueError(
            f"Cannot connect to JWKS endpoint '{uri}'. "
            "If using a Clerk custom domain that does not resolve from the VPS, "
            "set CLERK_JWKS_URI=https://api.clerk.com/v1/jwks in backend/.env "
            "and ensure CLERK_SECRET_KEY is also set."
        ) from e
    except httpx.TimeoutException as e:
        raise ValueError(
            f"Timeout fetching JWKS from '{uri}'. "
            "Check network connectivity from the VPS to Clerk."
        ) from e

    if resp.status_code == 401:
        raise ValueError(
            f"JWKS endpoint '{uri}' returned 401 Unauthorized. "
            "Set CLERK_SECRET_KEY in backend/.env so the request can be authenticated."
        )
    if resp.status_code == 404:
        raise ValueError(
            f"JWKS endpoint '{uri}' returned 404. "
            "Check CLERK_JWKS_URI — it may be pointing to a wrong URL. "
            "Try: CLERK_JWKS_URI=https://api.clerk.com/v1/jwks"
        )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ValueError(
            f"JWKS endpoint '{uri}' returned HTTP {resp.status_code}: {resp.text[:200]}"
        ) from e

    try:
        out: dict[str, Any] = resp.json()
    except Exception as e:
        raise ValueError(
            f"JWKS response from '{uri}' is not valid JSON: {resp.text[:200]}"
        ) from e

    if "keys" not in out or not isinstance(out["keys"], list):
        raise ValueError(
            f"JWKS response from '{uri}' missing or invalid 'keys' array. "
            f"Got keys: {list(out.keys())}"
        )
    if len(out["keys"]) == 0:
        raise ValueError(
            f"JWKS response from '{uri}' has an empty 'keys' array. "
            "The Clerk instance may be inactive or misconfigured."
        )
    return out


def _get_jwks() -> dict[str, Any]:
    """Return JWKS dict, from cache or by fetching. Thread-safe."""
    cached = _get_cached_jwks()
    if cached is not None:
        return cached
    uri = _jwks_uri()
    logger.info("clerk_jwks: fetching from %s", uri)
    try:
        data = _fetch_jwks(uri)
        _set_cached_jwks(data)
        logger.info(
            "clerk_jwks: loaded %d key(s) from %s",
            len(data.get("keys", [])),
            uri,
        )
        return data
    except Exception as e:
        logger.error(
            "clerk_jwks: FAILED to fetch from %s — %s\n"
            "→ Fix: add CLERK_JWKS_URI=https://api.clerk.com/v1/jwks "
            "and CLERK_SECRET_KEY=sk_... to backend/.env",
            uri,
            e,
        )
        raise


def _get_signing_key(token: str):
    """Resolve signing key for token from cached JWKS. Uses PyJWKSet."""
    jwks_data = _get_jwks()
    jwks = PyJWKSet.from_dict(jwks_data)
    try:
        header = jwt.get_unverified_header(token)
    except Exception as e:
        raise PyJWKError("Invalid token format") from e
    kid = header.get("kid")
    if not kid:
        raise PyJWKError("Token header is missing 'kid'")
    for key in jwks.keys:
        if key.key_id == kid:
            return key
    raise PyJWKError(f"Unable to find a signing key that matches: '{kid}'")


def verify_clerk_token(token: str) -> dict[str, Any]:
    """Verify a Clerk-issued JWT and return its payload.

    Fetches JWKS from Clerk (with in-memory cache), verifies signature (RS256),
    issuer (CLERK_ISSUER), exp, and nbf. Optionally validates `azp` against
    ALLOWED_ORIGINS.

    Args:
        token: Raw JWT string (no \"Bearer \" prefix).

    Returns:
        Decoded payload (e.g. sub, session_id, azp).

    Raises:
        ValueError: Token invalid, expired, wrong issuer, or azp not allowed.
    """
    issuer = (settings.clerk_issuer or "").strip()
    if not issuer:
        raise ValueError("CLERK_ISSUER must be set for JWT verification")

    # Log unverified claims at INFO level to help diagnose issuer mismatches.
    # This is especially useful when CLERK_ISSUER does not match the `iss` in the token.
    _token_iss = ""
    try:
        _unverified_payload = jwt.decode(token, options={"verify_signature": False})
        _token_iss = _unverified_payload.get("iss", "")
        logger.info(
            "clerk_jwt: token claims — iss=%s azp=%s sub=%s",
            _token_iss,
            _unverified_payload.get("azp"),
            (_unverified_payload.get("sub") or "")[:20],
        )
        # Warn early if the token issuer does not match config — saves a round-trip
        if _token_iss and issuer and _token_iss.rstrip("/") != issuer.rstrip("/"):
            logger.warning(
                "clerk_jwt: issuer MISMATCH — token iss='%s' but CLERK_ISSUER='%s'. "
                "Update CLERK_ISSUER in backend/.env to match the token's iss claim.",
                _token_iss,
                issuer,
            )
    except Exception:
        pass

    try:
        signing_key = _get_signing_key(token)
    except PyJWKError as e:
        logger.warning("clerk_jwt: signing key lookup failed: %s", e)
        raise ValueError("Invalid or unsupported JWT (key lookup failed)") from e

    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iss": True,
                "require": ["exp", "nbf"],
            },
        )
    except jwt.ExpiredSignatureError as e:
        logger.debug("clerk_jwt: token expired")
        raise ValueError("Token has expired") from e
    except jwt.ImmatureSignatureError as e:
        logger.debug("clerk_jwt: token not yet valid (nbf)")
        raise ValueError("Token not yet valid") from e
    except jwt.InvalidIssuerError as e:
        logger.warning(
            "clerk_jwt: issuer mismatch — token iss='%s' but CLERK_ISSUER='%s'. "
            "Set CLERK_ISSUER in backend/.env to exactly match the 'iss' claim in the token.",
            _token_iss,
            issuer,
        )
        raise ValueError(
            f"Invalid token issuer. Token has iss='{_token_iss}' but "
            f"backend expects CLERK_ISSUER='{issuer}'. "
            "Update CLERK_ISSUER in backend/.env."
        ) from e
    except jwt.InvalidTokenError as e:
        logger.warning("clerk_jwt: invalid token: %s", e)
        raise ValueError("Invalid token") from e

    # Optional: validate azp (authorized party) against allowed origins.
    #
    # IMPORTANT: We only enforce azp rejection when CLERK_AZP_STRICT=true.
    # By default we log a warning but accept
    # the token. This prevents a common misconfiguration lockout where
    # ALLOWED_ORIGINS does not include the exact origin that Clerk embeds as
    # `azp` (e.g. "https://clipbuilder.com.br" vs "https://www.clipbuilder.com.br").
    #
    # To enable strict mode: set CLERK_AZP_STRICT=true in backend/.env
    azp = payload.get("azp")
    if azp is not None and isinstance(azp, str):
        allowed = list(settings.allowed_origins or [])
        azp_strict = bool(getattr(settings, "clerk_azp_strict", False))
        if allowed and azp not in allowed:
            if azp_strict:
                logger.warning(
                    "clerk_jwt: azp=%s not in ALLOWED_ORIGINS=%s — rejecting (strict mode)",
                    azp,
                    allowed,
                )
                raise ValueError("Token azp not in allowed origins")
            else:
                logger.warning(
                    "clerk_jwt: azp=%s not in ALLOWED_ORIGINS=%s — "
                    "accepting token (set CLERK_AZP_STRICT=true to enforce). "
                    "Add '%s' to ALLOWED_ORIGINS in backend/.env to silence this warning.",
                    azp,
                    allowed,
                    azp,
                )

    return payload
