"""Clerk webhook receiver.

Clerk webhooks are delivered via Svix (signed payload + svix-* headers).
We verify the signature when CLERK_WEBHOOK_SECRET is configured.

Events handled:
- user.created, user.updated → upsert user in local DB
- user.deleted               → soft-delete user in local DB
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.auth.clerk_store import soft_delete_user_by_clerk_id, sync_user_from_clerk_payload
from app.core.config import settings

logger = logging.getLogger("clipbuilder")

router = APIRouter(prefix="/webhooks/clerk", tags=["webhooks"]) 


def _headers_dict(request: Request) -> dict[str, str]:
    # Svix verification expects a plain dict with original header names.
    return dict(request.headers.items())


@router.post("")
async def clerk_webhook(request: Request) -> dict[str, Any]:
    raw = await request.body()
    secret = (settings.clerk_webhook_secret or "").strip()

    evt: dict[str, Any]
    if secret:
        try:
            from svix.webhooks import Webhook

            # svix 2.x only validates (returns None); 1.x returned the parsed
            # body. Parse it ourselves after a successful verification.
            Webhook(secret).verify(raw, _headers_dict(request))
        except Exception as exc:
            # Avoid leaking details to the caller.
            logger.warning("clerk_webhook: signature verification failed: %s", exc)
            raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc
        try:
            evt = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON") from None
        if not isinstance(evt, dict):
            raise HTTPException(status_code=400, detail="Invalid JSON")
    else:
        # No secret means no way to tell Clerk from anyone else. Accepting the
        # payload would let a forged user.updated link an attacker's Clerk id
        # to an existing account (including the admin), so refuse instead.
        logger.error("clerk_webhook: CLERK_WEBHOOK_SECRET is not set; refusing the event")
        raise HTTPException(status_code=503, detail="Webhook não configurado")

    event_type = str(evt.get("type") or "")
    data = evt.get("data")

    if not isinstance(data, dict):
        data = {}

    if event_type in ("user.created", "user.updated"):
        synced = sync_user_from_clerk_payload(data)
        return {"ok": True, "type": event_type, "synced": bool(synced)}

    if event_type == "user.deleted":
        clerk_id = str(data.get("id") or "")
        deleted = soft_delete_user_by_clerk_id(clerk_id)
        return {"ok": True, "type": event_type, "deleted": deleted}

    # Ignore other Clerk events
    return {"ok": True, "type": event_type, "ignored": True}
