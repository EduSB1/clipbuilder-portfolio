"""Local JWT authentication — emergency admin backdoor.

Provides a secret management endpoint that issues short-lived HS256 tokens
for admin access when Clerk is unavailable or not yet configured for the
production domain.

Security properties:
- Endpoint path is not documented or linked anywhere in the UI.
- Requires LOCAL_JWT_SECRET env var (disabled when empty).
- Tokens are HS256-signed, expire in LOCAL_JWT_EXPIRE_MINUTES (default 60).
- Only users with role='admin' in the local DB can obtain a token.
- Token issuer is 'clipbuilder-local' to distinguish from Clerk tokens.
- Brute-force protected by slowapi rate limiter on the issuing endpoint.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

logger = logging.getLogger("clipbuilder")

# Issuer claim embedded in every local token — used to detect local vs Clerk tokens
_LOCAL_ISSUER = "clipbuilder-local"


def _get_secret() -> str:
    """Return LOCAL_JWT_SECRET from settings. Empty string means disabled."""
    from app.core.config import settings

    return (settings.local_jwt_secret or "").strip()


def is_enabled() -> bool:
    """Return True if local JWT login is configured (secret is set)."""
    return bool(_get_secret())


def create_local_token(user_id: str, email: str, role: str) -> str:
    """Create a signed HS256 JWT for a local admin user.

    Args:
        user_id: Local DB user UUID.
        email: User email (informational, not used for auth).
        role: Must be 'admin'.

    Returns:
        Compact JWT string.

    Raises:
        RuntimeError: If local JWT is disabled (no secret configured).
        ValueError: If role is not 'admin'.
    """
    secret = _get_secret()
    if not secret:
        raise RuntimeError("Local JWT login is disabled (LOCAL_JWT_SECRET not set)")
    if role != "admin":
        raise ValueError("Local JWT tokens can only be issued to admin users")

    from app.core.config import settings

    expire_minutes = max(5, settings.local_jwt_expire_minutes)

    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": _LOCAL_ISSUER,
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": now,
        "nbf": now,
        "exp": now + expire_minutes * 60,
    }

    import base64
    import json as _json

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = _b64url(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url(_json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def verify_local_token(token: str) -> dict[str, Any]:
    """Verify a local HS256 JWT and return its payload.

    Args:
        token: Raw JWT string (no 'Bearer ' prefix).

    Returns:
        Decoded payload dict with at least sub, email, role.

    Raises:
        ValueError: Token invalid, expired, wrong issuer, or local JWT disabled.
    """
    secret = _get_secret()
    if not secret:
        raise ValueError("Local JWT login is disabled")

    import base64
    import json as _json

    def _b64url_decode(s: str) -> bytes:
        # Re-add padding
        pad = 4 - len(s) % 4
        if pad != 4:
            s += "=" * pad
        return base64.urlsafe_b64decode(s)

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")

    header_b64, body_b64, sig_b64 = parts

    # Verify signature
    signing_input = f"{header_b64}.{body_b64}".encode()
    expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()

    try:
        provided_sig = _b64url_decode(sig_b64)
    except Exception:
        raise ValueError("Invalid token signature encoding") from None

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError("Invalid token signature")

    # Decode header
    try:
        header = _json.loads(_b64url_decode(header_b64))
    except Exception:
        raise ValueError("Invalid token header") from None

    if header.get("alg") != "HS256":
        raise ValueError("Unsupported token algorithm")

    # Decode payload
    try:
        payload = _json.loads(_b64url_decode(body_b64))
    except Exception:
        raise ValueError("Invalid token payload") from None

    # Validate issuer
    if payload.get("iss") != _LOCAL_ISSUER:
        raise ValueError("Invalid token issuer")

    # Validate expiry
    now = int(time.time())
    exp = payload.get("exp", 0)
    nbf = payload.get("nbf", 0)
    if now > exp:
        raise ValueError("Token has expired")
    if now < nbf:
        raise ValueError("Token not yet valid")

    # Validate role
    if payload.get("role") != "admin":
        raise ValueError("Local tokens must have admin role")

    return payload


def is_local_token(token: str) -> bool:
    """Quick check (without full verification) if a token was issued locally.

    Peeks at the payload's 'iss' claim without signature verification.
    Used to route the token to the correct verifier before full validation.
    """
    try:
        import base64
        import json as _json

        parts = token.split(".")
        if len(parts) != 3:
            return False
        pad = 4 - len(parts[1]) % 4
        if pad != 4:
            parts[1] += "=" * pad
        payload = _json.loads(base64.urlsafe_b64decode(parts[1]))
        return payload.get("iss") == _LOCAL_ISSUER
    except Exception:
        return False
