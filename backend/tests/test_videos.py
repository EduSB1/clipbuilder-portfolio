"""Posse, URL assinada, upload em partes e retenção dos vídeos.

Antes: os vídeos viviam num dict global sem dono, /file e /status não pediam
login, X-Chunk-Index sem limite travava o event loop, partes abandonadas
nunca eram apagadas, e a retenção global de 5 vídeos apagava o vídeo de um
usuário quando outros subiam os seus.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import main
from app.admin.models import VideoAsset
from app.services import video_store
from tests.conftest import auth_header

VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    main._videos.clear()
    main._uploads.clear()
    yield tmp_path
    main._videos.clear()
    main._uploads.clear()


def _upload(client: Any, user: Any) -> str:
    response = client.post(
        "/videos/raw",
        content=VIDEO_BYTES,
        headers={**auth_header(user), "X-Filename": "tela.mp4"},
    )
    assert response.status_code == 200, response.text
    return response.json()["video_id"]


def _chunk(client: Any, user: Any, upload_id: str, index: int, total: int, body: bytes = b"x") -> Any:
    return client.post(
        "/videos/raw",
        content=body,
        headers={
            **auth_header(user),
            "X-Filename": "tela.mp4",
            "X-Upload-Id": upload_id,
            "X-Chunk-Index": str(index),
            "X-Total-Chunks": str(total),
        },
    )


class TestOwnership:
    def test_owner_sees_status_with_signed_url(self, client: Any, make_user: Any) -> None:
        owner = make_user(credits=20)
        video_id = _upload(client, owner)
        response = client.get(f"/videos/{video_id}/status", headers=auth_header(owner))
        assert response.status_code == 200
        assert response.json()["file_url"].startswith(f"/videos/{video_id}/file?token=")

    def test_other_user_gets_404_on_every_video_route(self, client: Any, db: Any, make_user: Any) -> None:
        owner, intruder = make_user(credits=20), make_user(credits=20)
        video_id = _upload(client, owner)
        headers = auth_header(intruder)
        assert client.get(f"/videos/{video_id}/status", headers=headers).status_code == 404
        assert client.get(f"/videos/{video_id}/smart-text?t=1", headers=headers).status_code == 404
        from app.billing.service import get_balance

        db.expire_all()
        assert get_balance(db, intruder.id) == 20


class TestSignedFileUrl:
    def test_signed_url_serves_the_file_without_auth_header(self, client: Any, make_user: Any) -> None:
        owner = make_user(credits=20)
        video_id = _upload(client, owner)
        file_url = client.get(f"/videos/{video_id}/status", headers=auth_header(owner)).json()["file_url"]
        response = client.get(file_url)
        assert response.status_code == 200
        assert response.content == VIDEO_BYTES

    @pytest.mark.parametrize("token", ["", "garbage", "9999999999.deadbeef", "abc.def"])
    def test_missing_or_forged_token_is_refused(self, client: Any, make_user: Any, token: str) -> None:
        video_id = _upload(client, make_user(credits=20))
        assert client.get(f"/videos/{video_id}/file?token={token}").status_code == 404

    def test_token_of_another_video_is_refused(self, client: Any, make_user: Any) -> None:
        owner = make_user(credits=20)
        first, second = _upload(client, owner), _upload(client, owner)
        token = video_store.sign_file_token(first, owner.id)
        assert client.get(f"/videos/{second}/file?token={token}").status_code == 404

    def test_expired_token_is_refused(self, client: Any, make_user: Any) -> None:
        owner = make_user(credits=20)
        video_id = _upload(client, owner)
        old = time.time() - video_store.FILE_URL_TTL_SECONDS - 60
        token = video_store.sign_file_token(video_id, owner.id, now=old)
        assert client.get(f"/videos/{video_id}/file?token={token}").status_code == 404


class TestChunkedUpload:
    def test_parts_are_merged_into_one_video(self, client: Any, make_user: Any, isolated_storage: Path) -> None:
        owner = make_user(credits=20)
        upload_id = str(uuid.uuid4())
        assert _chunk(client, owner, upload_id, 0, 2, b"AAA").json() == {"status": "uploading", "chunk_index": 0}
        done = _chunk(client, owner, upload_id, 1, 2, b"BBB").json()
        assert done["status"] == "ready"
        assert (isolated_storage / f"video_{done['video_id']}.mp4").read_bytes() == b"AAABBB"
        assert not list(isolated_storage.glob("upload_*.part"))

    def test_retried_first_chunk_is_charged_once(self, client: Any, db: Any, make_user: Any) -> None:
        # O frontend reenvia uma parte quando a resposta se perde na rede.
        from app.billing.service import get_balance

        owner = make_user(credits=20)
        upload_id = str(uuid.uuid4())
        assert _chunk(client, owner, upload_id, 0, 2, b"AAA").status_code == 200
        assert _chunk(client, owner, upload_id, 0, 2, b"AAA").status_code == 200
        assert _chunk(client, owner, upload_id, 1, 2, b"BBB").json()["status"] == "ready"
        db.expire_all()
        assert get_balance(db, owner.id) == 15

    def test_first_chunk_without_credits_leaves_no_upload_behind(self, client: Any, make_user: Any) -> None:
        owner = make_user(credits=0)
        upload_id = str(uuid.uuid4())
        assert _chunk(client, owner, upload_id, 0, 2).status_code == 402
        assert upload_id not in main._uploads

    def test_another_user_cannot_add_parts(self, client: Any, make_user: Any) -> None:
        owner, intruder = make_user(credits=20), make_user(credits=20)
        upload_id = str(uuid.uuid4())
        assert _chunk(client, owner, upload_id, 0, 3).status_code == 200
        assert _chunk(client, intruder, upload_id, 1, 3).status_code == 409

    def test_part_without_first_chunk_is_refused(self, client: Any, make_user: Any) -> None:
        assert _chunk(client, make_user(credits=20), str(uuid.uuid4()), 1, 3).status_code == 409

    def test_huge_chunk_index_is_rejected_immediately(self, client: Any, make_user: Any) -> None:
        # Antes, chunk_index=10**6 bloqueava o event loop por ~6 s (medido).
        user = make_user(credits=20)
        started = time.monotonic()
        response = _chunk(client, user, str(uuid.uuid4()), 10**6, 10**9)
        assert response.status_code == 400
        assert time.monotonic() - started < 1


class TestRetention:
    def test_per_user_limit_never_touches_other_users(
        self, client: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "MAX_VIDEOS_PER_USER", 2)
        other, busy = make_user(credits=50), make_user(credits=50)
        kept = _upload(client, other)
        oldest = _upload(client, busy)
        for _ in range(2):
            _upload(client, busy)
        assert client.get(f"/videos/{oldest}/status", headers=auth_header(busy)).status_code == 404
        assert client.get(f"/videos/{kept}/status", headers=auth_header(other)).status_code == 200

    def test_old_videos_expire(self, client: Any, db: Any, make_user: Any, isolated_storage: Path) -> None:
        owner = make_user(credits=20)
        video_id = _upload(client, owner)
        db.get(VideoAsset, video_id).created_at = datetime.now(UTC) - timedelta(
            hours=main.VIDEO_RETENTION_HOURS + 1
        )
        db.commit()
        main._cleanup_videos()
        assert not (isolated_storage / f"video_{video_id}.mp4").exists()
        assert video_store.get_owner(video_id) is None

    def test_abandoned_parts_are_removed(self, db: Any, isolated_storage: Path) -> None:
        stale = isolated_storage / f"upload_{uuid.uuid4()}_0.part"
        fresh = isolated_storage / f"upload_{uuid.uuid4()}_0.part"
        stale.write_bytes(b"x")
        fresh.write_bytes(b"x")
        old = time.time() - main.UPLOAD_PART_MAX_AGE_SECONDS - 60
        os.utime(stale, (old, old))
        main._cleanup_videos()
        assert not stale.exists()
        assert fresh.exists()
