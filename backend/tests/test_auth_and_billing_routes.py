"""Autenticação e cobrança das rotas de IA, vídeo e exportação.

Antes, essas rotas aceitavam requisições sem token: qualquer pessoa usava a IA
paga pela chave do servidor, e um usuário logado escapava da cobrança só
omitindo o header Authorization.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient

import main
from tests.conftest import auth_header

# (método, caminho, kwargs da requisição) de cada rota que exige usuário.
PROTECTED_ROUTES: list[tuple[str, str, dict[str, Any]]] = [
    ("GET", "/ai-keys-status", {}),
    ("POST", "/test-api-keys", {}),
    ("POST", "/videos/raw", {"content": b"x", "headers": {"X-Filename": "a.mp4"}}),
    ("POST", "/videos/youtube", {"json": {"url": "https://youtu.be/abc"}}),
    ("GET", "/videos/abc/status", {}),
    ("GET", "/videos/abc/smart-text?t=1", {}),
    ("POST", "/export", {"data": {"steps": "[]"}}),
    ("POST", "/markdown-to-pdf", {"json": {"markdown": "# a"}}),
    ("POST", "/markdown-to-html", {"json": {"markdown": "# a"}}),
    ("POST", "/describe-gif", {"files": {"file": ("a.gif", b"GIF89a", "image/gif")}}),
    ("POST", "/format-and-export", {"data": {"markdown": "# a"}}),
    ("POST", "/generate-documentation", {"json": {"steps": []}}),
    ("POST", "/enhance-document", {"json": {"steps": []}}),
]

GIF_BYTES = b"GIF89a" + b"\x00" * 200


@pytest.mark.parametrize(("method", "path", "kwargs"), PROTECTED_ROUTES)
def test_route_rejects_anonymous_request(method: str, path: str, kwargs: dict[str, Any]) -> None:
    anonymous = TestClient(main.app)
    response = anonymous.request(method, path, **kwargs)
    assert response.status_code == 401, response.text


def _balance(db: Any, user: Any) -> int:
    from app.billing.service import get_balance

    db.expire_all()
    return get_balance(db, user.id)


@pytest.fixture
def fake_gemini(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Chave de servidor fictícia e um Gemini falso que registra as chamadas."""
    calls: list[str] = []

    def describe(**kwargs: Any) -> str:
        calls.append("describe-gif")
        return "Passo descrito"

    monkeypatch.setattr(main._app_settings, "gemini_api_key", "fake-key-for-tests")
    monkeypatch.setattr(main, "_describe_gif_with_gemini", describe)
    return calls


def _post_gif(client: Any, user: Any) -> Any:
    return client.post(
        "/describe-gif",
        files={"file": ("passo.gif", GIF_BYTES, "image/gif")},
        headers=auth_header(user),
    )


def test_inactive_user_is_blocked(client: Any, db: Any, make_user: Any) -> None:
    user = make_user(credits=10)
    user.is_active = False
    db.commit()
    assert client.get("/ai-keys-status", headers=auth_header(user)).status_code == 403


def test_ai_route_charges_one_credit(client: Any, db: Any, make_user: Any, fake_gemini: list[str]) -> None:
    user = make_user(credits=10)
    response = _post_gif(client, user)
    assert response.status_code == 200, response.text
    assert fake_gemini == ["describe-gif"]
    assert _balance(db, user) == 9


def test_ai_route_without_gemini_permission_is_forbidden(
    client: Any, db: Any, make_user: Any, fake_gemini: list[str]
) -> None:
    user = make_user(credits=10, can_use_gemini=False)
    assert _post_gif(client, user).status_code == 403
    assert fake_gemini == []
    assert _balance(db, user) == 10


def test_insufficient_credits_returns_402_without_calling_ai(
    client: Any, db: Any, make_user: Any, fake_gemini: list[str]
) -> None:
    user = make_user(credits=0)
    assert _post_gif(client, user).status_code == 402
    assert fake_gemini == []


def test_invalid_request_is_not_charged(client: Any, db: Any, make_user: Any, fake_gemini: list[str]) -> None:
    user = make_user(credits=10)
    response = client.post(
        "/describe-gif",
        files={"file": ("passo.png", GIF_BYTES, "image/png")},
        headers=auth_header(user),
    )
    assert response.status_code == 400
    assert _balance(db, user) == 10


def test_ai_failure_refunds_the_charge(
    client: Any, db: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(**kwargs: Any) -> str:
        raise RuntimeError("Gemini fora do ar")

    monkeypatch.setattr(main._app_settings, "gemini_api_key", "fake-key-for-tests")
    monkeypatch.setattr(main, "_describe_gif_with_gemini", broken)
    user = make_user(credits=10)
    assert _post_gif(client, user).status_code == 500
    assert _balance(db, user) == 10


def test_admin_is_not_charged(client: Any, db: Any, make_user: Any, fake_gemini: list[str]) -> None:
    admin = make_user(role="admin", credits=0)
    assert _post_gif(client, admin).status_code == 200
    assert _balance(db, admin) == 0


def test_smart_text_for_unknown_video_is_not_charged(
    client: Any, db: Any, make_user: Any, fake_gemini: list[str]
) -> None:
    user = make_user(credits=10)
    response = client.get("/videos/naoexiste/smart-text?t=1", headers=auth_header(user))
    assert response.status_code == 404
    assert _balance(db, user) == 10


def test_raw_upload_with_invalid_extension_is_not_charged(client: Any, db: Any, make_user: Any) -> None:
    user = make_user(credits=10)
    response = client.post(
        "/videos/raw",
        content=b"x" * 10,
        headers={**auth_header(user), "X-Filename": "arquivo.txt"},
    )
    assert response.status_code == 400
    assert _balance(db, user) == 10


def test_multipart_upload_route_no_longer_exists() -> None:
    # O frontend só usa /videos/raw (streaming). A rota multipart era um
    # segundo caminho de upload de até 6 GiB que ninguém usava.
    response = TestClient(main.app).post(
        "/videos", files={"video": ("tela.mp4", io.BytesIO(b"\x00" * 64), "video/mp4")}
    )
    assert response.status_code in (404, 405)
