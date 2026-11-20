"""Importação do YouTube: só YouTube, sem vazar o proxy, sem monopolizar o servidor.

Nada aqui acessa a rede: o download e o subprocesso do yt-dlp são falsos.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import main
from tests.conftest import auth_header


@pytest.mark.parametrize(
    ("url", "accepted"),
    [
        ("https://www.youtube.com/watch?v=abc", True),
        ("https://youtu.be/abc", True),
        ("https://m.youtube.com/watch?v=abc", True),
        ("https://music.youtube.com/watch?v=abc", True),
        ("https://user:senha@youtube.com/watch?v=abc", False),
        ("https://evil.example@m.youtube.com/watch?v=abc", False),
        ("https://youtube.com.evil.example/watch?v=abc", False),
        ("https://evil.example/youtube.com", False),
        ("ftp://youtube.com/watch?v=abc", False),
        ("file:///etc/passwd", False),
    ],
)
def test_only_youtube_urls_are_accepted(url: str, accepted: bool) -> None:
    assert main._is_supported_youtube_url(url) is accepted


def test_command_restricts_extractor_and_ends_options_before_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []
    out = tmp_path / "video.mp4"

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        out.write_bytes(b"\x00" * 32)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(main, "_ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(main, "_run_ytdlp", fake_run)
    url = "https://youtu.be/abc"
    main._download_youtube_video(url=url, out_path=out)

    cmd = commands[0]
    assert cmd[cmd.index("--use-extractors") + 1] == "youtube"
    assert cmd[-2:] == ["--", url]


def test_proxy_credentials_never_reach_logs_or_users() -> None:
    cmd = ["yt-dlp", "--proxy", "http://joao:s3nh4@proxy.example:8080", "--", "https://youtu.be/a"]
    assert "s3nh4" not in " ".join(main._redact_ytdlp_cmd(cmd))
    error = "ERROR: Unable to connect to proxy http://joao:s3nh4@proxy.example:8080/"
    assert main._redact_url_credentials(error) == (
        "ERROR: Unable to connect to proxy http://***@proxy.example:8080/"
    )


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    main._videos.clear()
    main._youtube_active.clear()
    yield tmp_path
    main._videos.clear()
    main._youtube_active.clear()


def _import(client: Any, user: Any) -> Any:
    return client.post(
        "/videos/youtube", json={"url": "https://youtu.be/abc"}, headers=auth_header(user)
    )


def test_second_simultaneous_import_is_refused_without_charge(
    client: Any, db: Any, make_user: Any, storage: Path
) -> None:
    from app.billing.service import get_balance

    user = make_user(credits=20)
    main._youtube_active[user.id] = 1  # uma importação já em andamento
    assert _import(client, user).status_code == 429
    db.expire_all()
    assert get_balance(db, user.id) == 20


def test_finished_import_releases_the_slot(
    client: Any, make_user: Any, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        main, "_download_youtube_video", lambda *, url, out_path: out_path.write_bytes(b"\x00")
    )
    user = make_user(credits=20)
    video_id = _import(client, user).json()["video_id"]
    assert main._youtube_active == {}
    status = client.get(f"/videos/{video_id}/status", headers=auth_header(user)).json()
    assert status["status"] == "ready"


def test_failed_import_refunds_hides_details_and_releases_slot(
    client: Any, db: Any, make_user: Any, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.billing.service import get_balance

    def broken(*, url: str, out_path: Path) -> None:
        raise RuntimeError("yt-dlp failed: proxy http://***@10.0.0.5:3128 recusou")

    monkeypatch.setattr(main, "_download_youtube_video", broken)
    user = make_user(credits=20)
    video_id = _import(client, user).json()["video_id"]
    status = client.get(f"/videos/{video_id}/status", headers=auth_header(user)).json()
    assert status["status"] == "error"
    assert "10.0.0.5" not in status["error"]
    assert main._youtube_active == {}
    db.expire_all()
    assert get_balance(db, user.id) == 20
