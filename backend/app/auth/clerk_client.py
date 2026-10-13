import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("clipbuilder")

CLERK_API_URL = "https://api.clerk.com/v1"


def get_clerk_user(user_id: str) -> dict[str, Any] | None:
    """Fetch a Clerk user by ID (e.g. 'user_...')."""
    if not user_id:
        return None
    if not settings.clerk_secret_key:
        logger.warning("clerk_client: CLERK_SECRET_KEY not set")
        return None

    try:
        headers = get_clerk_headers()
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{CLERK_API_URL}/users/{user_id}", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
    except Exception as e:
        logger.error("clerk_client: failed to fetch user %s — %s", user_id[:16], e)
        return None


def get_clerk_headers() -> dict[str, str]:
    """Base headers for Clerk API requests."""
    return {
        "Authorization": f"Bearer {settings.clerk_secret_key}",
        "Content-Type": "application/json",
    }

def get_clerk_user_by_email(email: str) -> dict[str, Any] | None:
    """Fetch user details from Clerk by primary email.
    
    Returns the first user found or None.
    """
    if not settings.clerk_secret_key:
        logger.warning("clerk_client: CLERK_SECRET_KEY not set")
        return None
        
    try:
        headers = get_clerk_headers()
        params = {"email_address": [email.strip().lower()]}
        with httpx.Client(timeout=10.0) as client:
            # Clerk /v1/users endpoint supports filtering by email_address list
            resp = client.get(f"{CLERK_API_URL}/users", headers=headers, params=params)
            resp.raise_for_status()
            users = resp.json()
            if users and len(users) > 0:
                return users[0]
    except Exception as e:
        logger.error("clerk_client: failed to fetch user by email %s — %s", email, e)
    return None

def list_clerk_users(limit: int = 100) -> list[dict[str, Any]]:
    """List users from Clerk with a given limit."""
    if not settings.clerk_secret_key:
        logger.warning("clerk_client: CLERK_SECRET_KEY not set")
        return []
        
    try:
        headers = get_clerk_headers()
        params = {"limit": limit, "order_by": "-created_at"}
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{CLERK_API_URL}/users", headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("clerk_client: failed to list users from Clerk — %s", e)
    return []

def create_clerk_user(email: str, password: str, full_name: str = "") -> str:
    """Create a new user in Clerk API.
    
    Returns the newly created Clerk user ID.
    Raises ValueError with details if creation fails (e.g., weak password).
    """
    if not settings.clerk_secret_key:
        raise ValueError("clerk_client: CLERK_SECRET_KEY not set")
        
    headers = get_clerk_headers()
    
    first_name = ""
    last_name = ""
    if full_name:
        parts = full_name.split(" ", 1)
        first_name = parts[0]
        if len(parts) > 1:
            last_name = parts[1]
            
    payload = {
        "email_address": [email.strip().lower()],
    }
    
    if password:
        payload["password"] = password
        
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{CLERK_API_URL}/users", headers=headers, json=payload)
            # Parse error first if it's 400 or 422 to give a better message
            if resp.status_code in (400, 422):
                err_data = resp.json()
                errors = err_data.get("errors", [])
                if errors:
                    msg = errors[0].get("long_message") or errors[0].get("message") or "Erro de validação do Clerk"
                    raise ValueError(f"Clerk recusou o cadastro: {msg}")
                    
            resp.raise_for_status()
            data = resp.json()
            return data.get("id")
    except httpx.HTTPStatusError as e:
        logger.error("clerk_client: create_user HTTP error — %s", e.response.text)
        raise ValueError(f"Erro na API do Clerk (HTTP {e.response.status_code})") from e
    except httpx.RequestError as e:
        logger.error("clerk_client: create_user Request error — %s", e)
        raise ValueError("Falha de conexão com a API do Clerk") from e
