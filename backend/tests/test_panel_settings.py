"""Opções do painel admin que agora têm efeito, e as que saíram.

Antes, só as configurações de SMTP eram lidas; armazenamento, segurança e
recursos eram exibidos e gravados sem mudar nada no sistema.
"""

from __future__ import annotations

from typing import Any

import pytest

import main
from app.admin.models import SystemSetting
from app.admin.settings import service as settings_service
from tests.conftest import auth_header

GIF_BYTES = b"GIF89a" + b"\x00" * 200


def _set(db: Any, category: str, key: str, value: str) -> None:
    settings_service.seed_settings(db)
    settings_service.update_settings(db, [{"category": category, "key": key, "value": value}])


def test_obsolete_settings_are_removed_at_startup(db: Any) -> None:
    db.add(SystemSetting(category="security", key="max_login_attempts", value="5", value_type="number"))
    db.commit()
    settings_service.seed_settings(db)
    keys = {(s.category, s.key) for s in db.query(SystemSetting).all()}
    assert ("security", "max_login_attempts") not in keys
    assert {c for c, _ in keys} == {"smtp", "storage", "features"}


def test_youtube_import_can_be_switched_off(client: Any, db: Any, make_user: Any) -> None:
    from app.billing.service import get_balance

    _set(db, "features", "allow_youtube_import", "false")
    user = make_user(credits=20)
    response = client.post("/videos/youtube", json={"url": "https://youtu.be/abc"}, headers=auth_header(user))
    assert response.status_code == 403
    db.expire_all()
    assert get_balance(db, user.id) == 20


def test_gif_generation_can_be_switched_off(
    client: Any, db: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main._app_settings, "gemini_api_key", "fake-key-for-tests")
    _set(db, "features", "enable_gif_generation", "false")
    response = client.post(
        "/describe-gif",
        files={"file": ("p.gif", GIF_BYTES, "image/gif")},
        headers=auth_header(make_user(credits=5)),
    )
    assert response.status_code == 403


def test_step_limit_applies_before_the_ai(
    client: Any, db: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main._app_settings, "gemini_api_key", "fake-key-for-tests")
    _set(db, "features", "max_steps_per_document", "2")
    user = make_user(credits=20)
    steps = [{"description": f"Passo {i}", "has_image": False} for i in range(3)]
    response = client.post("/generate-documentation", json={"steps": steps}, headers=auth_header(user))
    assert response.status_code == 400
    assert "limite é 2" in response.json()["detail"]


@pytest.mark.parametrize("where", ["panel", "user"])
def test_video_size_limit_from_panel_or_user(
    client: Any, db: Any, make_user: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    tiny_gb = "0.00000005"  # ~53 bytes
    if where == "panel":
        _set(db, "storage", "max_video_size_gb", tiny_gb)
        user = make_user(credits=20)
    else:
        user = make_user(credits=20, max_video_size_gb=float(tiny_gb))
    response = client.post(
        "/videos/raw", content=b"\x00" * 200, headers={**auth_header(user), "X-Filename": "a.mp4"}
    )
    assert response.status_code == 413
    assert "backend/.env" not in response.json()["detail"]
