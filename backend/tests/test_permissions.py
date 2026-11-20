"""Permissões que só existiam no frontend e tools globais abertas a qualquer usuário.

Antes: qualquer usuário logado ligava e desligava tools para todos, lia os
logs delas (com conteúdo de outros clientes) e rodava IA de graça pelo
/api/tools/run; as flags can_export_* não eram checadas no backend; e o
parâmetro `model` escolhia qualquer modelo pago pela chave do servidor.
"""

from __future__ import annotations

from typing import Any

import pytest

import main
from app.admin.models import AiTool
from tests.conftest import auth_header

GIF_BYTES = b"GIF89a" + b"\x00" * 200


@pytest.fixture
def tool_id(db: Any) -> str:
    from app.tools.service import seed_native_tools

    seed_native_tools(db)
    return db.query(AiTool).first().id


class TestToolsAreAdminOnly:
    def test_regular_user_cannot_toggle_read_logs_or_run(
        self, client: Any, make_user: Any, tool_id: str
    ) -> None:
        headers = auth_header(make_user())
        assert client.patch(f"/api/tools/{tool_id}/toggle", json={"is_active": False}, headers=headers).status_code == 403
        assert client.get(f"/api/tools/{tool_id}/logs", headers=headers).status_code == 403
        assert client.post("/api/tools/run/manual", json={}, headers=headers).status_code == 403

    def test_admin_can_toggle(self, client: Any, make_user: Any, tool_id: str) -> None:
        response = client.patch(
            f"/api/tools/{tool_id}/toggle", json={"is_active": False}, headers=auth_header(make_user(role="admin"))
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False


class TestExportPermissions:
    @pytest.mark.parametrize(
        ("path", "flag"),
        [("/markdown-to-pdf", "can_export_pdf"), ("/markdown-to-html", "can_export_html"), ("/markdown-to-docx", "can_export_docx")],
    )
    def test_endpoint_respects_flag(self, client: Any, make_user: Any, path: str, flag: str) -> None:
        user = make_user(**{flag: False})
        response = client.post(path, json={"markdown": "# Guia"}, headers=auth_header(user))
        assert response.status_code == 403

    def test_export_route_checks_the_requested_format(self, client: Any, make_user: Any) -> None:
        user = make_user(can_export_pdf=False)
        response = client.post(
            "/export", data={"steps": "[]", "output_format": "pdf"}, headers=auth_header(user)
        )
        assert response.status_code == 403

    def test_allowed_format_still_works(self, client: Any, make_user: Any) -> None:
        user = make_user(can_export_html=True)
        response = client.post("/markdown-to-html", json={"markdown": "# Guia"}, headers=auth_header(user))
        assert response.status_code == 200

    def test_admin_is_never_blocked(self, client: Any, make_user: Any) -> None:
        admin = make_user(role="admin", can_export_html=False)
        response = client.post("/markdown-to-html", json={"markdown": "# Guia"}, headers=auth_header(admin))
        assert response.status_code == 200


class TestModelChoice:
    def test_regular_user_falls_back_to_default_model(self) -> None:
        assert main._resolve_model("models/gemini-2.5-pro", {"role": "user"}) == main.DEFAULT_GEMINI_MODEL

    def test_admin_may_choose(self) -> None:
        assert main._resolve_model("models/gemini-2.5-pro", {"role": "admin"}) == "models/gemini-2.5-pro"

    def test_allowlist_can_be_extended(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLIPBUILDER_ALLOWED_GEMINI_MODELS", "models/gemini-2.5-pro")
        assert main._resolve_model("models/gemini-2.5-pro", {"role": "user"}) == "models/gemini-2.5-pro"

    def test_route_passes_the_resolved_model_to_the_ai(
        self, client: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def describe(**kwargs: Any) -> str:
            seen.update(kwargs)
            return "ok"

        monkeypatch.setattr(main._app_settings, "gemini_api_key", "fake-key-for-tests")
        monkeypatch.setattr(main, "_describe_gif_with_gemini", describe)
        user = make_user(credits=5)
        response = client.post(
            "/describe-gif",
            files={"file": ("p.gif", GIF_BYTES, "image/gif")},
            data={"model": "models/gemini-2.5-pro"},
            headers=auth_header(user),
        )
        assert response.status_code == 200
        assert seen["model"] == main.DEFAULT_GEMINI_MODEL
