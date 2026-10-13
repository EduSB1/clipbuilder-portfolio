"""Billing API router — credit balance, transactions, packages, Mercado Pago checkout & webhook.

Endpoints:
    GET  /billing/balance           → current credit balance
    GET  /billing/transactions      → transaction history
    GET  /billing/packages          → available credit packages (BRL)
    POST /billing/checkout/pix      → create Pix payment, return QR code
    POST /billing/checkout/card     → transparent card payment with token
    GET  /billing/payment/{id}      → check payment status (polling)
    POST /billing/webhook           → Mercado Pago webhook receiver (no JWT auth)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import CurrentAuthorizedUser
from app.billing.service import (
    add_credits,
    get_balance,
    get_or_create_account,
    get_transactions,
)
from app.core.config import settings
from app.core.constants import (
    BUSINESS_PACKAGE_CREDITS,
    BUSINESS_PACKAGE_PRICE_BRL,
    BUSINESS_PACKAGE_PRICE_CENTS,
    MAX_INSTALLMENTS,
    PRO_PACKAGE_CREDITS,
    PRO_PACKAGE_PRICE_BRL,
    PRO_PACKAGE_PRICE_CENTS,
    STARTER_PACKAGE_CREDITS,
    STARTER_PACKAGE_PRICE_BRL,
    STARTER_PACKAGE_PRICE_CENTS,
)
from app.database import get_db

logger = logging.getLogger("clipbuilder")

router = APIRouter(prefix="/billing", tags=["billing"])

# ── Credit packages (BRL) ─────────────────────────────────────────────────────

CREDIT_PACKAGES: list[dict[str, Any]] = [
    {
        "id": "starter",
        "credits": STARTER_PACKAGE_CREDITS,
        "price_brl": STARTER_PACKAGE_PRICE_BRL,
        "price_cents": STARTER_PACKAGE_PRICE_CENTS,
        "label": "Starter",
        "description": "Ideal para testes e projetos pequenos",
    },
    {
        "id": "pro",
        "credits": PRO_PACKAGE_CREDITS,
        "price_brl": PRO_PACKAGE_PRICE_BRL,
        "price_cents": PRO_PACKAGE_PRICE_CENTS,
        "label": "Pro",
        "description": "Para uso regular e times pequenos",
    },
    {
        "id": "business",
        "credits": BUSINESS_PACKAGE_CREDITS,
        "price_brl": BUSINESS_PACKAGE_PRICE_BRL,
        "price_cents": BUSINESS_PACKAGE_PRICE_CENTS,
        "label": "Business",
        "description": "Para times e uso intensivo",
    },
]

_PACKAGES_BY_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in CREDIT_PACKAGES}


# ── Pydantic models ───────────────────────────────────────────────────────────


class PixCheckoutRequest(BaseModel):
    package_id: str = Field(..., description="ID do pacote de créditos")


class CardCheckoutRequest(BaseModel):
    package_id: str = Field(..., description="ID do pacote de créditos")
    token: str = Field(..., description="Token do cartão gerado pelo SDK JS do MP")
    installments: int = Field(
        1, ge=1, le=MAX_INSTALLMENTS, description="Número de parcelas"
    )
    payment_method_id: str = Field(
        ..., description="ID do método de pagamento (ex: visa, master)"
    )
    issuer_id: str | None = Field(None, description="ID do emissor do cartão")
    payer: dict[str, Any] = Field(
        ..., description="Dados do pagador (email, identification)"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_mp():
    """Lazy-import and configure Mercado Pago SDK. Raises 503 if not configured."""
    try:
        import mercadopago
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Mercado Pago SDK não instalado no backend. Instale com: pip install mercadopago",
        ) from None

    token = (settings.mercadopago_access_token or "").strip()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="MERCADOPAGO_ACCESS_TOKEN não configurada no backend.",
        )

    return mercadopago.SDK(token)


def _check_idempotency(db: Session, user_id: str, payment_id: str | int) -> bool:
    """Check if this payment_id was already credited (idempotency check).

    Returns True if already credited, False otherwise.
    """
    txs = get_transactions(db, user_id, limit=200)
    return any(
        tx.stripe_payment_intent_id == str(payment_id) and tx.type == "purchase"
        for tx in txs
    )


def _credit_user_if_not_done(
    db: Session,
    user_id: str,
    payment_id: str | int,
    credits_amount: int,
    package_id: str,
) -> bool:
    """Credit user if not already credited. Returns True if credited, False if already done."""
    if _check_idempotency(db, user_id, payment_id):
        logger.info(
            "Payment %s already credited to user %s (idempotency check)",
            payment_id,
            user_id,
        )
        return False

    add_credits(
        db,
        user_id=user_id,
        amount=credits_amount,
        type_="purchase",
        stripe_payment_intent_id=str(payment_id),
        description=f"Compra do pacote {package_id}: {credits_amount} créditos",
    )
    logger.info(
        "Credited %d credits to user %s (package=%s, payment_id=%s)",
        credits_amount,
        user_id,
        package_id,
        payment_id,
    )
    return True


def _verify_mp_signature(
    request_headers: dict, payload_bytes: bytes, query_params: dict
) -> bool:
    """Verify Mercado Pago webhook signature.

    MP signs webhooks using HMAC-SHA256. The manifest to sign is:
    "id:{data.id};request-id:{x-request-id};ts:{ts};"

    Returns True if signature is valid OR if no webhook secret is configured
    (allows running without signature verification in development).
    """
    webhook_secret = (settings.mercadopago_webhook_secret or "").strip()
    if not webhook_secret:
        # Secret not configured — skip verification (dev/staging mode)
        logger.warning(
            "MERCADOPAGO_WEBHOOK_SECRET not set — skipping signature verification"
        )
        return True

    x_signature = request_headers.get("x-signature", "")
    x_request_id = request_headers.get("x-request-id", "")

    if not x_signature:
        logger.warning("Webhook received without x-signature header")
        return False

    # Parse ts and v1 from x-signature header
    # Format: "ts=<timestamp>,v1=<hex_signature>"
    ts = None
    v1 = None
    for part in x_signature.split(","):
        part = part.strip()
        if part.startswith("ts="):
            ts = part[3:]
        elif part.startswith("v1="):
            v1 = part[3:]

    if not ts or not v1:
        logger.warning("Webhook x-signature header malformed: %s", x_signature)
        return False

    # data.id comes from query params (MP sends it as ?data.id=xxx)
    data_id = query_params.get("data.id") or query_params.get("id", "")

    # Build the manifest string
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"

    # Compute expected HMAC-SHA256
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, v1):
        logger.warning(
            "Webhook signature mismatch — possible spoofed request. "
            "manifest=%s expected=%s received=%s",
            manifest,
            expected,
            v1,
        )
        return False

    return True


# ── GET /billing/balance ──────────────────────────────────────────────────────


@router.get("/balance")
def billing_balance(
    user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the current credit balance for the authenticated user."""
    user_id = user.get("id", "")
    balance = get_balance(db, user_id)
    account = get_or_create_account(db, user_id)
    return {
        "credits": balance,
        "user_id": user_id,
        "total_purchased": account.total_credits_purchased,
        "total_used": account.total_credits_used,
    }


