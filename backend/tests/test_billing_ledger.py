"""Saldo de créditos e idempotência das compras.

Antes: a idempotência de uma compra olhava só as últimas 200 transações
(empurrar a compra para fora dessa janela permitia creditá-la de novo), e
débito e crédito faziam read-modify-write no Python, perdendo atualizações
quando concorriam.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text

from app.admin.models import CreditTransaction
from app.billing import service
from app.database import SessionLocal
from tests.conftest import auth_header


def _balance(db: Any, user_id: str) -> int:
    db.expire_all()
    return service.get_balance(db, user_id)


def _in_threads(count: int, work: Callable[[int], Any]) -> list[Any]:
    """Run *work* in *count* threads released at the same instant."""
    barrier = threading.Barrier(count)
    results: list[Any] = [None] * count

    def run(index: int) -> None:
        barrier.wait()
        try:
            results[index] = work(index)
        except Exception as exc:  # the assertion inspects it
            results[index] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_same_payment_is_credited_once(db: Any, make_user: Any) -> None:
    user = make_user(credits=0)
    assert service.credit_purchase_once(db, user.id, "pay-1", 100, "Compra") is True
    assert service.credit_purchase_once(db, user.id, "pay-1", 100, "Compra") is False
    assert _balance(db, user.id) == 100


def test_payment_outside_the_old_200_transaction_window_is_not_credited_again(
    db: Any, make_user: Any
) -> None:
    user = make_user(credits=0)
    assert service.credit_purchase_once(db, user.id, "pay-old", 100, "Compra")
    # O ataque: gerar transações até a compra sair das últimas 200.
    db.add_all(
        CreditTransaction(user_id=user.id, amount=0, type="usage", description="ruído")
        for _ in range(250)
    )
    db.commit()
    assert service.credit_purchase_once(db, user.id, "pay-old", 100, "Compra") is False
    assert _balance(db, user.id) == 100


def test_concurrent_confirmations_of_one_payment_credit_once(db: Any, make_user: Any) -> None:
    # Webhook, polling do Pix e checkout de cartão vendo o mesmo pagamento.
    user = make_user(credits=0)

    def confirm(_: int) -> bool:
        with SessionLocal() as session:
            return service.credit_purchase_once(session, user.id, "pay-race", 100, "Compra")

    results = _in_threads(8, confirm)
    assert results.count(True) == 1, results
    assert results.count(False) == 7, results
    assert _balance(db, user.id) == 100


def test_concurrent_debits_never_overdraw(db: Any, make_user: Any) -> None:
    user = make_user(credits=5)

    def debit(_: int) -> bool:
        with SessionLocal() as session:
            try:
                service.debit_credits(session, user.id, 1, endpoint="/smart-text")
                return True
            except Exception:
                return False

    results = _in_threads(12, debit)
    assert results.count(True) == 5, results
    assert _balance(db, user.id) == 0


def test_concurrent_debit_and_purchase_do_not_lose_updates(db: Any, make_user: Any) -> None:
    user = make_user(credits=10)

    def work(index: int) -> None:
        with SessionLocal() as session:
            if index % 2:
                service.debit_credits(session, user.id, 1, endpoint="/smart-text")
            else:
                service.credit_purchase_once(session, user.id, f"pay-{index}", 10, "Compra")

    _in_threads(10, work)
    # 5 compras de 10 e 5 débitos de 1, partindo de 10.
    assert _balance(db, user.id) == 10 + 50 - 5


def test_admin_can_take_balance_below_zero(db: Any, make_user: Any) -> None:
    user = make_user(credits=3)
    service.admin_adjust_credits(db, user.id, -5, "adjustment", "Correção manual")
    assert _balance(db, user.id) == -2


def test_payment_status_polling_credits_once(
    client: Any, db: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.billing import router as billing_router

    user = make_user(credits=0)

    class FakePayment:
        def get(self, payment_id: int) -> dict[str, Any]:
            return {
                "status": 200,
                "response": {
                    "status": "approved",
                    "metadata": {"user_id": user.id, "package_id": "starter", "credits": "100"},
                },
            }

    class FakeSDK:
        def payment(self) -> FakePayment:
            return FakePayment()

    monkeypatch.setattr(billing_router, "_get_mp", FakeSDK)
    for _ in range(3):
        response = client.get("/billing/payment/123", headers=auth_header(user))
        assert response.status_code == 200, response.text
    assert _balance(db, user.id) == 100


def test_migration_reports_payments_already_credited_twice(
    db: Any, make_user: Any, caplog: pytest.LogCaptureFixture
) -> None:
    from app.services.run_migrations import run_migrations

    user = make_user(credits=0)
    db.execute(text("DROP INDEX uq_credit_transactions_purchase_payment"))
    db.add_all(
        CreditTransaction(
            user_id=user.id, amount=100, type="purchase", stripe_payment_intent_id="pay-dup"
        )
        for _ in range(2)
    )
    db.commit()
    try:
        with caplog.at_level(logging.ERROR, logger="clipbuilder"):
            run_migrations()
        assert "pay-dup" in caplog.text
        # Sem o índice, a compra falha em vez de creditar de novo.
        with pytest.raises(Exception, match="ON CONFLICT"):
            service.credit_purchase_once(db, user.id, "pay-new", 10, "Compra")
    finally:
        db.rollback()
        db.execute(text("DELETE FROM credit_transactions"))
        db.commit()
        run_migrations()
