"""Smoke tests: garantem que a aplicação monta e que as rotas essenciais existem.

Barato de rodar e pega a classe de erro mais cara — um import quebrado ou uma
rota que sumiu num refactor — antes do deploy, em vez de depois.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main

# Rotas que o frontend e o monitoramento dependem.  Remover qualquer uma delas
# é uma mudança de contrato, não um detalhe interno.
ESSENTIAL_ROUTES = [
    "/health",
    "/auth/me",
    "/templates",
    "/videos",
    "/videos/youtube",
    "/videos/{video_id}/smart-text",
    "/export",
    "/markdown-to-docx",
    "/markdown-to-pdf",
    "/enhance-document",
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    # Sem `with`: o lifespan (que conecta no Postgres e cria tabelas) não roda,
    # então o smoke test não precisa de banco.
    return TestClient(main.app)


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ESSENTIAL_ROUTES)
def test_essential_route_is_registered(path: str) -> None:
    registered = {getattr(route, "path", None) for route in main.app.routes}
    assert path in registered, f"rota {path} desapareceu do app"


def test_cors_is_not_wide_open() -> None:
    """`allow_origins=["*"]` com `allow_credentials=True` é um erro de segurança.

    A combinação é rejeitada pelos navegadores e, pior, sinaliza que a lista de
    origens foi afrouxada para "resolver" um problema de CORS.
    """
    from app.core.config import settings

    assert "*" not in settings.allowed_origins
