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
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.admin.models import CreditAccount, CreditTransaction
from app.core.constants import DEFAULT_TRANSACTION_QUERY_LIMIT, INITIAL_FREE_CREDITS

if TYPE_CHECKING:
    pass

logger = logging.getLogger("clipbuilder")


def get_or_create_account(db: Session, user_id: str) -> CreditAccount:
    """Return the CreditAccount for *user_id*, creating one if it doesn't exist.

    New accounts start with ``INITIAL_FREE_CREDITS`` free credits and a
    corresponding bonus transaction is recorded.
    """
    account = db.query(CreditAccount).filter(CreditAccount.user_id == user_id).first()
    if account:
        return account

    account = CreditAccount(
        user_id=user_id,
        credits_balance=INITIAL_FREE_CREDITS,
        total_credits_purchased=0,
        total_credits_used=0,
    )
    db.add(account)
    db.flush()

    # Record the initial bonus transaction
    if INITIAL_FREE_CREDITS > 0:
        tx = CreditTransaction(
            user_id=user_id,
            amount=INITIAL_FREE_CREDITS,
            type="bonus",
            description=f"Bônus de boas-vindas: {INITIAL_FREE_CREDITS} créditos grátis",
        )
        db.add(tx)

    db.commit()
    db.refresh(account)
    logger.info(
        "Created credit account for user %s with %d free credits",
        user_id,
        INITIAL_FREE_CREDITS,
    )
    return account


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

    account = get_or_create_account(db, user_id)

    if account.credits_balance < amount:
        logger.warning(
            "Insufficient credits for user %s: balance=%d, required=%d, endpoint=%s",
            user_id,
            account.credits_balance,
            amount,
            endpoint,
        )
        raise HTTPException(
            status_code=402,
            detail=(
                f"Créditos insuficientes. Você tem {account.credits_balance} crédito(s), "
                f"mas esta operação requer {amount}. Adquira mais créditos para continuar."
            ),
        )

    account.credits_balance -= amount
    account.total_credits_used += amount

    tx = CreditTransaction(
        user_id=user_id,
        amount=-amount,
        type="usage",
        description=description or f"Uso de {amount} crédito(s) em {endpoint or 'API'}",
        endpoint=endpoint,
    )
    db.add(tx)
    db.commit()
    db.refresh(account)

    logger.info(
        "Debited %d credits from user %s (endpoint=%s, new_balance=%d)",
        amount,
        user_id,
        endpoint,
        account.credits_balance,
    )
    return account


def add_credits(
    db: Session,
    user_id: str,
    amount: int,
    type_: str = "purchase",
    stripe_payment_intent_id: str | None = None,
    description: str | None = None,
) -> CreditAccount:
    """Add *amount* credits to the user's account.

    Args:
        db: Active SQLAlchemy session.
        user_id: Local user UUID.
        amount: Number of credits to add (must be > 0).
        type_: Transaction type — ``"purchase"``, ``"bonus"``, or ``"refund"``.
        stripe_payment_intent_id: Stripe PaymentIntent ID (for purchases).
        description: Human-readable description.

    Returns:
        The updated :class:`CreditAccount`.
    """
    if amount <= 0:
        raise ValueError("Credit amount must be positive")

    account = get_or_create_account(db, user_id)

    account.credits_balance += amount
    if type_ == "purchase":
        account.total_credits_purchased += amount

    tx = CreditTransaction(
        user_id=user_id,
        amount=amount,
        type=type_,
        description=description or f"Adição de {amount} crédito(s) ({type_})",
        stripe_payment_intent_id=stripe_payment_intent_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(account)

    logger.info(
        "Added %d credits to user %s (type=%s, stripe_pi=%s, new_balance=%d)",
        amount,
        user_id,
        type_,
        stripe_payment_intent_id or "N/A",
        account.credits_balance,
    )
    return account


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
