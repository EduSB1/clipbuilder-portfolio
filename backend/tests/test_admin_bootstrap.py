"""Primeiro admin de uma instalação nova e promoções de papel.

Antes: o banco nascia sem usuários e ninguém conseguia entrar (seed_admin
existia, mas nunca era chamado); ADMIN_EMAIL tinha como padrão um domínio
.com de terceiros; e a sincronização com o Clerk reativava e promovia a conta
de ADMIN_EMAIL a cada evento, desfazendo uma desativação feita no painel.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from app.admin.bootstrap import bootstrap_admin
from app.admin.models import User
from app.core.config import settings

STRONG = "senha-de-admin-forte"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "admin.py"


def _admins(db: Any) -> list[User]:
    db.expire_all()
    return db.query(User).filter(User.role == "admin").all()


def test_fresh_database_gets_an_active_admin_with_local_password(db: Any) -> None:
    outcome = bootstrap_admin(db, "Dono@Example.com", STRONG)
    assert outcome == "created admin dono@example.com"
    [admin] = _admins(db)
    assert admin.email == "dono@example.com" and admin.is_active and admin.password_hash


def test_fresh_install_can_sign_in_with_the_emergency_login(
    client: Any, db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.auth import local_router
    from app.core.limiter import limiter

    monkeypatch.setattr(settings, "local_jwt_secret", "x" * 40)
    monkeypatch.setattr(local_router, "LOGIN_ANTI_ENUMERATION_DELAY_SECONDS", 0)
    monkeypatch.setattr(limiter, "enabled", False)
    bootstrap_admin(db, "dono@example.com", STRONG)
    response = client.post("/sys/token", json={"email": "dono@example.com", "password": STRONG})
    assert response.status_code == 200


def test_nothing_happens_once_an_active_admin_exists(db: Any, make_user: Any) -> None:
    existing = make_user(role="admin")
    outcome = bootstrap_admin(db, "outro@example.com", STRONG)
    assert outcome.startswith("skipped")
    assert [a.id for a in _admins(db)] == [existing.id]


def test_restart_does_not_undo_a_deactivation(db: Any, make_user: Any) -> None:
    make_user(role="admin")  # outro admin continua ativo
    bootstrap_admin(db, "dono@example.com", STRONG)
    deactivated = make_user(role="admin")
    deactivated.email, deactivated.is_active = "dono@example.com", False
    db.commit()
    bootstrap_admin(db, "dono@example.com", STRONG)
    db.refresh(deactivated)
    assert deactivated.is_active is False


def test_short_password_is_not_stored(db: Any) -> None:
    bootstrap_admin(db, "dono@example.com", "curta")
    [admin] = _admins(db)
    assert admin.is_active and admin.password_hash is None


def test_empty_admin_email_creates_nobody(db: Any) -> None:
    assert bootstrap_admin(db, "", STRONG) == "skipped: ADMIN_EMAIL is empty"
    assert _admins(db) == []


class TestClerkSync:
    def test_verified_admin_email_links_to_the_bootstrapped_admin(self, db: Any) -> None:
        from app.auth.clerk_store import upsert_user

        bootstrap_admin(db, "dono@example.com", STRONG)
        user = upsert_user(db, clerk_id="user_dono", email="dono@example.com")
        assert user.role == "admin" and user.clerk_id == "user_dono"

    def test_new_clerk_account_with_admin_email_is_not_promoted(
        self, db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.auth.clerk_store import upsert_user

        monkeypatch.setattr(settings, "admin_email", "dono@example.com")
        user = upsert_user(db, clerk_id="user_x", email="dono@example.com")
        assert user.role == "user" and user.is_active is False

    def test_sync_does_not_reactivate_a_deactivated_admin(
        self, db: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.auth.clerk_store import upsert_user

        admin = make_user(role="admin")
        admin.is_active = False
        admin.clerk_id = "user_dono"
        db.commit()
        monkeypatch.setattr(settings, "admin_email", admin.email)
        upsert_user(db, clerk_id="user_dono", email=admin.email)
        db.refresh(admin)
        assert admin.is_active is False


@pytest.fixture
def admin_cli() -> Any:
    spec = importlib.util.spec_from_file_location("admin_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["admin_cli"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("admin_cli", None)


class TestAdminCommand:
    def test_promote_and_list(self, db: Any, make_user: Any, admin_cli: Any, capsys: Any) -> None:
        user = make_user()
        assert admin_cli.main(["promote", user.email]) == 0
        assert admin_cli.main(["list"]) == 0
        assert f"{user.email}  [ativo, sem senha local" in capsys.readouterr().out

    def test_set_password_requires_twelve_characters(
        self, db: Any, admin_cli: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bootstrap_admin(db, "dono@example.com", STRONG)
        monkeypatch.setattr(admin_cli.getpass, "getpass", lambda prompt="": "curta")
        assert admin_cli.main(["set-password", "dono@example.com"]) == 1
        monkeypatch.setattr(admin_cli.getpass, "getpass", lambda prompt="": "outra-senha-forte")
        assert admin_cli.main(["set-password", "dono@example.com"]) == 0
