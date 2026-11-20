"""Ownership, signed file URLs and retention of uploaded videos.

Video files live in DATA_DIR. Who owns each one is kept in the database
(``video_assets``), so access checks survive restarts and the retention
policy can be applied per user instead of to the whole server.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.admin.models import VideoAsset
from app.core.config import settings
from app.database import SessionLocal

# Video ids are uuid4().hex; anything else is rejected before touching the
# database or building a file path from it.
_VIDEO_ID_RE = re.compile(r"[0-9a-f]{32}")

# How long a signed file URL stays valid. The <video> element cannot send an
# Authorization header, so the URL itself carries a short-lived proof of
# ownership instead.
FILE_URL_TTL_SECONDS = 6 * 3600


def is_valid_video_id(video_id: str) -> bool:
    return bool(_VIDEO_ID_RE.fullmatch(video_id or ""))


def register_video(video_id: str, owner_id: str, file_name: str) -> None:
    with SessionLocal() as db:
        db.add(VideoAsset(id=video_id, owner_id=owner_id, file_name=file_name))
        db.commit()


def get_owner(video_id: str) -> str | None:
    if not is_valid_video_id(video_id):
        return None
    with SessionLocal() as db:
        return db.scalar(select(VideoAsset.owner_id).where(VideoAsset.id == video_id))


def _signature(video_id: str, owner_id: str, expires: int) -> str:
    message = f"video-file:{video_id}:{owner_id}:{expires}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def sign_file_token(video_id: str, owner_id: str, now: float | None = None) -> str:
    """Token for GET /videos/{id}/file, bound to the video and its owner."""
    expires = int((now if now is not None else time.time()) + FILE_URL_TTL_SECONDS)
    return f"{expires}.{_signature(video_id, owner_id, expires)}"


def verify_file_token(video_id: str, token: str, now: float | None = None) -> bool:
    owner = get_owner(video_id)
    if not owner or not token:
        return False
    expires_raw, _, signature = token.partition(".")
    try:
        expires = int(expires_raw)
    except ValueError:
        return False
    if expires < (now if now is not None else time.time()):
        return False
    return hmac.compare_digest(signature, _signature(video_id, owner, expires))


def videos_to_expire(
    max_age_hours: int, max_per_user: int, now: datetime | None = None
) -> list[tuple[str, str]]:
    """(id, file_name) of videos older than the window or beyond each user's newest N."""
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=max_age_hours)
    with SessionLocal() as db:
        rows = db.execute(
            select(
                VideoAsset.id, VideoAsset.file_name, VideoAsset.owner_id, VideoAsset.created_at
            ).order_by(VideoAsset.owner_id, VideoAsset.created_at.desc())
        ).all()

    expired: list[tuple[str, str]] = []
    kept_per_owner: dict[str, int] = {}
    for video_id, file_name, owner_id, created_at in rows:
        kept_per_owner[owner_id] = kept_per_owner.get(owner_id, 0) + 1
        if created_at < cutoff or kept_per_owner[owner_id] > max_per_user:
            expired.append((video_id, file_name))
    return expired


def known_video_ids() -> set[str]:
    with SessionLocal() as db:
        return set(db.scalars(select(VideoAsset.id)))


def forget_videos(video_ids: list[str]) -> None:
    if not video_ids:
        return
    with SessionLocal() as db:
        db.execute(delete(VideoAsset).where(VideoAsset.id.in_(video_ids)))
        db.commit()
