"""Configuração de produção: o que a API revela e o que guarda em claro.

Antes: /docs e /openapi.json públicos; erros de token devolviam o motivo
(incluindo o issuer configurado); o login de emergência dizia se o e-mail
existia, se era admin, se estava ativo e se tinha senha; um LOCAL_JWT_SECRET
de qualquer tamanho valia; azp não era estrito; a senha SMTP ficava em texto
puro no banco e voltava inteira no GET; e erros inesperados ecoavam o texto
interno da exceção.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import main
from app.admin.settings import service as settings_service
from app.core.config import Settings, settings
from tests.conftest import auth_header

STRONG_SECRET = "s" * 40


def test_api_docs_are_off_by_default() -> None:
    anonymous = TestClient(main.app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert anonymous.get(path).status_code == 404, path


def test_token_errors_do_not_explain_the_failure() -> None:
    response = TestClient(main.app).get("/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Token inválido"


def test_azp_is_strict_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLERK_AZP_STRICT", raising=False)
    assert Settings().clerk_azp_strict is True


class TestEmergencyLogin:
    @pytest.fixture(autouse=True)
    def enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.auth import local_router
        from app.core.limiter import limiter

        monkeypatch.setattr(settings, "local_jwt_secret", STRONG_SECRET)
        monkeypatch.setattr(local_router, "LOGIN_ANTI_ENUMERATION_DELAY_SECONDS", 0)
        monkeypatch.setattr(limiter, "enabled", False)

    @staticmethod
    def _login(client: Any, email: str, password: str) -> Any:
        return client.post("/sys/token", json={"email": email, "password": password})

    def _user(self, db: Any, role: str, password: str | None, active: bool = True) -> Any:
        from app.admin.crud import create_user

        user = create_user(db, email=f"{role}-{active}-{bool(password)}@example.com", role=role, password=password)
        user.is_active = active
        db.commit()
        return user

    def test_every_failure_looks_the_same(self, client: Any, db: Any) -> None:
        no_password = self._user(db, "admin", None)
        regular = self._user(db, "user", "senha-certa")
        inactive = self._user(db, "admin", "senha-certa", active=False)
        admin = self._user(db, "admin", "senha-certa")
        attempts = [
            ("ninguem@example.com", "x"),
            (no_password.email, "x"),
            (regular.email, "senha-certa"),
            (inactive.email, "senha-certa"),
            (admin.email, "senha-errada"),
        ]
        for email, password in attempts:
            response = self._login(client, email, password)
            assert (response.status_code, response.json()) == (401, {"detail": "Credenciais inválidas"}), email

    def test_admin_with_right_password_gets_a_token(self, client: Any, db: Any) -> None:
        admin = self._user(db, "admin", "senha-certa")
        response = self._login(client, admin.email, "senha-certa")
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_short_secret_disables_login_and_tokens(
        self, client: Any, db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.auth.local_jwt import create_local_token, verify_local_token

        admin = self._user(db, "admin", "senha-certa")
        token = create_local_token(user_id=admin.id, email=admin.email, role="admin")
        monkeypatch.setattr(settings, "local_jwt_secret", "curto")
        assert self._login(client, admin.email, "senha-certa").status_code == 404
        with pytest.raises(ValueError):
            verify_local_token(token)


class TestSmtpPassword:
    def test_stored_encrypted_and_masked(self, db: Any) -> None:
        from app.admin.models import SystemSetting

        settings_service.seed_settings(db)
        settings_service.update_settings(db, [{"category": "smtp", "key": "password", "value": "senha-smtp"}])
        row = db.query(SystemSetting).filter_by(category="smtp", key="password").one()
        assert row.is_encrypted and "senha-smtp" not in row.value
        listed = {s["key"]: s["value"] for s in settings_service.get_settings_by_category(db, "smtp")}
        assert listed["password"] == settings_service.SECRET_MASK
        assert settings_service.get_setting_value("smtp", "password") == "senha-smtp"

    def test_echoed_mask_keeps_the_password(self, db: Any) -> None:
        settings_service.seed_settings(db)
        settings_service.update_settings(db, [{"category": "smtp", "key": "password", "value": "senha-smtp"}])
        settings_service.update_settings(
            db, [{"category": "smtp", "key": "password", "value": settings_service.SECRET_MASK}]
        )
        assert settings_service.get_setting_value("smtp", "password") == "senha-smtp"

    def test_plaintext_from_before_is_encrypted_at_startup(self, db: Any) -> None:
        from app.admin.models import SystemSetting

        settings_service.seed_settings(db)
        row = db.query(SystemSetting).filter_by(category="smtp", key="password").one()
        row.value, row.is_encrypted = "antiga-em-claro", False
        db.commit()
        settings_service.encrypt_plaintext_secrets(db)
        db.refresh(row)
        assert row.is_encrypted and "antiga-em-claro" not in row.value
        assert settings_service.get_setting_value("smtp", "password") == "antiga-em-claro"

    def test_admin_panel_never_receives_it(self, client: Any, db: Any, make_user: Any) -> None:
        settings_service.seed_settings(db)
        settings_service.update_settings(db, [{"category": "smtp", "key": "password", "value": "senha-smtp"}])
        response = client.get("/admin/settings", params={"category": "smtp"}, headers=auth_header(make_user(role="admin")))
        assert "senha-smtp" not in response.text


def test_unexpected_errors_do_not_echo_internals(
    client: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.export_from_markdown as export

    def broken(*args: Any, **kwargs: Any) -> str:
        raise Exception("conexão com 10.0.0.9 recusada; segredo interno")

    monkeypatch.setattr(export, "markdown_to_html", broken)
    response = client.post("/markdown-to-html", json={"markdown": "# a"}, headers=auth_header(make_user()))
    assert response.status_code == 500
    assert "segredo interno" not in response.text