# ── GET /billing/transactions ─────────────────────────────────────────────────


@router.get("/transactions")
def billing_transactions(
    user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return transaction history for the authenticated user (newest first)."""
    user_id = user.get("id", "")
    txs = get_transactions(db, user_id, limit=min(limit, 200), offset=max(offset, 0))
    return [
        {
            "id": tx.id,
            "amount": tx.amount,
            "type": tx.type,
            "description": tx.description,
            "endpoint": tx.endpoint,
            "stripe_payment_intent_id": tx.stripe_payment_intent_id,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
        for tx in txs
    ]


# ── GET /billing/packages ────────────────────────────────────────────────────


@router.get("/packages")
def billing_packages() -> list[dict[str, Any]]:
    """Return the list of available credit packages (in BRL)."""
    return CREDIT_PACKAGES


# ── POST /billing/checkout/pix ────────────────────────────────────────────────


@router.post("/checkout/pix")
async def billing_checkout_pix(
    body: PixCheckoutRequest,
    user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a Pix payment via Mercado Pago.

    Returns QR code data for the user to scan and pay.
    """
    sdk = _get_mp()

    user_id = user.get("id", "")
    user_email = user.get("email", "")

    package_id = body.package_id.strip()
    if package_id not in _PACKAGES_BY_ID:
        raise HTTPException(
            status_code=400,
            detail=f"Pacote inválido: '{package_id}'. Opções: {list(_PACKAGES_BY_ID.keys())}",
        )

    package = _PACKAGES_BY_ID[package_id]

    # Ensure credit account exists
    get_or_create_account(db, user_id)

    # Build notification URL for webhook
    api_base = (settings.api_base_url or "http://localhost:8000").rstrip("/")
    notification_url = f"{api_base}/billing/webhook"

    # Create Pix payment
    payment_data = {
        "transaction_amount": float(package["price_brl"]),
        "description": f"ClipBuilder — {package['label']} ({package['credits']} créditos)",
        "payment_method_id": "pix",
        "payer": {
            "email": user_email or "cliente@clipbuilder.com",
        },
        "metadata": {
            "user_id": user_id,
            "package_id": package_id,
            "credits": str(package["credits"]),
        },
        "notification_url": notification_url,
    }

    try:
        result = sdk.payment().create(payment_data)
        response = result.get("response", {})
        status_code = result.get("status", 500)

        if status_code not in (200, 201):
            error_msg = response.get("message", "Erro desconhecido")
            logger.error(
                "Mercado Pago Pix creation failed: status=%s, response=%s",
                status_code,
                response,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Falha ao criar pagamento Pix: {error_msg}",
            )

        payment_id = response.get("id")
        payment_status = response.get("status", "pending")

        # Extract QR code data
        point_of_interaction = response.get("point_of_interaction", {})
        transaction_data = point_of_interaction.get("transaction_data", {})
        qr_code = transaction_data.get("qr_code", "")
        qr_code_base64 = transaction_data.get("qr_code_base64", "")

        logger.info(
            "Pix payment created for user %s: payment_id=%s, package=%s",
            user_id,
            payment_id,
            package_id,
        )

        return {
            "payment_id": payment_id,
            "status": payment_status,
            "qr_code": qr_code,
            "qr_code_base64": qr_code_base64,
            "package": package,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Mercado Pago Pix creation error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao criar pagamento Pix: {str(exc)[:200]}",
        ) from exc


# ── POST /billing/checkout/card ───────────────────────────────────────────────


@router.post("/checkout/card")
async def billing_checkout_card(
    body: CardCheckoutRequest,
    user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a card payment via Mercado Pago (transparent checkout).

    The card token is generated by the MP SDK JS on the frontend.
    Card data never touches our backend.
    """
    sdk = _get_mp()

    user_id = user.get("id", "")

    package_id = body.package_id.strip()
    if package_id not in _PACKAGES_BY_ID:
        raise HTTPException(
            status_code=400,
            detail=f"Pacote inválido: '{package_id}'. Opções: {list(_PACKAGES_BY_ID.keys())}",
        )

    package = _PACKAGES_BY_ID[package_id]

    # Ensure credit account exists
    get_or_create_account(db, user_id)

    # Build notification URL for webhook
    api_base = (settings.api_base_url or "http://localhost:8000").rstrip("/")
    notification_url = f"{api_base}/billing/webhook"

    # Build payer data
    payer = body.payer or {}
    payer_email = payer.get("email", "")
    payer_identification = payer.get("identification", {})

    # Create card payment
    payment_data = {
        "transaction_amount": float(package["price_brl"]),
        "description": f"ClipBuilder — {package['label']} ({package['credits']} créditos)",
        "token": body.token,
        "installments": body.installments,
        "payment_method_id": body.payment_method_id,
        "payer": {
            "email": payer_email,
            "identification": payer_identification,
        },
        "metadata": {
            "user_id": user_id,
            "package_id": package_id,
            "credits": str(package["credits"]),
        },
        "notification_url": notification_url,
    }

    if body.issuer_id:
        payment_data["issuer_id"] = body.issuer_id

    try:
        result = sdk.payment().create(payment_data)
        response = result.get("response", {})
        status_code = result.get("status", 500)

        if status_code not in (200, 201):
            error_msg = response.get("message", "Erro desconhecido")
            cause = response.get("cause", [])
            if cause:
                error_details = "; ".join(
                    c.get("description", c.get("code", "")) for c in cause if c
                )
                error_msg = f"{error_msg}: {error_details}"
            logger.error(
                "Mercado Pago card payment failed: status=%s, response=%s",
                status_code,
                response,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Falha no pagamento: {error_msg}",
            )

        payment_id = response.get("id")
        payment_status = response.get("status", "pending")
        status_detail = response.get("status_detail", "")

        logger.info(
            "Card payment created for user %s: payment_id=%s, status=%s, package=%s",
            user_id,
            payment_id,
            payment_status,
            package_id,
        )

        # If approved immediately, credit the user
        approved = payment_status == "approved"
        if approved:
            _credit_user_if_not_done(
                db,
                user_id=user_id,
                payment_id=payment_id,
                credits_amount=package["credits"],
                package_id=package_id,
            )

        return {
            "payment_id": payment_id,
            "status": payment_status,
            "status_detail": status_detail,
            "approved": approved,
            "package": package,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Mercado Pago card payment error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar pagamento: {str(exc)[:200]}",
        ) from exc


# ── GET /billing/payment/{payment_id} ─────────────────────────────────────────


@router.get("/payment/{payment_id}")
def billing_payment_status(
    payment_id: int,
    user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Check payment status and credit user if approved (polling endpoint).

    Used by frontend to poll Pix payment status.
    """
    sdk = _get_mp()
    user_id = user.get("id", "")

    try:
        result = sdk.payment().get(payment_id)
        response = result.get("response", {})
        status_code = result.get("status", 500)

        if status_code != 200:
            raise HTTPException(
                status_code=404,
                detail="Pagamento não encontrado",
            )

        payment_status = response.get("status", "pending")
        status_detail = response.get("status_detail", "")
        metadata = response.get("metadata", {})
        payment_user_id = metadata.get("user_id", "")

        # Security check: only allow the owner to query their payment
        if payment_user_id and payment_user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Você não tem permissão para consultar este pagamento",
            )

        # If approved, credit the user (idempotency handled inside)
        if payment_status == "approved" and payment_user_id == user_id:
            package_id = metadata.get("package_id", "unknown")
            try:
                credits_amount = int(metadata.get("credits", "0"))
            except (ValueError, TypeError):
                credits_amount = 0

            if credits_amount > 0:
                _credit_user_if_not_done(
                    db,
                    user_id=user_id,
                    payment_id=payment_id,
                    credits_amount=credits_amount,
                    package_id=package_id,
                )

        return {
            "payment_id": payment_id,
            "status": payment_status,
            "status_detail": status_detail,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching payment status: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao consultar pagamento: {str(exc)[:200]}",
        ) from exc


# ── POST /billing/webhook ─────────────────────────────────────────────────────


@router.post("/webhook")
async def billing_webhook(request: Request):
    """Receive Mercado Pago webhook notifications.

    **No JWT authentication** — this endpoint is called by Mercado Pago servers.
    Signature is validated via HMAC-SHA256 using MERCADOPAGO_WEBHOOK_SECRET.

    Handles payment notifications to credit users when Pix payments are confirmed.
    """
    # Read raw payload for signature verification
    payload_bytes = await request.body()
    headers = dict(request.headers)
    query_params = dict(request.query_params)

    # Verify webhook signature
    if not _verify_mp_signature(headers, payload_bytes, query_params):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # Parse JSON body
    try:
        import json as _json

        body = _json.loads(payload_bytes) if payload_bytes else {}
    except Exception:
        body = {}

    # Mercado Pago webhook format
    topic = body.get("type") or body.get("topic", "")
    action = body.get("action", "")
    data = body.get("data", {})

    logger.info(
        "Mercado Pago webhook received: topic=%s, action=%s, data=%s",
        topic,
        action,
        data,
    )

    # Handle payment notifications
    if topic == "payment" or action == "payment.created" or action == "payment.updated":
        payment_id = data.get("id")
        if not payment_id:
            # Try to get from query params (older webhook format)
            payment_id = body.get("id")

        if not payment_id:
            logger.warning("Webhook received without payment_id")
            return {"status": "ignored", "reason": "no payment_id"}

        # Fetch payment details from Mercado Pago
        try:
            sdk = _get_mp()
            result = sdk.payment().get(payment_id)
            response = result.get("response", {})
            status_code = result.get("status", 500)

            if status_code != 200:
                logger.error(
                    "Failed to fetch payment %s: status=%s",
                    payment_id,
                    status_code,
                )
                return {"status": "error", "reason": "failed to fetch payment"}

            payment_status = response.get("status", "")
            metadata = response.get("metadata", {})
            user_id = metadata.get("user_id", "")
            package_id = metadata.get("package_id", "")
            credits_str = metadata.get("credits", "0")

            logger.info(
                "Payment %s status=%s, user_id=%s, package=%s",
                payment_id,
                payment_status,
                user_id,
                package_id,
            )

            # Credit user if payment is approved
            if payment_status == "approved" and user_id:
                try:
                    credits_amount = int(credits_str)
                except (ValueError, TypeError):
                    credits_amount = 0

                if credits_amount > 0:
                    from app.database import SessionLocal

                    with SessionLocal() as db:
                        credited = _credit_user_if_not_done(
                            db,
                            user_id=user_id,
                            payment_id=payment_id,
                            credits_amount=credits_amount,
                            package_id=package_id,
                        )
                        if credited:
                            logger.info(
                                "Webhook credited %d credits to user %s",
                                credits_amount,
                                user_id,
                            )

        except Exception as exc:
            logger.error(
                "Error processing webhook for payment %s: %s",
                payment_id,
                exc,
                exc_info=True,
            )
            return {"status": "error", "reason": str(exc)[:100]}

    return {"status": "ok"}
