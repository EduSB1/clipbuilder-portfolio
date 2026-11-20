"""Webhooks do Clerk e do Mercado Pago.

Antes, sem o secret configurado (o .env.example vinha com ele vazio), os dois
webhooks aceitavam qualquer payload. No Clerk isso permitia postar um
user.updated com o e-mail do admin e assumir a conta.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.admin.models import User
from app.core.config import settings

CLERK_SECRET = "whsec_" + base64.b64encode(b"segredo-de-teste-do-clerk-32bytes").decode()
MP_SECRET = "segredo-de-teste-do-mercado-pago"


def _clerk_user_event(clerk_id: str, email: str, *, verified: bool = True) -> dict[str, Any]:
    return {
        "type": "user.updated",
        "data": {
            "id": clerk_id,
            "primary_email_address_id": "idn_1",
            "email_addresses": [
                {
                    "id": "idn_1",
                    "email_address": email,
                    "verification": {"status": "verified" if verified else "unverified"},
                }
            ],
            "first_name": "Pessoa",
            "last_name": "Teste",
        },
    }


def _signed_clerk_post(client: Any, event: dict[str, Any]) -> Any:
    from svix.webhooks import Webhook

    body = json.dumps(event)
    msg_id = f"msg_{uuid.uuid4().hex}"
    now = datetime.now(UTC)
    signature = Webhook(CLERK_SECRET).sign(msg_id, now, body)
    return client.post(
        "/webhooks/clerk",
        content=body,
        headers={
            "svix-id": msg_id,
            "svix-timestamp": str(int(now.timestamp())),
            "svix-signature": signature,
            "content-type": "application/json",
        },
    )


@pytest.fixture
def clerk_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "clerk_webhook_secret", CLERK_SECRET)


def test_clerk_webhook_without_secret_refuses_forged_takeover(
    client: Any, db: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "clerk_webhook_secret", "")
    admin = make_user(role="admin")
    forged = _clerk_user_event("user_atacante", admin.email)
    response = client.post("/webhooks/clerk", json=forged)
    assert response.status_code == 503
    db.refresh(admin)
    assert admin.clerk_id is None


def test_clerk_webhook_rejects_bad_signature(client: Any, clerk_secret: None) -> None:
    response = client.post(
        "/webhooks/clerk",
        json=_clerk_user_event("user_x", "x@example.com"),
        headers={"svix-id": "msg_1", "svix-timestamp": "1", "svix-signature": "v1,AAAA"},
    )
    assert response.status_code == 400


def test_clerk_webhook_ignores_unverified_email(
    client: Any, db: Any, make_user: Any, clerk_secret: None
) -> None:
    admin = make_user(role="admin")
    response = _signed_clerk_post(client, _clerk_user_event("user_novo", admin.email, verified=False))
    assert response.status_code == 200
    assert response.json()["synced"] is False
    db.refresh(admin)
    assert admin.clerk_id is None


def test_clerk_webhook_links_verified_email(
    client: Any, db: Any, make_user: Any, clerk_secret: None
) -> None:
    user = make_user()
    response = _signed_clerk_post(client, _clerk_user_event("user_legitimo", user.email))
    assert response.json()["synced"] is True
    db.refresh(user)
    assert user.clerk_id == "user_legitimo"


def test_clerk_webhook_never_rebinds_an_account_owned_by_another_clerk_user(
    client: Any, db: Any, make_user: Any, clerk_secret: None
) -> None:
    user = make_user()
    user.clerk_id = "user_dono"
    db.commit()
    response = _signed_clerk_post(client, _clerk_user_event("user_outro", user.email))
    assert response.json()["synced"] is False
    db.refresh(user)
    assert user.clerk_id == "user_dono"


def _mp_headers(data_id: str, secret: str = MP_SECRET) -> dict[str, str]:
    request_id = uuid.uuid4().hex
    ts = str(int(datetime.now(UTC).timestamp()))
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts={ts},v1={v1}", "x-request-id": request_id}


@pytest.fixture
def fake_mp(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """SDK falso do Mercado Pago; `state` diz o que a API vai responder."""
    from app.billing import router as billing_router

    state: dict[str, Any] = {"calls": 0, "user_id": None}

    class FakePayment:
        def get(self, payment_id: Any) -> dict[str, Any]:
            state["calls"] += 1
            return {
                "status": 200,
                "response": {
                    "status": "approved",
                    "metadata": {"user_id": state["user_id"], "package_id": "starter", "credits": "100"},
                },
            }

    class FakeSDK:
        def payment(self) -> FakePayment:
            return FakePayment()

    monkeypatch.setattr(billing_router, "_get_mp", FakeSDK)
    return state


def test_mp_webhook_without_secret_is_refused(
    client: Any, fake_mp: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mercadopago_webhook_secret", "")
    response = client.post(
        "/billing/webhook?data.id=55&type=payment",
        json={"type": "payment", "data": {"id": "55"}},
    )
    assert response.status_code == 400
    assert fake_mp["calls"] == 0


def test_mp_webhook_rejects_wrong_signature(
    client: Any, fake_mp: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mercadopago_webhook_secret", MP_SECRET)
    response = client.post(
        "/billing/webhook?data.id=55&type=payment",
        json={"type": "payment", "data": {"id": "55"}},
        headers=_mp_headers("55", secret="outro-segredo"),
    )
    assert response.status_code == 400
    assert fake_mp["calls"] == 0


def test_mp_webhook_redelivery_credits_once(
    client: Any, db: Any, make_user: Any, fake_mp: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.billing.service import get_balance

    monkeypatch.setattr(settings, "mercadopago_webhook_secret", MP_SECRET)
    user = make_user(credits=0)
    fake_mp["user_id"] = user.id
    for _ in range(3):  # o MP reenvia a mesma notificação
        response = client.post(
            "/billing/webhook?data.id=77&type=payment",
            json={"type": "payment", "data": {"id": "77"}},
            headers=_mp_headers("77"),
        )
        assert response.status_code == 200, response.text
    db.expire_all()
    assert get_balance(db, user.id) == 100
    assert db.query(User).count() == 1
