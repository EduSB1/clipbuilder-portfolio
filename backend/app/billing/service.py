"""Credit service — core billing logic.

Provides functions to manage user credit accounts:
- get_or_create_account: lazy-create credit account for a user
- get_balance: current credit balance
- has_enough_credits: check if user can afford an operation
- debit_credits: subtract credits and log transaction (raises 402 if insufficient)
- add_credits: add credits (purchase, bonus, refund) and log transaction
- refund_credits: convenience wrapper for refunds
- get_transactions: audit trail for a user
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.admin.models import (
    PURCHASE_PAYMENT_INDEX_WHERE,
    CreditAccount,
    CreditTransaction,
)
from app.core.constants import DEFAULT_TRANSACTION_QUERY_LIMIT, INITIAL_FREE_CREDITS

if TYPE_CHECKING:
    pass

logger = logging.getLogger("clipbuilder")


def _new_id() -> str:
    """Primary key for rows inserted with Core statements (ORM defaults don't run)."""
    return str(uuid.uuid4())


def get_or_create_account(db: Session, user_id: str) -> CreditAccount:
    """Return the CreditAccount for *user_id*, creating one if it doesn't exist.

    New accounts start with ``INITIAL_FREE_CREDITS`` free credits and a
    corresponding bonus transaction is recorded. Two concurrent first calls
    are safe: the insert is ``ON CONFLICT DO NOTHING`` on the unique user_id,
    so only one of them creates the account and records the bonus.
    """
    account = db.query(CreditAccount).filter(CreditAccount.user_id == user_id).first()
    if account:
        return account

    inserted = db.execute(
        pg_insert(CreditAccount)
        .values(
            id=_new_id(),
            user_id=user_id,
            credits_balance=INITIAL_FREE_CREDITS,
            total_credits_purchased=0,
            total_credits_used=0,
        )
        .on_conflict_do_nothing(index_elements=[CreditAccount.user_id])
        .returning(CreditAccount.id)
    ).scalar_one_or_none()

    if inserted and INITIAL_FREE_CREDITS > 0:
        db.add(
            CreditTransaction(
                user_id=user_id,
                amount=INITIAL_FREE_CREDITS,
                type="bonus",
                description=f"Bônus de boas-vindas: {INITIAL_FREE_CREDITS} créditos grátis",
            )
        )
    db.commit()
    if inserted:
        logger.info(
            "Created credit account for user %s with %d free credits",
            user_id,
            INITIAL_FREE_CREDITS,
        )
    return db.query(CreditAccount).filter(CreditAccount.user_id == user_id).one()


def _apply_delta(
    db: Session,
    user_id: str,
    delta: int,
    *,
    purchased: int = 0,
    used: int = 0,
    require_funds: bool = False,
) -> int | None:
    """Change the balance in a single UPDATE and return the new balance.

    The arithmetic happens in the database (``balance = balance + delta``),
    so concurrent debits and credits cannot overwrite each other the way a
    read-modify-write in Python did. With ``require_funds`` the row is only
    updated while the balance covers the debit; ``None`` means it did not.
    Does not commit: the caller records the transaction in the same unit.
    """
    stmt = update(CreditAccount).where(CreditAccount.user_id == user_id)
    if require_funds:
        stmt = stmt.where(CreditAccount.credits_balance >= -delta)
    stmt = stmt.values(
        credits_balance=CreditAccount.credits_balance + delta,
        total_credits_purchased=CreditAccount.total_credits_purchased + purchased,
        total_credits_used=CreditAccount.total_credits_used + used,
        updated_at=func.now(),
    ).returning(CreditAccount.credits_balance)
    return db.execute(stmt).scalar_one_or_none()


def get_balance(db: Session, user_id: str) -> int:
    """Return the current credit balance for *user_id*."""
    account = get_or_create_account(db, user_id)
    return account.credits_balance


def has_enough_credits(db: Session, user_id: str, amount: int) -> bool:
    """Check whether *user_id* has at least *amount* credits."""
    return get_balance(db, user_id) >= amount


def debit_credits(
    db: Session,
    user_id: str,
    amount: int,
    endpoint: str | None = None,
    description: str | None = None,
) -> CreditAccount:
    """Debit *amount* credits from the user's account.

    Creates a ``"usage"`` transaction. If the balance is insufficient,
    raises ``HTTPException(402)`` with a user-friendly message.

    Args:
        db: Active SQLAlchemy session.
        user_id: Local user UUID.
        amount: Number of credits to debit (must be > 0).
        endpoint: Which API endpoint triggered the debit (for auditing).
        description: Human-readable description for the transaction.

    Returns:
        The updated :class:`CreditAccount`.

    Raises:
        HTTPException: 402 if insufficient credits.
    """
    if amount <= 0:
        raise ValueError("Debit amount must be positive")

    get_or_create_account(db, user_id)
    new_balance = _apply_delta(db, user_id, -amount, used=amount, require_funds=True)

    if new_balance is None:
        db.rollback()
        balance = get_balance(db, user_id)
        logger.warning(
            "Insufficient credits for user %s: balance=%d, required=%d, endpoint=%s",
            user_id,
            balance,
            amount,
            endpoint,
        )
        raise HTTPException(
            status_code=402,
            detail=(
                f"Créditos insuficientes. Você tem {balance} crédito(s), "
                f"mas esta operação requer {amount}. Adquira mais créditos para continuar."
            ),
        )

    db.add(
        CreditTransaction(
            user_id=user_id,
            amount=-amount,
            type="usage",
            description=description or f"Uso de {amount} crédito(s) em {endpoint or 'API'}",
            endpoint=endpoint,
        )
    )
    db.commit()

    logger.info(
        "Debited %d credits from user %s (endpoint=%s, new_balance=%d)",
        amount,
        user_id,
        endpoint,
        new_balance,
    )
    return get_or_create_account(db, user_id)


def add_credits(
    db: Session,
    user_id: str,
    amount: int,
    type_: str = "purchase",
    stripe_payment_intent_id: str | None = None,
    description: str | None = None,
) -> CreditAccount:
    """Add *amount* credits to the user's account.

    For a purchase tied to a payment, use :func:`credit_purchase_once`
    instead: it is the only path that refuses to credit a payment twice.

    Args:
        db: Active SQLAlchemy session.
        user_id: Local user UUID.
        amount: Number of credits to add (must be > 0).
        type_: Transaction type — ``"purchase"``, ``"bonus"``, or ``"refund"``.
        stripe_payment_intent_id: Payment id (for purchases).
        description: Human-readable description.

    Returns:
        The updated :class:`CreditAccount`.
    """
    if amount <= 0:
        raise ValueError("Credit amount must be positive")

    get_or_create_account(db, user_id)
    new_balance = _apply_delta(
        db, user_id, amount, purchased=amount if type_ == "purchase" else 0
    )
    db.add(
        CreditTransaction(
            user_id=user_id,
            amount=amount,
            type=type_,
            description=description or f"Adição de {amount} crédito(s) ({type_})",
            stripe_payment_intent_id=stripe_payment_intent_id,
        )
    )
    db.commit()

    logger.info(
        "Added %d credits to user %s (type=%s, payment_id=%s, new_balance=%s)",
        amount,
        user_id,
        type_,
        stripe_payment_intent_id or "N/A",
        new_balance,
    )
    return get_or_create_account(db, user_id)


def credit_purchase_once(
    db: Session,
    user_id: str,
    payment_id: str,
    amount: int,
    description: str,
) -> bool:
    """Credit a paid purchase exactly once per payment id.

    The webhook, the Pix polling endpoint and the card checkout can all see
    the same approved payment, sometimes at the same moment. The purchase
    transaction is inserted with ``ON CONFLICT DO NOTHING`` against the
    unique index ``uq_credit_transactions_purchase_payment``: whichever call
    inserts the row also moves the balance, in the same database
    transaction, and every other call gets ``False`` and changes nothing.

    Returns:
        ``True`` if this call credited the purchase, ``False`` if the payment
        had already been credited.
    """
    if amount <= 0:
        raise ValueError("Credit amount must be positive")

    get_or_create_account(db, user_id)
    inserted = db.execute(
        pg_insert(CreditTransaction)
        .values(
            id=_new_id(),
            user_id=user_id,
            amount=amount,
            type="purchase",
            description=description,
            stripe_payment_intent_id=str(payment_id),
        )
        .on_conflict_do_nothing(
            index_elements=[CreditTransaction.stripe_payment_intent_id],
            index_where=PURCHASE_PAYMENT_INDEX_WHERE,
        )
        .returning(CreditTransaction.id)
    ).scalar_one_or_none()

    if inserted is None:
        db.rollback()
        logger.info("Payment %s already credited (user %s)", payment_id, user_id)
        return False

    new_balance = _apply_delta(db, user_id, amount, purchased=amount)
    db.commit()
    logger.info(
        "Credited purchase: %d credits to user %s (payment_id=%s, new_balance=%s)",
        amount,
        user_id,
        payment_id,
        new_balance,
    )
    return True


def admin_adjust_credits(
    db: Session,
    user_id: str,
    amount: int,
    type_: str,
    description: str | None,
) -> None:
    """Admin override: add or remove credits without the balance check.

    A negative *amount* may take the balance below zero on purpose (manual
    correction); it is still applied atomically.
    """
    if amount == 0:
        raise ValueError("Adjustment amount must not be zero")
    if amount > 0:
        add_credits(db, user_id=user_id, amount=amount, type_=type_, description=description)
        return

    get_or_create_account(db, user_id)
    _apply_delta(db, user_id, amount, used=-amount)
    db.add(
        CreditTransaction(
            user_id=user_id,
            amount=amount,
            type=type_,
            description=description,
        )
    )
    db.commit()


def refund_credits(
    db: Session,
    user_id: str,
    amount: int,
    endpoint: str | None = None,
    description: str | None = None,
) -> CreditAccount:
    """Refund *amount* credits back to the user (e.g. after an AI failure).

    Convenience wrapper around :func:`add_credits` with ``type_="refund"``.
    """
    desc = (
        description
        or f"Reembolso de {amount} crédito(s) (falha em {endpoint or 'API'})"
    )
    return add_credits(
        db,
        user_id=user_id,
        amount=amount,
        type_="refund",
        description=desc,
    )


def charge_endpoint(user: dict[str, Any], endpoint: str) -> str | None:
    """Debit the credit cost of *endpoint* from an authenticated *user*.

    Fails closed: the caller must pass the user resolved by an auth
    dependency, never ``None``. Admins are exempt and nothing is debited.

    Returns:
        The user id when credits were debited, or ``None`` for admins, so the
        result can go straight to :func:`refund_endpoint` on failure.

    Raises:
        HTTPException: 403 if the user record has no id, 402 if the balance
            is insufficient.
    """
    from app.billing.costs import get_credit_cost
    from app.database import SessionLocal

    if user.get("role") == "admin":
        return None
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Conta não identificada.")

    with SessionLocal() as db:
        debit_credits(db, user_id=user_id, amount=get_credit_cost(endpoint), endpoint=endpoint)
    return user_id


def refund_endpoint(user_id: str | None, endpoint: str, amount: int | None = None) -> None:
    """Give back the credits debited by :func:`charge_endpoint` after a failure.

    Does nothing when ``user_id`` is ``None`` (admin, or nothing was debited).
    Errors are logged, not raised: a failed refund must not hide the error
    that triggered it.
    """
    if not user_id:
        return

    from app.billing.costs import get_credit_cost
    from app.database import SessionLocal

    refund_amount = amount if amount is not None else get_credit_cost(endpoint)
    try:
        with SessionLocal() as db:
            refund_credits(db, user_id=user_id, amount=refund_amount, endpoint=endpoint)
        logger.info(
            "Refunded %d credits to user %s (endpoint=%s)", refund_amount, user_id, endpoint
        )
    except Exception as exc:
        logger.error("Failed to refund credits for user %s: %s", user_id, exc, exc_info=True)


def get_transactions(
    db: Session,
    user_id: str,
    limit: int = DEFAULT_TRANSACTION_QUERY_LIMIT,
    offset: int = 0,
) -> list[CreditTransaction]:
    """Return recent credit transactions for *user_id*, newest first."""
    return (
        db.query(CreditTransaction)
        .filter(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
