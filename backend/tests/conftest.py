"""Configuração compartilhada dos testes.

As variáveis de ambiente precisam existir ANTES de qualquer import de `app.*`,
porque `app.core.config` instancia as settings no momento da importação.

Testes que usam as fixtures `db`, `make_user` ou `client` precisam de um
Postgres real (ON CONFLICT, RETURNING e índices parciais não existem no
SQLite). Aponte `TEST_DATABASE_URL` para um banco descartável:

    docker run -d --rm --name cb-test-pg -p 127.0.0.1:55432:5432 \\
        -e POSTGRES_USER=clipbuilder -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=clipbuilder_test postgres:16-alpine
    TEST_DATABASE_URL=postgresql://clipbuilder:test@127.0.0.1:55432/clipbuilder_test pytest

Sem a variável esses testes são pulados, exceto quando
CLIPBUILDER_REQUIRE_DB_TESTS=1 (o CI usa isso): aí eles falham.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from typing import Annotated, Any

import pytest
from fastapi import Header, HTTPException

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-production")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://clipbuilder:test@localhost:5432/clipbuilder_test"
)
os.environ.setdefault("CLIPBUILDER_DATA_DIR", "/tmp/clipbuilder-test-data")
os.environ.setdefault("CLIPBUILDER_LOG_DIR", "/tmp/clipbuilder-test-logs")

# Prefixo do token falso aceito pelo cliente de teste: "Bearer test:<user_id>".
_TEST_TOKEN_PREFIX = "Bearer test:"


def auth_header(user: Any) -> dict[str, str]:
    """Header Authorization que o cliente de teste resolve para *user*."""
    return {"Authorization": f"{_TEST_TOKEN_PREFIX}{user.id}"}


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Any]:
    if not TEST_DATABASE_URL:
        if os.environ.get("CLIPBUILDER_REQUIRE_DB_TESTS") == "1":
            pytest.fail("CLIPBUILDER_REQUIRE_DB_TESTS=1, mas TEST_DATABASE_URL não foi definido")
        pytest.skip("TEST_DATABASE_URL não definido: testes com banco pulados")

    import app.admin.models  # noqa: F401  (registra todos os modelos no metadata)
    from app.database import Base, engine
    from app.services.run_migrations import run_migrations

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_migrations()
    yield engine


@pytest.fixture
def db(db_engine: Any) -> Iterator[Any]:
    """Sessão num banco com todas as tabelas vazias."""
    from sqlalchemy import text

    from app.database import Base, SessionLocal

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def make_user(db: Any) -> Callable[..., Any]:
    """Cria um usuário ativo. `credits` define o saldo inicial."""
    from app.admin.crud import create_user
    from app.billing.service import get_or_create_account

    def _make(role: str = "user", credits: int | None = None, **permissions: Any) -> Any:
        user = create_user(db, email=f"{uuid.uuid4().hex[:10]}@example.com", role=role)
        user.is_active = True
        for name, value in permissions.items():
            setattr(user.permissions, name, value)
        db.commit()
        if credits is not None:
            account = get_or_create_account(db, user.id)
            account.credits_balance = credits
            db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def client(db: Any) -> Iterator[Any]:
    """TestClient com a verificação de JWT trocada por um token de teste.

    Só a criptografia do token é substituída: a busca do usuário no banco, o
    bloqueio de conta inativa e as checagens de permissão e de dono rodam de
    verdade.
    """
    from fastapi.testclient import TestClient

    import main
    from app.auth.deps import get_current_user_jwt

    def fake_jwt(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> dict[str, Any]:
        if not authorization or not authorization.startswith(_TEST_TOKEN_PREFIX):
            raise HTTPException(status_code=401, detail="Token ausente")
        return {"sub": authorization[len(_TEST_TOKEN_PREFIX) :]}

    main.app.dependency_overrides[get_current_user_jwt] = fake_jwt
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.pop(get_current_user_jwt, None)
