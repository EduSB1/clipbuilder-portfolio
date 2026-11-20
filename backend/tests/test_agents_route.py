"""Rota do agente PydanticAI.

Antes, sem chave do Gemini no ambiente, importar o módulo do agente falhava
dentro do cliente do Google, o main.py engolia o erro e as rotas /agents
sumiam em silêncio, com um traceback no log a cada inicialização.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import main
from tests.conftest import auth_header


def test_route_exists_even_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    # 401 (exige login), não 404 (rota ausente).
    assert TestClient(main.app).post("/agents/extract-steps", json={}).status_code == 401


def test_model_failure_refunds_the_charge(
    client: Any, db: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.billing.service import get_balance

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    user = make_user(credits=10)
    response = client.post(
        "/agents/extract-steps",
        json={"transcript": "Abra o sistema e clique em Salvar."},
        headers=auth_header(user),
    )
    assert response.status_code == 502
    assert "Abra o sistema" not in response.text
    db.expire_all()
    assert get_balance(db, user.id) == 10
