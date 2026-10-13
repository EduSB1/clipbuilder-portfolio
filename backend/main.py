from __future__ import annotations

import functools
import io
import json
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass, field
from errno import ENOSPC
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import anyio

# Carregar configurações e injetar chaves no ambiente antes de outros imports
from app.core.config import settings as _app_settings

try:
    from agents.router import router as agents_router
except Exception as _agents_import_err:
    agents_router = None
    logging.getLogger("clipbuilder").warning(
        "Agents module unavailable (pydantic-ai not installed?): %s — "
        "the /agents/* endpoints will be disabled but everything else works.",
        _agents_import_err,
    )
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.admin.router import router as admin_router
from app.admin.usage_logger import log_ai_usage_background
from app.auth.deps import (
    CurrentAuthorizedUser,
    get_current_user_jwt,
)
from app.auth.store import get_user_by_id
from app.auth.webhook import router as clerk_webhook_router
from app.billing.router import router as billing_router
from app.core.constants import (
    AUDIO_BITRATE_KBPS,
    AUDIO_EXTRACTION_WINDOW_SECONDS,
    DEFAULT_FRAME_COUNT,
    DEFAULT_GEMINI_CLIP_SECONDS,
    DEFAULT_GEMINI_PROXY_HEIGHT,
    DEFAULT_MAX_DATA_FILES,
    DEFAULT_MAX_VIDEO_MB,
    FRAME_EXTRACTION_WINDOW_SECONDS,
    GEMINI_POLL_INTERVAL_SECONDS,
    GEMINI_POLL_TIMEOUT_SECONDS,
    GIF_FRAME_COUNT,
    LOG_ERROR_BACKUP_COUNT,
    LOG_ERROR_FILE_MAX_BYTES,
    LOG_FILE_MAX_BYTES,
    LOG_INFO_BACKUP_COUNT,
    MAX_GIF_BYTES_MB,
    MAX_RETRY_SLEEP_SECONDS,
    MAX_SINGLE_IMAGE_BYTES_MB,
    MAX_TOTAL_IMAGE_BYTES_MB,
    MIN_AUDIO_FILE_SIZE_BYTES,
    MIN_CLIP_DURATION_SECONDS,
    MIN_FRAME_SCALE_HEIGHT,
    TIMESTAMP_ANALYSIS_WINDOW_SECONDS,
    UPLOAD_CHUNK_SIZE_KB,
    VIDEO_ENCODE_CRF,
    WHISPER_SAMPLE_RATE_HZ,
    YTDLP_DEFAULT_TIMEOUT_SECONDS,
)
from app.database import get_db
from app.tools.router import router as tools_router

try:
    from dotenv import load_dotenv

    _dotenv_path = Path(__file__).resolve().parent / ".env"
    if _dotenv_path.exists():
        load_dotenv(dotenv_path=_dotenv_path)
    else:
        load_dotenv()
except Exception:
    pass


LOG_DIR = Path(
    os.getenv("CLIPBUILDER_LOG_DIR", Path(__file__).resolve().parent / "logs")
)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("clipbuilder")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    info_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "clipbuilder.log",
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_INFO_BACKUP_COUNT,
        encoding="utf-8",
    )
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(fmt)

    error_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "clipbuilder.error.log",
        maxBytes=LOG_ERROR_FILE_MAX_BYTES,
        backupCount=LOG_ERROR_BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)

    logger.addHandler(info_handler)
    logger.addHandler(error_handler)


def _http_exception_handler(_request: Request, exc: StarletteHTTPException):
    # Starlette hides multipart errors behind a generic message; return actionable hint.
    if (
        exc.status_code == 400
        and str(exc.detail) == "There was an error parsing the body"
    ):
        logger.warning("multipart parse error: %s", exc.detail)
        return JSONResponse(
            status_code=400,
            content={
                "detail": (
                    "Falha ao ler o upload (multipart). Isso costuma acontecer com vídeos grandes por limite do parser. "
                    "Use o upload raw (endpoint /videos/raw) no frontend/backend atualizados."
                )
            },
        )

    if exc.status_code >= 500:
        logger.error("http error %s: %s", exc.status_code, exc.detail, exc_info=True)
    elif exc.status_code >= 400:
        logger.warning("http %s: %s", exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def _unhandled_exception_handler(_request: Request, exc: Exception):
    logger.error("unhandled error: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Erro interno no servidor"})


MAX_TOTAL_IMAGE_BYTES = MAX_TOTAL_IMAGE_BYTES_MB * 1024 * 1024
MAX_SINGLE_IMAGE_BYTES = MAX_SINGLE_IMAGE_BYTES_MB * 1024 * 1024
MAX_GIF_BYTES = MAX_GIF_BYTES_MB * 1024 * 1024


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


MAX_VIDEO_BYTES = _env_int(
    "CLIPBUILDER_MAX_VIDEO_BYTES", DEFAULT_MAX_VIDEO_MB * 1024 * 1024
)  # default 700MB
MAX_VIDEO_MB = max(1, int(MAX_VIDEO_BYTES / (1024 * 1024)))

logger.info(
    "config: CLIPBUILDER_MAX_VIDEO_BYTES=%s (~%s MB)", MAX_VIDEO_BYTES, MAX_VIDEO_MB
)

GEMINI_CLIP_SECONDS = _env_int("CLIPBUILDER_GEMINI_CLIP_SECONDS", DEFAULT_GEMINI_CLIP_SECONDS)
GEMINI_PROXY_HEIGHT = _env_int("CLIPBUILDER_GEMINI_PROXY_HEIGHT", DEFAULT_GEMINI_PROXY_HEIGHT)

# Chaves e modelos agora centralizados no app.core.config.settings
DEFAULT_GEMINI_MODEL = _app_settings.gemini_model or "models/gemini-2.5-flash"
AI_LANGUAGE = (os.getenv("CLIPBUILDER_AI_LANGUAGE") or "pt-BR").strip() or "pt-BR"

# Gemini API configuration

YTDLP_COOKIES_FILE = (os.getenv("CLIPBUILDER_YTDLP_COOKIES_FILE") or "").strip()
YTDLP_COOKIES_FROM_BROWSER = (
    os.getenv("CLIPBUILDER_YTDLP_COOKIES_FROM_BROWSER") or ""
).strip()
YTDLP_COOKIES_FROM_BROWSER_ARGS = (
    os.getenv("CLIPBUILDER_YTDLP_COOKIES_FROM_BROWSER_ARGS") or ""
).strip()
# Proxy URL for yt-dlp (e.g. socks5://user:pass@host:port or http://host:port).
# Using a residential proxy is the most reliable way to avoid YouTube IP bans on VPS.
YTDLP_PROXY = (os.getenv("CLIPBUILDER_YTDLP_PROXY") or "").strip()
# PO Token extractor base URL (bgutil-ytdlp-pot-provider).
# When set, yt-dlp uses it to generate PO Tokens automatically, bypassing
# YouTube's "not a bot" check on VPS/server environments without any cookies.
# Leave empty to use the in-process extractor (default, works in most cases).
YTDLP_PO_TOKEN_EXTRACTOR_URL = (
    os.getenv("CLIPBUILDER_YTDLP_PO_TOKEN_EXTRACTOR_URL") or ""
).strip()


def _youtube_startup_diagnostic() -> None:
    """Run YouTube / yt-dlp diagnostic checks at startup and log a summary.

    Checks performed:
      1. yt-dlp installed & version
      2. Cookies file configured & exists
      3. bgutil-ytdlp-pot-provider plugin installed
      4. Proxy configured
      5. Warning if NO auth method is configured at all

    The most reliable long-term fix for VPS IP bans is configuring
    CLIPBUILDER_YTDLP_PROXY with a residential proxy.
    Providers: Bright Data, Oxylabs, Smartproxy.
    Format: http://user:pass@host:port  or  socks5://user:pass@host:port
    """
    separator = "─" * 50
    logger.info("YouTube diagnostic %s", separator)

    # 1. yt-dlp version
    ytdlp_version: str | None = None
    try:
        cmd = _ytdlp_cmd() + ["--version"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            ytdlp_version = (proc.stdout or "").strip()
            logger.info("  yt-dlp version: %s", ytdlp_version)
        else:
            logger.warning(
                "  yt-dlp --version failed (rc=%d): %s", proc.returncode, proc.stderr
            )
    except FileNotFoundError:
        logger.error("  yt-dlp is NOT installed — YouTube imports will fail!")
    except Exception as exc:
        logger.warning("  yt-dlp version check error: %s", exc)

    # 2. Cookies file
    cookies_configured = bool((YTDLP_COOKIES_FILE or "").strip())
    cookies_exists = False
    cookies_lines = 0
    if cookies_configured:
        try:
            p = Path(YTDLP_COOKIES_FILE).expanduser()
            if not p.is_absolute():
                p = (Path(__file__).resolve().parent / p).resolve()
            cookies_exists = p.exists() and p.is_file()
            if cookies_exists:
                cookies_lines = sum(
                    1 for _ in p.open(encoding="utf-8", errors="ignore")
                )
                logger.info("  Cookies file: %s (%d lines) ✓", p, cookies_lines)
            else:
                logger.warning("  Cookies file configured but NOT found at %s", p)
        except Exception as exc:
            logger.warning("  Cookies file check error: %s", exc)
    else:
        logger.info("  Cookies file: not configured")

    # 3. Browser cookies
    browser_cookies_configured = bool((YTDLP_COOKIES_FROM_BROWSER or "").strip())
    if browser_cookies_configured:
        logger.info("  Browser cookies: %s", YTDLP_COOKIES_FROM_BROWSER)
    else:
        logger.info("  Browser cookies: not configured")

    # 4. PO Token plugin (bgutil-ytdlp-pot-provider)
    pot_plugin_installed = False
    try:
        import importlib

        importlib.import_module("yt_dlp_plugins")
        pot_plugin_installed = True
        logger.info("  PO Token plugin (yt_dlp_plugins): found ✓")
    except ImportError:
        pass

    if not pot_plugin_installed:
        # Fallback: check via pip
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "show", "bgutil-ytdlp-pot-provider"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode == 0:
                pot_plugin_installed = True
                logger.info(
                    "  PO Token plugin (bgutil-ytdlp-pot-provider): installed ✓"
                )
            else:
                logger.warning(
                    "  PO Token plugin (bgutil-ytdlp-pot-provider): NOT installed"
                )
        except Exception:
            logger.warning("  PO Token plugin check: unable to verify")

    # 5. Proxy
    proxy_configured = bool((YTDLP_PROXY or "").strip())
    if proxy_configured:
        # Mask credentials in log
        masked = YTDLP_PROXY
        try:
            from urllib.parse import urlparse as _up

            _pp = _up(YTDLP_PROXY)
            if _pp.password:
                masked = YTDLP_PROXY.replace(_pp.password, "****")
        except Exception:
            pass
        logger.info("  Proxy: %s ✓", masked)
    else:
        logger.info("  Proxy: not configured")

    # PO Token extractor URL
    pot_extractor_url = bool((YTDLP_PO_TOKEN_EXTRACTOR_URL or "").strip())
    if pot_extractor_url:
        logger.info("  PO Token extractor URL: %s", YTDLP_PO_TOKEN_EXTRACTOR_URL)

    # Summary of active strategies
    strategies: list[str] = []
    if cookies_exists:
        strategies.append("cookies-file")
    if browser_cookies_configured:
        strategies.append("browser-cookies")
    if pot_plugin_installed:
        strategies.append("po-token")
    if proxy_configured:
        strategies.append("proxy")
    if strategies:
        logger.info("  Active strategies: %s", " + ".join(strategies))
    else:
        logger.warning(
            "  ⚠ NO YouTube auth strategy is configured! "
            "Downloads will likely fail with 'Sign in to confirm you're not a bot'. "
            "Recommended fix: set CLIPBUILDER_YTDLP_PROXY with a residential proxy "
            "(e.g. http://user:pass@host:port or socks5://user:pass@host:port). "
            "Providers: Bright Data, Oxylabs, Smartproxy. "
            "Alternatively, install cookies via ./setup_youtube_cookies.sh"
        )

    logger.info("YouTube diagnostic %s", separator)


async def _lifespan(app: FastAPI):
    """Startup: create DB tables. Auth is handled by Clerk."""
    try:
        from app.admin.models import (  # noqa: F401
            AiTool,
            AiToolLog,
            ApiUsageLog,
            CreditAccount,
            CreditTransaction,
            DailyMetrics,
            DocumentTemplateDef,
            SystemSetting,
            User,
            UserGroup,
            UserGroupMember,
            UserPermission,
        )
        from app.database import Base, SessionLocal, engine
        from app.services.run_migrations import run_migrations

        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured")
        try:
            run_migrations()
        except Exception as mExc:
            logger.warning("Migrations skipped: %s", mExc)

        # Seed native AI tools
        try:
            from app.tools.service import seed_native_tools

            with SessionLocal() as db:
                seed_native_tools(db)
        except Exception as tools_exc:
            logger.warning("Native AI tools seed skipped: %s", tools_exc)

        # Seed built-in document templates
        try:
            from app.admin.template_service import seed_builtin_templates

            seed_builtin_templates()
            logger.info("Built-in templates seeded")
        except Exception as tpl_exc:
            logger.warning("Template seeding skipped: %s", tpl_exc)
    except Exception as exc:
        logger.warning("DB init skipped: %s", exc)

    # ── YouTube / yt-dlp diagnostic ───────────────────────────────────
    try:
        _youtube_startup_diagnostic()
    except Exception as yt_diag_exc:
        logger.warning("YouTube startup diagnostic failed: %s", yt_diag_exc)

    yield


from app.core.limiter import limiter

app = FastAPI(title="ClipBuilder", lifespan=_lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Auth is handled by Clerk — local JWT router mounted at /sys (hidden backdoor)
from app.api.router import router as api_router
from app.auth.local_router import router as local_jwt_router

app.include_router(api_router)
app.include_router(admin_router)
app.include_router(clerk_webhook_router)
app.include_router(billing_router)
app.include_router(tools_router)
app.include_router(local_jwt_router)
if agents_router is not None:
    app.include_router(agents_router)

app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
app.add_exception_handler(Exception, _unhandled_exception_handler)


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Muitas tentativas. Aguarde alguns instantes e tente novamente."
        },
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

from app.core.config import settings as _app_settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=_app_settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Execução de trabalho bloqueante fora do event loop
# ---------------------------------------------------------------------------


# Número de conversões de documento (LibreOffice / python-docx) que podem rodar
# ao mesmo tempo.  Cada instância do LibreOffice consome centenas de MB; sem
# teto, uma rajada de exportações derruba a VPS por falta de memória.  As
# requisições excedentes esperam sua vez em vez de competir por RAM.
EXPORT_CONCURRENCY = max(1, _env_int("CLIPBUILDER_EXPORT_CONCURRENCY", 2))
_export_limiter = anyio.CapacityLimiter(EXPORT_CONCURRENCY)


async def _run_blocking(_func, /, *args, **kwargs):
    """Executa uma função síncrona pesada numa worker thread.

    Handlers declarados como ``async def`` rodam na própria thread do event
    loop.  Chamar ali dentro algo que bloqueia por segundos — LibreOffice,
    ffmpeg, python-docx, uma request HTTP síncrona ao Gemini — congela a API
    inteira para todos os usuários, porque o uvicorn sobe um único worker.

    Todo trabalho desse tipo deve passar por aqui.
    """
    return await anyio.to_thread.run_sync(functools.partial(_func, *args, **kwargs))


async def _run_export(_func, /, *args, **kwargs):
    """Como :func:`_run_blocking`, mas limitado a ``EXPORT_CONCURRENCY`` em paralelo.

    Use para geração de DOCX/PDF, que é cara em CPU e memória.  Chamadas de
    rede (Gemini) não precisam desse teto e devem usar ``_run_blocking``.
    """
    return await anyio.to_thread.run_sync(
        functools.partial(_func, *args, **kwargs), limiter=_export_limiter
    )


@dataclass
class VideoEntry:
    path: Path
    status: str  # ready|error
    clip_cache: dict[str, str] = field(default_factory=dict)  # key -> gemini_file_name
    error: str | None = None


DATA_DIR = Path(
    os.getenv("CLIPBUILDER_DATA_DIR", Path(__file__).resolve().parent / "data")
)
DATA_DIR.mkdir(parents=True, exist_ok=True)
logger.info("config: CLIPBUILDER_DATA_DIR=%s", DATA_DIR)

# Maximum number of video files to keep in DATA_DIR (oldest files are removed when exceeded)
MAX_DATA_FILES = _env_int("CLIPBUILDER_MAX_DATA_FILES", DEFAULT_MAX_DATA_FILES)
logger.info("config: CLIPBUILDER_MAX_DATA_FILES=%s", MAX_DATA_FILES)

_videos_lock = threading.Lock()
_videos: dict[str, VideoEntry] = {}


def _cleanup_old_files() -> None:
    """Remove oldest video files from DATA_DIR if count exceeds MAX_DATA_FILES.

    Files are sorted by modification time and the oldest ones are deleted
    until only MAX_DATA_FILES remain.
    """
    try:
        # Get all video files in DATA_DIR
        video_files = [
            f
            for f in DATA_DIR.iterdir()
            if f.is_file()
            and f.name.startswith("video_")
            and f.suffix.lower() in {".mp4", ".mkv"}
        ]

        if len(video_files) <= MAX_DATA_FILES:
            return

        # Sort by modification time (oldest first)
        video_files.sort(key=lambda f: f.stat().st_mtime)

        # Remove oldest files until we're at the limit
        files_to_remove = len(video_files) - MAX_DATA_FILES
        for i in range(files_to_remove):
            file_to_delete = video_files[i]
            try:
                # Also remove from in-memory cache
                video_id = file_to_delete.stem.replace("video_", "")
                with _videos_lock:
                    if video_id in _videos:
                        del _videos[video_id]

                file_to_delete.unlink()
                logger.info("cleanup: removed old video file %s", file_to_delete.name)
            except Exception as exc:
                logger.warning(
                    "cleanup: failed to remove %s: %s", file_to_delete.name, exc
                )
    except Exception as exc:
        logger.warning("cleanup: failed to clean old files: %s", exc)


def _restore_video_entry_if_missing(video_id: str) -> VideoEntry | None:
    """Restore an in-memory entry from disk after a server reload.

    We intentionally keep _videos in-memory for simplicity, but uvicorn --reload
    restarts the process, so we reconstruct entries on demand when possible.
    """
    candidates = [
        DATA_DIR / f"video_{video_id}.mp4",
        DATA_DIR / f"video_{video_id}.mkv",
    ]
    for path in candidates:
        try:
            if path.exists() and path.is_file() and path.stat().st_size > 0:
                entry = VideoEntry(path=path, status="ready")
                _videos[video_id] = entry
                return entry
        except Exception:
            continue
    return None


def _configure_genai(api_key: str) -> None:
    try:
        import google.generativeai as genai
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Dependência 'google-generativeai' não instalada no backend.",
        ) from exc

    genai.configure(api_key=api_key)


def _mask_key(key: str) -> str:
    """Retorna versão mascarada da chave para logs seguros (ex: 'AIza...xY9z')."""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def _get_user_from_authorization(authorization: str | None) -> dict | None:
    """Extract user from Authorization header without raising exceptions.

    Lookup strategy:
      1. Try get_user_by_id(sub) — works when Clerk sync mapped sub → local UUID.
      2. Fallback: try get_user_by_clerk_id(_clerk_id) — works when sync
         failed but the user already exists in DB with the given clerk_id.

    NOTE: Auto-sync (creating new DB records on the fly) has been intentionally
    removed. A user MUST exist in the local DB to be granted access. This prevents
    deleted/excluded users from regaining access by re-logging with Clerk.
    Account status is enforced: deleted or inactive users are blocked here.
    """
    if not authorization or not isinstance(authorization, str):
        return None
    raw = authorization.strip()
    if not raw.lower().startswith("bearer "):
        return None
    token = raw[7:].strip()
    if not token:
        return None
    try:
        from app.auth.store import get_user_by_clerk_id

        payload = get_current_user_jwt(authorization)
        sub = payload.get("sub", "")
        clerk_id = payload.get("_clerk_id", "")

        # 1. Primary lookup — by local UUID (set by sync step)
        user = get_user_by_id(sub) if sub else None

        # 2. Fallback — by clerk_id field
        if not user and clerk_id:
            user = get_user_by_clerk_id(clerk_id)

        # Also try sub directly as clerk_id when it looks like one (starts with 'user_')
        if not user and sub and sub.startswith("user_"):
            user = get_user_by_clerk_id(sub)

        if not user:
            return None

        # Enforce account status — deleted or inactive users are denied
        if user.get("deleted_at") is not None or not user.get("is_active", True):
            logger.warning(
                "_get_user_from_authorization: blocked inactive/deleted user id=%s",
                user.get("id"),
            )
            return None

        return user
    except Exception:
        return None


def _check_ai_permission(authorization: str | None, provider: str) -> None:
    """Check if user has permission to use the specified AI provider.

    Args:
        authorization: Authorization header value
        provider: One of 'gemini'

    Raises:
        HTTPException: 403 if user doesn't have permission
    """
    user = _get_user_from_authorization(authorization)
    if not user:
        # If no user found, allow (legacy behavior for unauthenticated endpoints)
        return

    permissions = user.get("permissions", {})
    permission_key = f"can_use_{provider}"

    if not permissions.get(permission_key, True):
        provider_names = {"gemini": "Gemini"}
        provider_name = provider_names.get(provider, provider)
        raise HTTPException(
            status_code=403,
            detail=f"Você não tem permissão para usar o {provider_name}. "
            "Entre em contato com o administrador.",
        )


def _debit_user_credits(authorization: str | None, endpoint: str) -> str | None:
    """Verify and debit credits for an AI endpoint call.

    Admins are exempt from credit requirements. If the user cannot be
    identified (e.g. unauthenticated legacy request), the call is allowed
    without debiting (graceful degradation).

    Args:
        authorization: The raw ``Authorization`` header value.
        endpoint: The endpoint path string (e.g. ``"/smart-text"``).

    Returns:
        The local ``user_id`` if credits were debited, or ``None`` if the
        user could not be resolved (no debit occurred).

    Raises:
        HTTPException: 402 if the user has insufficient credits.
    """
    from app.billing.costs import get_credit_cost
    from app.billing.service import debit_credits
    from app.database import SessionLocal

    user = _get_user_from_authorization(authorization)
    if not user:
        # Cannot identify user — allow the request (legacy / unauthenticated)
        return None

    # Admins are exempt from credit billing
    if user.get("role") == "admin":
        return user.get("id")

    user_id = user.get("id", "")
    if not user_id:
        return None

    cost = get_credit_cost(endpoint)

    with SessionLocal() as db:
        debit_credits(db, user_id=user_id, amount=cost, endpoint=endpoint)

    return user_id


def _refund_user_credits(
    user_id: str | None, endpoint: str, amount: int | None = None
) -> None:
    """Refund credits after an AI call failure.

    Called in except blocks when the AI provider fails *after* credits were
    already debited.  Silently does nothing if ``user_id`` is ``None`` or
    the user is an admin.

    Args:
        user_id: The local user UUID returned by :func:`_debit_user_credits`.
        endpoint: The endpoint path (for audit logging).
        amount: Override refund amount. If ``None``, uses the endpoint's cost.
    """
    if not user_id:
        return

    from app.billing.costs import get_credit_cost
    from app.billing.service import refund_credits
    from app.database import SessionLocal

    # Check if admin (admins were never debited)
    user = get_user_by_id(user_id)
    if user and user.get("role") == "admin":
        return

    refund_amount = amount if amount is not None else get_credit_cost(endpoint)

    try:
        with SessionLocal() as db:
            refund_credits(db, user_id=user_id, amount=refund_amount, endpoint=endpoint)
        logger.info(
            "Refunded %d credits to user %s (endpoint=%s)",
            refund_amount,
            user_id,
            endpoint,
        )
    except Exception as exc:
        logger.error(
            "Failed to refund credits for user %s: %s", user_id, exc, exc_info=True
        )


def _get_api_key(header_key: str | None = None) -> str:
    """Obtém a chave da API Gemini.

    Prioridade:
      1. Header X-Gemini-Key enviado pelo frontend (chave do usuário).
      2. Configuração no .env (via Pydantic Settings).
      3. Se todas ausentes → 401 Unauthorized.
    """
    # 1. Chave do header (usuário)
    if header_key and header_key.strip():
        clean = header_key.strip()
        logger.info("Gemini: usando chave do usuário (Header) [%s]", _mask_key(clean))
        return clean

    # 2. Fallback: Pydantic Settings (carregado do .env)
    if _app_settings.gemini_api_key:
        key = _app_settings.gemini_api_key
        logger.info("Gemini: usando chave do servidor (Env) [%s]", _mask_key(key))
        return key

    # 3. Nenhuma chave disponível
    raise HTTPException(
        status_code=401,
        detail=(
            "Chave da API Gemini não configurada no servidor. "
            "Verifique o arquivo .env no backend."
        ),
    )


def _upload_video_to_gemini(video_path: Path, api_key: str) -> str:
    _configure_genai(api_key)
    import google.generativeai as genai

    uploaded = genai.upload_file(path=str(video_path))
    file_name = getattr(uploaded, "name", None)
    if not file_name:
        raise RuntimeError("Falha ao fazer upload do vídeo para o Gemini")

    deadline = time.time() + GEMINI_POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        current = genai.get_file(file_name)
        state = getattr(getattr(current, "state", None), "name", None) or str(
            getattr(current, "state", "")
        )
        if state == "ACTIVE":
            return file_name
        if state in {"FAILED", "ERROR"}:
            raise RuntimeError("Gemini falhou ao processar o arquivo de vídeo")
        time.sleep(GEMINI_POLL_INTERVAL_SECONDS)

    raise RuntimeError("Timeout aguardando o Gemini processar o arquivo (ACTIVE)")


def _format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total = int(seconds)
    hh = total // 3600
    mm = (total % 3600) // 60
    ss = total % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def _parse_timestamp_to_seconds(timestamp: str) -> float:
    ts = (timestamp or "").strip()
    if not ts:
        return 0.0
    parts = ts.split(":")
    if len(parts) > 3:
        raise ValueError("timestamp inválido")
    try:
        nums = [float(p) for p in parts]
    except ValueError as exc:
        raise ValueError("timestamp inválido") from exc

    while len(nums) < 3:
        nums.insert(0, 0.0)
    hh, mm, ss = nums
    return max(0.0, hh * 3600.0 + mm * 60.0 + ss)


def _ensure_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg não está instalado no servidor. No Fedora: sudo dnf install -y ffmpeg",
        )
    return path


def _is_supported_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host in {"youtube.com", "m.youtube.com", "youtu.be"} or host.endswith(
        ".youtube.com"
    )


def _ytdlp_cmd() -> list[str]:
    # Prefer binary if available, otherwise fall back to python module.
    base = ["yt-dlp"] if shutil.which("yt-dlp") else [sys.executable, "-m", "yt_dlp"]
    return base + [
        "--no-playlist",
        "--no-warnings",
        "--max-filesize",
        f"{MAX_VIDEO_MB}M",
        "--js-runtime",
        "node",
        "--remote-components",
        "ejs:github",
        # Force mp4 for easiest handling in browser/premiere
        "-f",
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format",
        "mp4",
    ]


def _ytdlp_cookie_args() -> list[str]:
    raw = (YTDLP_COOKIES_FILE or "").strip()
    if not raw:
        return []
    try:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (Path(__file__).resolve().parent / path).resolve()
        if path.exists() and path.is_file():
            return ["--cookies", str(path)]
    except Exception:
        pass
    return []


def _ytdlp_browser_cookie_args() -> list[str]:
    raw = (YTDLP_COOKIES_FROM_BROWSER or "").strip()
    if not raw:
        return []
    # Allow passing extra selector arguments if needed (e.g. "firefox:default" or keyring selector).
    if (YTDLP_COOKIES_FROM_BROWSER_ARGS or "").strip():
        selector = f"{raw}:{YTDLP_COOKIES_FROM_BROWSER_ARGS.strip()}"
    else:
        selector = raw
    return ["--cookies-from-browser", selector]


def _ytdlp_po_token_args() -> list[str]:
    """Return yt-dlp flags that activate PO Token generation (no cookies).

    Uses the bgutil-ytdlp-pot-provider plugin installed in the Docker image.
    When CLIPBUILDER_YTDLP_PO_TOKEN_EXTRACTOR_URL is set, it points yt-dlp at
    an external bgutil HTTP server.  Otherwise the in-process extractor is used,
    which works transparently without any browser or cookies.

    PO Tokens tell YouTube that the request is coming from a real client, which
    is the root cause of the "Sign in to confirm you're not a bot" error on VPS.

    NOTE: Do NOT combine this with cookies — the GetPOT plugin intercepts all
    yt-dlp requests when installed, and mixing player_client=web + cookies causes
    "No video formats found!" in yt-dlp 2026.x because the two auth paths
    conflict.  Use _ytdlp_tv_client_args() when cookies are also present.
    """
    args = [
        "--extractor-args",
        "youtube:player_client=web",
        "--extractor-args",
        "youtube:po_token=web+MnS",  # instruct yt-dlp to request a PO token
    ]
    extractor_url = (YTDLP_PO_TOKEN_EXTRACTOR_URL or "").strip()
    if extractor_url:
        # External bgutil HTTP server — more reliable on headless VPS
        args += ["--extractor-args", f"youtube:pot_provider_base_url={extractor_url}"]
    return args


def _ytdlp_tv_client_args() -> list[str]:
    """Return yt-dlp flags that use the TV embedded client WITH cookies.

    The TV embedded client (tv_embedded) does NOT require a PO Token, so it
    sidesteps the GetPOT plugin conflict that causes "No video formats found!"
    when player_client=web is combined with a cookies file.

    This is the correct strategy to use when cookies are present:
      - player_client=tv_embedded bypasses GetPOT entirely
      - cookies authenticate the session as a logged-in user
      - result: YouTube treats the request as a real TV app + account

    Works even when the GetPOT plugin is installed, because tv_embedded does
    not trigger the PO Token code path in yt-dlp.
    """
    return [
        "--extractor-args",
        "youtube:player_client=tv_embedded",
    ]


def _ytdlp_ios_client_args() -> list[str]:
    """Return yt-dlp flags that use the iOS client."""
    return [
        "--extractor-args",
        "youtube:player_client=ios",
    ]


def _ytdlp_android_client_args() -> list[str]:
    """Return yt-dlp flags that use the Android client."""
    return [
        "--extractor-args",
        "youtube:player_client=android",
    ]


def _ytdlp_proxy_args() -> list[str]:
    """Return yt-dlp --proxy flag if CLIPBUILDER_YTDLP_PROXY is configured.

    A residential or mobile proxy is the most reliable long-term fix for VPS
    IP bans by YouTube.  Supported formats:
      - http://user:pass@host:port
      - socks5://user:pass@host:port
      - socks5h://host:port  (DNS resolved by proxy)

    Leave CLIPBUILDER_YTDLP_PROXY empty to skip (default).
    """
    proxy = (YTDLP_PROXY or "").strip()
    if not proxy:
        return []
    return ["--proxy", proxy]


def _ytdlp_auth_args() -> list[str]:
    """Build the full list of auth/bypass arguments for yt-dlp.

    When cookies are present, uses tv_embedded client (avoids GetPOT conflict).
    When no cookies are present, uses PO Token via bgutil plugin.
    Proxy args are always appended when configured.
    """
    cookie_args = _ytdlp_cookie_args() or _ytdlp_browser_cookie_args()
    proxy_args = _ytdlp_proxy_args()
    if cookie_args:
        # tv_embedded client works with cookies and does NOT trigger GetPOT,
        # which avoids the "No video formats found!" conflict in yt-dlp 2026.x.
        return cookie_args + _ytdlp_tv_client_args() + proxy_args
    # No cookies — use PO Token generation (GetPOT plugin) for VPS bypass.
    return _ytdlp_po_token_args() + proxy_args


def _run_ytdlp(cmd: list[str], timeout: int = YTDLP_DEFAULT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """Run a yt-dlp command and return the result.

    Uses a timeout (default 10 min) to prevent indefinite hangs on slow
    connections or large videos.
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timed out after %ds", timeout)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr=f"yt-dlp timed out after {timeout}s",
        )


def _is_bot_check_error(tail: str) -> bool:
    lowered = (tail or "").lower()
    return (
        ("sign in to confirm" in lowered and "not a bot" in lowered)
        or "confirm you're not a bot" in lowered
        or "tryyoutube" in lowered
        or "please sign in" in lowered
    )


def _is_bad_cookies_error(tail: str) -> bool:
    """Detect when cookies are poisoning the yt-dlp request.

    When cookies are expired/corrupt (e.g. only 24 lines instead of 100+),
    YouTube returns an empty player response instead of a normal bot check.
    The GetPOT plugin then reports "No video formats found!" because the
    authenticated session is broken.  In this case, retrying WITHOUT cookies
    (PO Token only) typically succeeds.

    Also detects "unable to extract" errors that occur with stale cookies
    sending yt-dlp to a malformed page.
    """
    lowered = (tail or "").lower()
    return (
        "no video formats found" in lowered
        or "requested format is not available" in lowered
        or ("unable to extract" in lowered and "initial player" in lowered)
        or "login required" in lowered
    )


def _download_youtube_video(*, url: str, out_path: Path) -> None:
    _ensure_ffmpeg()  # yt-dlp may need it to merge streams

    base_cmd = _ytdlp_cmd() + [
        "-o",
        str(out_path),
        url,
    ]

    # ── Strategy ordering ─────────────────────────────────────────────
    #
    # ROOT CAUSE: The GetPOT plugin intercepts ALL yt-dlp YouTube requests
    # when installed (visible as [youtube+GetPOT] in error output).
    # Combining player_client=web + cookies in yt-dlp 2026.x causes
    # "No video formats found!" because the two auth paths conflict.
    #
    # SOLUTION: When cookies are present, use player_client=tv_embedded
    # which does NOT require a PO Token and works cleanly with cookies.
    # When no cookies are present, use player_client=web + GetPOT (PO Token).
    #
    # Order:
    #   1. cookies + tv_embedded + proxy  — correct combo for cookies (no GetPOT conflict)
    #   2. cookies + tv_embedded          — same, without proxy
    #   3. pot + proxy                    — no cookies, GetPOT generates PO Token
    #   4. pot-only                       — no cookies, no proxy
    #   5. cookies + web (legacy)         — old behaviour, kept as fallback
    #   6. bare                           — last resort
    #
    # If a cookies-based strategy still fails with "No video formats found",
    # cookies_are_bad is set True and all remaining cookie strategies are
    # skipped to avoid wasting time on genuinely corrupt cookies.
    #
    # The most reliable long-term fix for VPS IP bans is configuring
    # CLIPBUILDER_YTDLP_PROXY with a residential proxy.
    # Providers: Bright Data, Oxylabs, Smartproxy.
    # Format: http://user:pass@host:port  or  socks5://user:pass@host:port
    proxy_args = _ytdlp_proxy_args()
    cookie_args = _ytdlp_cookie_args() or _ytdlp_browser_cookie_args()
    po_token_args = _ytdlp_po_token_args()
    tv_client_args = _ytdlp_tv_client_args()

    strategies: list[tuple[str, list[str], bool]] = []

    # Cookie strategies — use tv_embedded to avoid GetPOT conflict
    if cookie_args:
        # Use --no-plugin-dirs to prevent GetPOT plugin from intercepting
        # and conflicting with the cookies/tv_embedded path.
        cookie_base = cookie_args + ["--no-plugin-dirs"]
        if proxy_args:
            strategies.append(
                (
                    "cookies+tv_embedded+proxy",
                    cookie_base + tv_client_args + proxy_args,
                    True,
                )
            )
        strategies.append(
            (
                "cookies+tv_embedded",
                cookie_base + tv_client_args,
                True,
            )
        )

    # PO Token strategies — no cookies, GetPOT plugin handles PO Token
    if proxy_args:
        strategies.append(("pot+proxy", po_token_args + proxy_args, False))
    strategies.append(("pot-only", po_token_args, False))

    # Web Embedded
    web_embedded_args = ["--extractor-args", "youtube:player_client=web_embedded"]
    if proxy_args:
        strategies.append(("web_embedded+proxy", web_embedded_args + proxy_args, False))
    strategies.append(("web_embedded-only", web_embedded_args, False))

    # Mobile clients
    if proxy_args:
        strategies.append(("ios+proxy", _ytdlp_ios_client_args() + proxy_args, False))
        strategies.append(("android+proxy", _ytdlp_android_client_args() + proxy_args, False))

    # Legacy fallback: cookies with web client (may conflict with GetPOT,
    # but kept in case tv_embedded fails for some video types)
    if cookie_args and proxy_args:
        strategies.append(
            ("cookies+web+proxy (legacy)", cookie_base + proxy_args, True)
        )
    if cookie_args:
        strategies.append(("cookies+web (legacy)", cookie_base, True))

    strategies.append(("bare", [], False))

    # De-duplicate consecutive identical arg lists (e.g. when no cookies are
    # set, strategy 1 and pot+proxy would be the same).
    seen: list[list[str]] = []
    deduped_strategies: list[tuple[str, list[str], bool]] = []
    for label, extra, uses_cookies in strategies:
        if extra not in seen:
            seen.append(extra)
            deduped_strategies.append((label, extra, uses_cookies))

    last_tail = ""
    proc: subprocess.CompletedProcess | None = None
    cookies_are_bad = False  # set True when cookies cause format errors

    for label, extra_args, uses_cookies in deduped_strategies:
        # Skip cookie-based strategies once we know cookies are poisoned
        if uses_cookies and cookies_are_bad:
            logger.info(
                "yt-dlp strategy=%s skipped (cookies detected as expired/corrupt)",
                label,
            )
            continue

        # Remove output file from a previous failed attempt before retrying
        if out_path.exists():
            try:
                out_path.unlink()
            except Exception:
                pass

        cmd = base_cmd[:-1] + extra_args + [base_cmd[-1]]  # insert before url
        logger.info("yt-dlp strategy=%s cmd=%s", label, cmd)
        proc = _run_ytdlp(cmd)

        if proc.returncode == 0:
            logger.info("yt-dlp succeeded with strategy=%s", label)
            break  # success — stop retrying

        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        last_tail = "\n".join((stderr.splitlines() + stdout.splitlines())[-20:]).strip()
        logger.warning(
            "yt-dlp strategy=%s failed (rc=%d): %s", label, proc.returncode, last_tail
        )

        # Detect poisoned cookies: "No video formats found!" or "Requested
        # format is not available" when cookies are in use means the
        # authenticated session is broken.  Mark cookies as bad so that
        # subsequent cookie-based strategies are skipped — retrying without
        # cookies (PO Token only) typically fixes it.
        if uses_cookies and _is_bad_cookies_error(last_tail):
            cookies_are_bad = True
            logger.warning(
                "yt-dlp: cookies appear expired/corrupt (bad-cookies error detected). "
                "Skipping remaining cookie-based strategies. "
                "Re-export cookies via ./setup_youtube_cookies.sh to fix."
            )
    else:
        # All strategies exhausted
        if cookies_are_bad:
            logger.error(
                "yt-dlp: all strategies failed. Cookies are expired/corrupt "
                "(detected 'No video formats found' with cookies active). "
                "Admin: re-export cookies via ./setup_youtube_cookies.sh or "
                "remove them with ./setup_youtube_cookies.sh --remove. "
                "Also consider configuring CLIPBUILDER_YTDLP_PROXY. "
                "Last output: %s",
                last_tail,
            )

        if _is_bot_check_error(last_tail) or cookies_are_bad:
            # Log the full technical details for the admin
            if not cookies_are_bad:
                logger.error(
                    "YouTube bot-check block detected. Strategies exhausted. "
                    "Admin: configure CLIPBUILDER_YTDLP_COOKIES_FILE, "
                    "CLIPBUILDER_YTDLP_COOKIES_FROM_BROWSER, or "
                    "CLIPBUILDER_YTDLP_PROXY to resolve. Last output: %s",
                    last_tail,
                )

            if cookies_are_bad:
                hint = (
                    "O YouTube bloqueou o download do vídeo. "
                    "Os cookies instalados no servidor estão expirados ou corrompidos "
                    "e estão prejudicando o download. "
                    "Peça ao administrador para atualizar os cookies "
                    "(./setup_youtube_cookies.sh) ou removê-los "
                    "(./setup_youtube_cookies.sh --remove), "
                    "e/ou configurar um proxy residencial (CLIPBUILDER_YTDLP_PROXY)."
                )
            else:
                hint = (
                    "O YouTube bloqueou o download do vídeo. "
                    "Isso pode ser temporário — tente novamente em alguns minutos."
                )
            raise HTTPException(status_code=403, detail=hint)

        raise RuntimeError(
            f"yt-dlp failed (rc={proc.returncode if proc is not None else '?'}): {last_tail or 'unknown error'}"
        )

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("Download falhou: arquivo de saída não foi criado")

    if out_path.stat().st_size > MAX_VIDEO_BYTES:
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(
            status_code=413,
            detail=(
                f"Vídeo muito grande (limite atual: {MAX_VIDEO_MB} MB). "
                "Ajuste CLIPBUILDER_MAX_VIDEO_BYTES no backend/.env."
            ),
        )


def _make_gemini_clip(
    *, source_path: Path, timestamp_seconds: float, clip_seconds: int, out_path: Path
) -> tuple[int, int]:
    ffmpeg: str = _ensure_ffmpeg()
    clip_seconds = max(MIN_CLIP_DURATION_SECONDS, int(clip_seconds))
    half = clip_seconds // 2
    start = max(0, int(timestamp_seconds) - half)
    duration = clip_seconds

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, capture_output=True, text=True)

    def tail(stderr: str) -> str:
        return "\n".join((stderr or "").strip().splitlines()[-20:]).strip()

    # Attempt 1: re-encode to a smaller proxy (best for cost/speed), but may fail on
    # ffmpeg builds without libx264 (common on Fedora ffmpeg-free).
    vf = f"scale=-2:{max(MIN_FRAME_SCALE_HEIGHT, int(GEMINI_PROXY_HEIGHT))}"
    for video_encoder in ["libx264", "libopenh264"]:
        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-i",
            str(source_path),
            "-vf",
            vf,
            "-c:v",
            video_encoder,
            "-preset",
            "veryfast",
            "-crf",
            str(VIDEO_ENCODE_CRF),
            "-c:a",
            "aac",
            "-b:a",
            f"{AUDIO_BITRATE_KBPS}k",
            "-movflags",
            "+faststart",
            str(out_path),
        ]

        proc = run(cmd)
        if proc.returncode == 0:
            return start, duration

        err = proc.stderr or ""
        # If encoder isn't available, try the next option.
        if f"Unknown encoder '{video_encoder}'" in err:
            continue

        # Other failures: break and try stream copy.
        break

    # Attempt 2: stream copy (no re-encode). This is very compatible and avoids encoder issues.
    copy_cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-i",
        str(source_path),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(out_path),
    ]

    proc = run(copy_cmd)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg falhou: " + tail(proc.stderr or ""))
    return start, duration


def _describe_at_timestamp(
    *,
    gemini_file_name: str,
    timestamp: str,
    clip_seconds: int,
    api_key: str,
    model_name: str,
    user_prompt: str | None = None,
    include_timestamp: bool = True,
) -> str:
    _configure_genai(api_key)
    import google.generativeai as genai
    from google.api_core import exceptions as gexc  # type: ignore

    # Accept either "gemini-2.0-flash" or "models/gemini-2.0-flash".
    normalized_model = (model_name or "").strip()
    if normalized_model and not normalized_model.startswith("models/"):
        normalized_model = f"models/{normalized_model}"

    file_ref = genai.get_file(gemini_file_name)

    # 1. Instrução de Sistema / Persona
    system_instruction = (
        f"Você é um especialista em Documentação Técnica de Software. "
        f"Seu objetivo é criar tutoriais passo a passo claros e diretos. "
        f"Responda sempre em português do Brasil (pt-BR). Idioma preferido: {AI_LANGUAGE}."
    )

    # 2. Definição de Contexto Temporal (análise expandida)
    time_instruction = (
        f"O foco principal é o timestamp: {timestamp}. "
        f"No entanto, para entender o contexto, ANALISE o vídeo desde {TIMESTAMP_ANALYSIS_WINDOW_SECONDS} segundos ANTES até {TIMESTAMP_ANALYSIS_WINDOW_SECONDS} segundos DEPOIS desse momento. "
        "Use esse intervalo para identificar qual processo lógico está sendo iniciado ou concluído. "
        "Entenda o fluxo: Onde o usuário clicou antes para chegar aqui? O que acontece depois que confirma a ação? "
        "Identifique o OBJETIVO FINAL da ação (ex: não é apenas 'preencher campo', é 'Configurar filtro de data')."
    )

    # 3. Regras de Formatação e Estilo
    formatting_instruction = (
        "REGRAS DE SAÍDA:\n"
        "1. Identifique a ação macro (ex: 'Cadastrando um novo usuário').\n"
        "2. Gere APENAS os passos imperativos necessários para realizar essa ação.\n"
        "3. Ignore movimentos de mouse erráticos ou tentativas falhas.\n"
        "4. Não use narração (ex: 'O usuário clica...'). Use imperativo (ex: 'Clique em Salvar').\n"
        "5. Seja conciso (3 a 10 passos).\n"
        "6. Evite detalhes técnicos visuais (coordenadas X/Y, posições específicas como 'célula A1') a menos que cruciais.\n"
        "7. Não mencione 'vídeo', 'clipe', 'cena', 'tela', 'o usuário' ou 'o mouse'.\n"
        "8. Foque nos comandos, menus e opções relevantes para reproduzir o processo."
    )

    base_parts: list[str] = [
        system_instruction,
        time_instruction,
        formatting_instruction,
    ]

    if include_timestamp:
        base_parts.append(
            f"O procedimento ocorre especificamente ao redor de {timestamp}."
        )
    else:
        base_parts.append(
            "Descreva o procedimento exibido. Não inclua timestamp na resposta."
        )

    base = "\n\n".join(base_parts)

    if user_prompt and str(user_prompt).strip():
        prompt = (
            base
            + "\n\n"
            + "Contexto extra do usuário (se aplicável):\n"
            + str(user_prompt).strip()
        )
    else:
        prompt = base

    model = genai.GenerativeModel(normalized_model or DEFAULT_GEMINI_MODEL)

    def _extract_retry_seconds(message: str) -> float | None:
        # Example: "Please retry in 13.644857575s."
        import re

        m = re.search(
            r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", message, flags=re.IGNORECASE
        )
        if not m:
            return None
        try:
            value = float(m.group(1))
        except ValueError:
            return None
        return min(value, MAX_RETRY_SLEEP_SECONDS) if value > 0 else None

    response = None
    for attempt in range(2):
        try:
            response = model.generate_content([file_ref, prompt])
            break
        except (
            getattr(gexc, "ResourceExhausted", Exception),
            getattr(gexc, "TooManyRequests", Exception),
        ) as exc:
            if attempt >= 1:
                raise
            retry_seconds = _extract_retry_seconds(str(exc) or "")
            # Cap to keep requests responsive.
            sleep_for = min(max(retry_seconds or 2.0, 0.5), 15.0)
            import time

            time.sleep(sleep_for)

    if response is None:
        return ""
    text = getattr(response, "text", None)
    if not text:
        return ""
    return str(text).strip()


# ---------------------------------------------------------------------------
# Gemini API Integration (Llama 4 Vision + Whisper Turbo)
# ---------------------------------------------------------------------------


def _extract_frames_from_video(
    video_path: Path,
    timestamp_seconds: float,
    window_seconds: int = FRAME_EXTRACTION_WINDOW_SECONDS,
    frame_count: int = DEFAULT_FRAME_COUNT,
) -> list[bytes]:
    """Extract frames from video around the timestamp.

    Extracts `frame_count` frames evenly distributed in a window of
    `window_seconds` before and after the timestamp.
    Returns list of PNG image bytes.
    """
    ffprobe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        video_duration = float(result.stdout.strip())
    except Exception:
        video_duration = timestamp_seconds + window_seconds + 10

    # Calculate frame timestamps
    start_time = max(0, timestamp_seconds - window_seconds)
    end_time = min(video_duration, timestamp_seconds + window_seconds)
    actual_window = end_time - start_time

    if frame_count <= 1:
        timestamps = [timestamp_seconds]
    else:
        step = actual_window / (frame_count - 1)
        timestamps = [start_time + i * step for i in range(frame_count)]

    frames: list[bytes] = []
    for ts in timestamps:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(ts),
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-vf",
                f"scale=-1:{max(MIN_FRAME_SCALE_HEIGHT, GEMINI_PROXY_HEIGHT)}",  # Reuse existing height config
                "-f",
                "image2",
                tmp_path,
            ]
            subprocess.run(ffmpeg_cmd, capture_output=True, check=True)

            with open(tmp_path, "rb") as f:
                frame_data = f.read()
                if frame_data:
                    frames.append(frame_data)
        except Exception as exc:
            logger.warning("Failed to extract frame at %.2fs: %s", ts, exc)
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    return frames


def _extract_frames_from_gif(gif_bytes: bytes, frame_count: int = GIF_FRAME_COUNT) -> list[bytes]:
    """Extract frames from a GIF file using Pillow.

    Returns up to `frame_count` frames evenly distributed across the GIF,
    as PNG bytes for sending to Gemini Vision.
    """
    try:
        from PIL import Image, ImageSequence
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Dependência 'Pillow' não instalada. Execute: pip install Pillow",
        ) from exc

    try:
        img = Image.open(io.BytesIO(gif_bytes))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo GIF inválido ou corrompido: {exc!s}",
        ) from exc

    if getattr(img, "format", None) and str(img.format).upper() not in ("GIF",):
        raise HTTPException(
            status_code=400,
            detail="O arquivo não é um GIF válido.",
        )

    # Collect all frames (ImageSequence.Iterator consumes, so we list once)
    seq_frames: list[Any] = []
    for frame in ImageSequence.Iterator(img):
        seq_frames.append(frame.copy())
    if not seq_frames:
        seq_frames = [img.copy()]

    n = len(seq_frames)
    if frame_count <= 1 or n <= 1:
        indices = [0]
    else:
        step = (n - 1) / max(1, frame_count - 1)
        indices = [min(int(round(i * step)), n - 1) for i in range(frame_count)]
        indices = sorted(set(indices))[:frame_count]

    out: list[bytes] = []
    for idx in indices:
        try:
            frame_img = seq_frames[idx]
            buf = io.BytesIO()
            frame_img.save(buf, format="PNG")
            data = buf.getvalue()
            if data:
                out.append(data)
        except Exception as exc:
            logger.warning("Failed to export GIF frame %s as PNG: %s", idx, exc)

    if not out:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível extrair frames do GIF.",
        )
    return out


def _extract_audio_clip(
    video_path: Path,
    timestamp_seconds: float,
    window_seconds: int = AUDIO_EXTRACTION_WINDOW_SECONDS,
) -> Path | None:
    """Extract audio clip from video around the timestamp.

    Returns path to temporary WAV file, or None if extraction fails.
    """
    # Get video duration
    ffprobe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        video_duration = float(result.stdout.strip())
    except Exception:
        video_duration = timestamp_seconds + window_seconds + 10

    start_time = max(0, timestamp_seconds - window_seconds)
    end_time = min(video_duration, timestamp_seconds + window_seconds)
    duration = end_time - start_time

    # Arquivo temporário para o áudio.  mkstemp() cria o arquivo de forma
    # atômica — mktemp() apenas sorteava um nome, deixando uma janela em que
    # outro processo podia criar o caminho antes de nós.
    _audio_fd, _audio_name = tempfile.mkstemp(suffix=".wav", prefix="clip_audio_")
    os.close(_audio_fd)
    audio_path = Path(_audio_name)

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_time),
        "-i",
        str(video_path),
        "-t",
        str(duration),
        "-vn",  # No video
        "-acodec",
        "pcm_s16le",
        "-ar",
str(WHISPER_SAMPLE_RATE_HZ),  # 16kHz for Whisper
        "-ac",
        "1",  # Mono
        str(audio_path),
    ]

    try:
        subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
        if audio_path.exists() and audio_path.stat().st_size > MIN_AUDIO_FILE_SIZE_BYTES:
            return audio_path
    except Exception as exc:
        logger.warning("Failed to extract audio: %s", exc)

    try:
        audio_path.unlink(missing_ok=True)
    except Exception:
        pass
    return None


@dataclass(frozen=True, slots=True)
class StepPayload:
    """Um passo recebido no campo `steps` de /export.

    Aceita tanto `"texto"` quanto `{"description": ..., "has_image": ...}`; a
    normalização acontece em :func:`_parse_steps`.
    """

    description: str
    has_image: bool = True


def _parse_steps(steps_raw: str) -> list[StepPayload]:
    try:
        payload: Any = json.loads(steps_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid steps JSON: {exc.msg}"
        ) from exc

    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="Steps must be a JSON array")

    steps: list[StepPayload] = []
    for item in payload:
        if isinstance(item, str):
            steps.append(StepPayload(description=item, has_image=True))
            continue
        if isinstance(item, dict):
            description = item.get("description", "")
            if not isinstance(description, str):
                raise HTTPException(
                    status_code=400, detail="Each step description must be a string"
                )

            has_image_raw = item.get("has_image", True)
            has_image = True
            if isinstance(has_image_raw, bool):
                has_image = has_image_raw
            elif has_image_raw is None:
                has_image = True
            else:
                raise HTTPException(
                    status_code=400, detail="Each step has_image must be a boolean"
                )

            steps.append(StepPayload(description=description, has_image=has_image))
            continue
        raise HTTPException(
            status_code=400, detail="Each step must be a string or an object"
        )

    return steps


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def _normalize_image_to_png(image_bytes: bytes) -> bytes:
    """Accept PNG as-is; accept JPEG and convert to PNG. Raise HTTPException for invalid data."""
    if not image_bytes or len(image_bytes) < 8:
        raise HTTPException(
            status_code=400,
            detail="One or more images are invalid (expected PNG or JPEG)",
        )
    if image_bytes.startswith(_PNG_MAGIC):
        return image_bytes
    if image_bytes.startswith(_JPEG_MAGIC):
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="One or more images are invalid (could not convert to PNG)",
            ) from exc
    raise HTTPException(
        status_code=400, detail="One or more images are invalid (expected PNG or JPEG)"
    )


def _safe_filename(title: str, fallback: str = "documento") -> str:
    """Gera nome de arquivo seguro a partir do título.

    Remove acentos (NFD + strip combining marks), substitui caracteres
    inválidos por ``_`` e limita a 80 caracteres.  Espaços são preservados
    para que o nome fique legível no sistema de arquivos.
    """
    name = (title or "").strip()
    if not name:
        return fallback
    # Remove acentos: Título → Titulo
    name = unicodedata.normalize("NFD", name)
    name = "".join(ch for ch in name if unicodedata.category(ch) != "Mn")
    # Mantém letras, dígitos, espaço, ponto, hífen e underscore
    name = "".join(c if c.isalnum() or c in "._- " else "_" for c in name)
    # Colapsa espaços/underscores consecutivos
    name = " ".join(name.split())
    return name[:80].strip() or fallback


def _sanitize_image_prefix(prefix: str | None) -> str:
    raw = (prefix or "").strip()
    if not raw:
        return "step_"
    # If user typed an extension, drop it to avoid "foo.png01.png"
    if raw.lower().endswith(".png"):
        raw = raw[: -len(".png")]
    # Prevent path traversal / nested paths
    raw = raw.replace("/", "_").replace("\\", "_")
    raw = "_".join(raw.split())
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    cleaned = "".join((ch if ch in allowed else "_") for ch in raw)
    cleaned = cleaned[:60].strip("._")
    return cleaned or "step_"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/templates")
def list_templates_endpoint(
    user: CurrentAuthorizedUser,
    db: Session = Depends(get_db),
):
    """Return available document templates, filtered by user permissions.

    If the user has template restrictions enabled, only permitted templates are returned.
    Admins always see everything.
    """
    from app.admin.template_service import list_all_templates, list_templates_for_user
    
    templates = list_templates_for_user(db, user)
    
    # Fallback: if the database itself has no active templates, use the in-memory registry.
    # Otherwise, if templates is empty, it means the user is strictly restricted to no templates.
    if not templates and not list_all_templates(db):
        from templates.template_registry import list_templates as list_registry

        templates = list_registry()

    return {"templates": templates}


@app.get("/auth/me")
def auth_me(user: CurrentAuthorizedUser) -> dict:
    return user


@app.get("/ai-keys-status")
async def ai_keys_status():
    """Retorna quais chaves de IA estão configuradas no servidor (via .env)."""
    return {
        "gemini": bool(_app_settings.gemini_api_key),
        
    }


@app.post("/test-api-keys")
async def test_api_keys(
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
        x_google_api_key: str | None = Header(default=None, alias="X-Google-Api-Key"),
    ):
    """
    Testa a validade das chaves de API enviadas via headers ou configuradas no servidor.
    """
    result: dict[str, Any] = {"gemini": False}

    # --- Testar Gemini ---
    gemini_header = x_gemini_key or x_google_api_key
    try:
        gemini_key = _get_api_key(gemini_header)
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        # Chamada leve: listar modelos disponíveis
        list(genai.list_models())
        result["gemini"] = True
        if not gemini_header:
            result["geminiNote"] = "Usando chave do servidor."
    except Exception as exc:
        msg = str(exc)[:200]
        result["geminiError"] = f"Falha no Gemini: {msg}"
        logger.warning("test-api-keys: Gemini FALHOU: %s", msg)

    return result


@app.post("/videos")
async def upload_video(
    video: UploadFile = File(...),
    x_google_api_key: str | None = Header(default=None, alias="X-Google-Api-Key"),
):
    filename = (video.filename or "").strip()
    ext = Path(filename).suffix.lower()
    content_type = (video.content_type or "").lower().strip()

    content_type_to_ext = {
        "video/mp4": ".mp4",
        "video/x-matroska": ".mkv",
        "application/x-matroska": ".mkv",
    }

    if ext == "" and content_type in content_type_to_ext:
        ext = content_type_to_ext[content_type]

    if ext not in {".mp4", ".mkv"}:
        raise HTTPException(
            status_code=400,
            detail=f"Formato inválido. Use .mp4 ou .mkv (filename='{filename}', content_type='{content_type}')",
        )

    video_id = uuid.uuid4().hex
    target_path = DATA_DIR / f"video_{video_id}{ext}"

    total = 0
    try:
        with target_path.open("wb") as f:
            while True:
                chunk = await video.read(UPLOAD_CHUNK_SIZE_KB * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Vídeo muito grande (limite atual: {MAX_VIDEO_MB} MB). "
                            "Ajuste CLIPBUILDER_MAX_VIDEO_BYTES no backend/.env."
                        ),
                    )
                f.write(chunk)
    except OSError as exc:
        if getattr(exc, "errno", None) == ENOSPC:
            logger.error(
                "disk full while saving upload to %s", target_path, exc_info=True
            )
            raise HTTPException(
                status_code=507,
                detail=(
                    "Sem espaço em disco para salvar o vídeo. "
                    "Ajuste CLIPBUILDER_DATA_DIR para um caminho com espaço suficiente."
                ),
            ) from exc
        logger.error("os error while saving upload to %s", target_path, exc_info=True)
        raise
    finally:
        try:
            await video.close()
        except Exception:
            pass

    # For very large videos, we keep the original locally and only send a short clip to Gemini on demand.
    with _videos_lock:
        _videos[video_id] = VideoEntry(path=target_path, status="ready")

    # Cleanup old files to stay within MAX_DATA_FILES limit
    _cleanup_old_files()

    return {"video_id": video_id, "status": "ready"}


@app.post("/videos/raw")
async def upload_video_raw(
    request: Request,
    x_filename: str | None = Header(default=None, alias="X-Filename"),
    x_google_api_key: str | None = Header(default=None, alias="X-Google-Api-Key"),
    x_upload_id: str | None = Header(default=None, alias="X-Upload-Id"),
    x_chunk_index: str | None = Header(default=None, alias="X-Chunk-Index"),
    x_total_chunks: str | None = Header(default=None, alias="X-Total-Chunks"),
):
    is_chunked = (
        x_upload_id is not None
        and x_chunk_index is not None
        and x_total_chunks is not None
    )

    _billing_user_id = None
    if is_chunked:
        import re
        if not re.match(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", x_upload_id, re.IGNORECASE):
            raise HTTPException(status_code=400, detail="Invalid X-Upload-Id format")
        try:
            chunk_index = int(x_chunk_index)
            total_chunks = int(x_total_chunks)
        except ValueError:
            raise HTTPException(status_code=400, detail="X-Chunk-Index and X-Total-Chunks must be integers") from None
        
        if chunk_index < 0 or total_chunks <= 0 or chunk_index >= total_chunks:
            raise HTTPException(status_code=400, detail="Invalid chunk range parameters")
        
        # Only debit on first chunk
        if chunk_index == 0:
            _billing_user_id = _debit_user_credits(
                request.headers.get("authorization"), "/videos/raw"
            )
    else:
        # Standard raw upload, debit user credits
        _billing_user_id = _debit_user_credits(
            request.headers.get("authorization"), "/videos/raw"
        )

    filename = (x_filename or "video.mp4").strip()
    ext = Path(filename).suffix.lower()
    if ext not in {".mp4", ".mkv"}:
        # Refund credits if error occurs
        if _billing_user_id:
            _refund_user_credits(_billing_user_id, "/videos/raw")
        raise HTTPException(
            status_code=400, detail="Formato inválido. Use .mp4 ou .mkv"
        )

    if is_chunked:
        chunk_target_path = DATA_DIR / f"upload_{x_upload_id}_{chunk_index}.part"
        target_path = chunk_target_path
    else:
        video_id = uuid.uuid4().hex
        target_path = DATA_DIR / f"video_{video_id}{ext}"

    total = 0
    try:
        previous_size = 0
        if is_chunked:
            for idx in range(chunk_index):
                part_path = DATA_DIR / f"upload_{x_upload_id}_{idx}.part"
                if part_path.exists():
                    previous_size += part_path.stat().st_size
            if previous_size > MAX_VIDEO_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Vídeo muito grande (limite atual: {MAX_VIDEO_MB} MB). "
                        "Ajuste CLIPBUILDER_MAX_VIDEO_BYTES no backend/.env."
                    ),
                )

        with target_path.open("wb") as f:
            async for chunk in request.stream():
                if not chunk:
                    continue
                total += len(chunk)
                if (previous_size + total) > MAX_VIDEO_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Vídeo muito grande (limite atual: {MAX_VIDEO_MB} MB). "
                            "Ajuste CLIPBUILDER_MAX_VIDEO_BYTES no backend/.env."
                        ),
                    )
                f.write(chunk)
    except HTTPException:
        if _billing_user_id:
            _refund_user_credits(_billing_user_id, "/videos/raw")
        raise
    except OSError as exc:
        if _billing_user_id:
            _refund_user_credits(_billing_user_id, "/videos/raw")
        if getattr(exc, "errno", None) == ENOSPC:
            logger.error(
                "disk full while saving raw upload to %s", target_path, exc_info=True
            )
            raise HTTPException(
                status_code=507,
                detail=(
                    "Sem espaço em disco para salvar o vídeo. "
                    "Ajuste CLIPBUILDER_DATA_DIR para um caminho com espaço suficiente."
                ),
            ) from exc
        logger.error(
            "os error while saving raw upload to %s", target_path, exc_info=True
        )
        raise
    except Exception as exc:
        if _billing_user_id:
            _refund_user_credits(_billing_user_id, "/videos/raw")
        logger.warning("raw upload stream failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail="Falha ao ler o upload (conexão interrompida?)"
        ) from exc

    if is_chunked:
        # Check if all chunks have been received
        all_parts_exist = True
        for idx in range(total_chunks):
            if idx == chunk_index:
                continue
            part_path = DATA_DIR / f"upload_{x_upload_id}_{idx}.part"
            if not part_path.exists():
                all_parts_exist = False
                break
        
        if all_parts_exist:
            final_video_id = uuid.uuid4().hex
            final_target_path = DATA_DIR / f"video_{final_video_id}{ext}"
            
            try:
                with final_target_path.open("wb") as outfile:
                    for idx in range(total_chunks):
                        part_path = chunk_target_path if idx == chunk_index else DATA_DIR / f"upload_{x_upload_id}_{idx}.part"
                        with part_path.open("rb") as infile:
                            while True:
                                data = infile.read(64 * 1024)
                                if not data:
                                    break
                                outfile.write(data)
                
                # Cleanup part files
                for idx in range(total_chunks):
                    part_path = DATA_DIR / f"upload_{x_upload_id}_{idx}.part"
                    try:
                        part_path.unlink(missing_ok=True)
                    except Exception as e:
                        logger.warning("Failed to delete chunk part file %s: %s", part_path, e)
            except Exception as exc:
                if final_target_path.exists():
                    final_target_path.unlink(missing_ok=True)
                if _billing_user_id:
                    _refund_user_credits(_billing_user_id, "/videos/raw")
                logger.error("Failed to merge chunk parts for upload %s: %s", x_upload_id, exc, exc_info=True)
                raise HTTPException(
                    status_code=500, detail="Falha ao juntar as partes do upload"
                ) from exc
            
            with _videos_lock:
                _videos[final_video_id] = VideoEntry(path=final_target_path, status="ready")

            _cleanup_old_files()
            return {"video_id": final_video_id, "status": "ready"}
        else:
            return {"status": "uploading", "chunk_index": chunk_index}
    else:
        with _videos_lock:
            _videos[video_id] = VideoEntry(path=target_path, status="ready")

        _cleanup_old_files()
        return {"video_id": video_id, "status": "ready"}


@app.get("/videos/{video_id}/status")
def video_status(video_id: str):
    with _videos_lock:
        entry = _videos.get(video_id)
        if not entry:
            entry = _restore_video_entry_if_missing(video_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Vídeo não encontrado")
        return {"status": entry.status, "error": entry.error}


@app.get("/videos/{video_id}/file")
def video_file(video_id: str):
    with _videos_lock:
        entry = _videos.get(video_id)
        if not entry:
            entry = _restore_video_entry_if_missing(video_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Vídeo não encontrado")
        if entry.status != "ready":
            raise HTTPException(
                status_code=409, detail=entry.error or "Vídeo não está pronto"
            )
        path = entry.path

    ext = path.suffix.lower()
    media_type = "video/mp4" if ext == ".mp4" else "video/x-matroska"
    return FileResponse(
        path=path,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{path.name}"',
            "Cross-Origin-Resource-Policy": "cross-origin",
        },
    )


@app.post("/videos/youtube")
async def upload_youtube(
    background_tasks: BackgroundTasks,
    request: Request,
    x_google_api_key: str | None = Header(default=None, alias="X-Google-Api-Key"),
):
    # ── Credit debit (before processing) ──
    _billing_user_id = _debit_user_credits(
        request.headers.get("authorization"), "/videos/youtube"
    )

    # Expect JSON: {"url": "https://..."}
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail="Body inválido. Envie JSON com campo 'url'."
        ) from exc

    url = payload.get("url") if isinstance(payload, dict) else ""
    url = (url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Campo 'url' é obrigatório")
    if not _is_supported_youtube_url(url):
        raise HTTPException(
            status_code=400,
            detail="URL não suportada. Use um link do YouTube (youtube.com / youtu.be).",
        )

    # NOTE: API key validation removed from here – downloading a YouTube video
    # does not require the Gemini key.  The key will be validated later when
    # the user actually requests AI processing (e.g. /smart-text).

    video_id = uuid.uuid4().hex
    target_path = DATA_DIR / f"video_{video_id}.mp4"

    with _videos_lock:
        _videos[video_id] = VideoEntry(path=target_path, status="processing")

    def job() -> None:
        try:
            _download_youtube_video(url=url, out_path=target_path)
            with _videos_lock:
                current = _videos.get(video_id)
                if current:
                    current.status = "ready"
                    current.error = None
            # Cleanup old files to stay within MAX_DATA_FILES limit
            _cleanup_old_files()
        except HTTPException as exc:
            with _videos_lock:
                current = _videos.get(video_id)
                if current:
                    current.status = "error"
                    current.error = str(exc.detail)
        except Exception as exc:
            with _videos_lock:
                current = _videos.get(video_id)
                if current:
                    current.status = "error"
                    current.error = str(exc)
            logger.error(
                "youtube download failed (video_id=%s): %s",
                video_id,
                exc,
                exc_info=True,
            )

    background_tasks.add_task(job)
    return {"video_id": video_id, "status": "processing"}


@app.get("/videos/{video_id}/smart-text")
async def smart_text(
    request: Request,
    background_tasks: BackgroundTasks,
    video_id: str,
    timestamp: str | None = None,
    t: float | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
    prompt: str | None = None,
    include_timestamp: bool = True,
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
        # Legacy aliases (retrocompatibilidade)
    x_google_api_key: str | None = Header(default=None, alias="X-Google-Api-Key"),
    ):
    # Check AI permission based on model provider
    authorization = request.headers.get("authorization")
    _check_ai_permission(authorization, "gemini")

    # ── Credit debit (before AI call) ──
    _billing_user_id = _debit_user_credits(authorization, "/smart-text")

    with _videos_lock:
        entry = _videos.get(video_id)
        if not entry:
            entry = _restore_video_entry_if_missing(video_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Vídeo não encontrado")
        if entry.status != "ready":
            raise HTTPException(
                status_code=409, detail=entry.error or "Vídeo não está pronto"
            )
        source_path = entry.path

    gemini_header = x_gemini_key or x_google_api_key
    if timestamp is None:
        if t is None:
            raise HTTPException(
                status_code=400, detail="Informe timestamp (HH:MM:SS) ou t (segundos)"
            )
        timestamp = _format_timestamp(float(t))

    try:
        ts_seconds = _parse_timestamp_to_seconds(str(timestamp))
    except ValueError:
        raise HTTPException(
            status_code=400, detail="timestamp inválido. Use HH:MM:SS"
        ) from None

    # Default: Use Gemini
    api_key = _get_api_key(gemini_header)
    clip_key = f"{int(ts_seconds)}:{int(GEMINI_CLIP_SECONDS)}"
    with _videos_lock:
        cached = entry.clip_cache.get(clip_key)

    if not cached:
        clip_path = (
            DATA_DIR
            / f"clip_{video_id}_{int(ts_seconds)}_{int(GEMINI_CLIP_SECONDS)}.mp4"
        )
        try:
            # ffmpeg recorta o trecho do vídeo: segundos de CPU fora do loop.
            await _run_blocking(
                _make_gemini_clip,
                source_path=source_path,
                timestamp_seconds=ts_seconds,
                clip_seconds=GEMINI_CLIP_SECONDS,
                out_path=clip_path,
            )

            def upload_work() -> str:
                return _upload_video_to_gemini(clip_path, api_key)

            cached = await anyio.to_thread.run_sync(upload_work)
            with _videos_lock:
                current = _videos.get(video_id)
                if current and current.status == "ready":
                    current.clip_cache[clip_key] = cached
        except HTTPException:
            raise
        except Exception as exc:
            _refund_user_credits(_billing_user_id, "/smart-text")
            with _videos_lock:
                current = _videos.get(video_id)
                if current:
                    current.error = str(exc)
            logger.error(
                "gemini clip upload failed (video_id=%s, timestamp=%s): %s",
                video_id,
                timestamp,
                exc,
                exc_info=True,
            )
            raise HTTPException(
                status_code=500, detail="Falha ao preparar/enviar clipe para o Gemini"
            ) from exc
        finally:
            try:
                if clip_path.exists():
                    clip_path.unlink()
            except Exception:
                pass

    def work() -> str:
        return _describe_at_timestamp(
            gemini_file_name=str(cached),
            timestamp=str(timestamp),
            clip_seconds=int(GEMINI_CLIP_SECONDS),
            api_key=api_key,
            model_name=model,
            user_prompt=prompt,
            include_timestamp=bool(include_timestamp),
        )

    try:
        text = await anyio.to_thread.run_sync(work)
    except Exception as exc:
        _refund_user_credits(_billing_user_id, "/smart-text")
        if isinstance(exc, HTTPException):
            raise

        # Normalize common Gemini errors so the frontend gets a meaningful status.
        try:
            import re

            from google.api_core import exceptions as gexc  # type: ignore

            def _retry_hint_from_message(message: str) -> str:
                # Example: "Please retry in 13.644857575s."
                m = re.search(
                    r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", message, flags=re.IGNORECASE
                )
                if not m:
                    return ""
                seconds = m.group(1)
                return f" Tente novamente em ~{seconds}s."

            def _as_list(e: BaseException) -> list[BaseException]:
                # AnyIO / Python may raise ExceptionGroup with multiple nested exceptions.
                eg = getattr(e, "exceptions", None)
                if isinstance(eg, list):
                    return eg
                return [e]

            candidates: list[BaseException] = []
            for one in _as_list(exc):
                candidates.append(one)
                cause = getattr(one, "__cause__", None)
                if isinstance(cause, BaseException):
                    candidates.append(cause)

            def _msg(e: BaseException) -> str:
                try:
                    return str(e) or e.__class__.__name__
                except Exception:
                    return e.__class__.__name__

            for one in candidates:
                message = _msg(one)
                if isinstance(one, getattr(gexc, "ResourceExhausted", ())) or (
                    "quota" in message.lower()
                    or "resourceexhausted" in message.lower()
                    or " 429" in message
                ):
                    raise HTTPException(
                        status_code=429,
                        detail=(
                            "Quota/limite do Gemini excedido (429). Verifique billing/limites do projeto e tente novamente."
                            + _retry_hint_from_message(message)
                        ),
                    ) from exc

            if isinstance(exc, getattr(gexc, "TooManyRequests", ())):
                raise HTTPException(
                    status_code=429,
                    detail="Muitas requisições ao Gemini (429). Tente novamente em instantes.",
                ) from exc

            if isinstance(exc, getattr(gexc, "PermissionDenied", ())):
                raise HTTPException(
                    status_code=403,
                    detail="Permissão negada pelo Gemini. Verifique se a API está habilitada e se a chave é válida.",
                ) from exc

            if isinstance(exc, getattr(gexc, "NotFound", ())):
                raise HTTPException(
                    status_code=400,
                    detail="Modelo do Gemini não encontrado/suportado. Ajuste o model para um valor retornado por list_models().",
                ) from exc

            if isinstance(exc, getattr(gexc, "InvalidArgument", ())):
                raise HTTPException(
                    status_code=400, detail="Parâmetros inválidos ao chamar o Gemini."
                ) from exc
        except Exception:
            # If google-api-core isn't available or anything goes wrong while mapping,
            # fall back to the generic handler below.
            pass

        with _videos_lock:
            current = _videos.get(video_id)
            if current:
                current.error = str(exc)
        logger.error(
            "gemini smart-text failed (video_id=%s, model=%s, timestamp=%s): %s",
            video_id,
            model,
            timestamp,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Falha ao analisar com Gemini"
        ) from exc

    # Log Gemini usage
    background_tasks.add_task(
        log_ai_usage_background,
        authorization=request.headers.get("authorization"),
        endpoint="/smart-text",
        ai_provider="gemini",
        model=model,
    )
    # ── Run on_frame_capture tools in parallel (non-blocking) ──────────
    response_data: dict[str, Any] = {"text": text}

    try:
        from app.database import SessionLocal
        from app.tools.engine import tools_engine

        # Resolve API keys for tools (best-effort, don't fail the main response)
        _tools_gemini_key = None
        _tools_gemini_key = None
        try:
            _tools_gemini_key = _get_api_key(gemini_header)
        except Exception:
            pass
        if _tools_gemini_key:
            # Extração de frame e de áudio chamam ffprobe/ffmpeg e leem arquivos
            # do disco: trabalho bloqueante que precisa sair do event loop.
            def _extract_frame_for_tools() -> bytes | None:
                frames = _extract_frames_from_video(
                    video_path=source_path,
                    timestamp_seconds=ts_seconds,
                    window_seconds=5,
                    frame_count=1,
                )
                return frames[0] if frames else None

            def _extract_audio_for_tools() -> bytes | None:
                audio_path = _extract_audio_clip(
                    video_path=source_path,
                    timestamp_seconds=ts_seconds,
                    window_seconds=AUDIO_EXTRACTION_WINDOW_SECONDS,
                )
                if not (audio_path and audio_path.exists()):
                    return None
                try:
                    return audio_path.read_bytes()
                finally:
                    audio_path.unlink(missing_ok=True)

            _tool_image_bytes = None
            try:
                _tool_image_bytes = await _run_blocking(_extract_frame_for_tools)
            except Exception:
                logger.debug("Falha ao extrair frame para as tools", exc_info=True)

            _tool_audio_bytes = None
            try:
                _tool_audio_bytes = await _run_blocking(_extract_audio_for_tools)
            except Exception:
                logger.debug("Falha ao extrair áudio para as tools", exc_info=True)

            # Build context for tools
            _tool_context: dict[str, Any] = {
                "trigger": "on_frame_capture",
                "image_bytes": _tool_image_bytes,
                "audio_bytes": _tool_audio_bytes,
                "previous_steps": [],  # frontend can enrich this later
                "project_id": None,
            }

            with SessionLocal() as tools_db:
                tools_results = await tools_engine.run_tools_for_trigger(
                    trigger="on_frame_capture",
                    context=_tool_context,
                    gemini_key=_tools_gemini_key,
                    db=tools_db,
                )

            # Merge tool outputs into the response by output_target
            tools_outputs = {}
            for tid, info in tools_results.items():
                tools_outputs[tid] = info.get("output")
                if info.get("status") != "success":
                    continue
                target = info.get("output_target", "log_only")
                if target == "suggestion" and info.get("output"):
                    response_data["suggestion"] = info["output"]
                elif target == "context_tag" and info.get("output"):
                    response_data["context_tag"] = info["output"]
                elif target == "description" and info.get("output"):
                    # Don't overwrite the main description — append as extra
                    response_data.setdefault("tools_description", info["output"])

            if tools_outputs:
                response_data["tools_outputs"] = tools_outputs
    except Exception as tools_exc:
        # Tools must never break the main smart-text flow
        logger.debug("on_frame_capture tools skipped: %s", tools_exc)

    return response_data


@app.post("/export")
async def export_documentation(
    steps: str = Form(...),
    images: list[UploadFile] = File(default=[]),
    image_name_prefix: str | None = Form(default=None),
    output_format: str | None = Form(default="markdown"),
):
    parsed_steps = _parse_steps(steps)

    fmt = (output_format or "markdown").strip().lower()
    if fmt not in {"markdown", "html", "docx", "plain", "pdf"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid output_format. Use markdown, html, docx, pdf, or plain.",
        )

    prefix = _sanitize_image_prefix(image_name_prefix)

    expected_images = sum(1 for s in parsed_steps if s.has_image)
    if expected_images != len(images):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Images count ({len(images)}) must match steps with images ({expected_images}). "
                "Send images only for steps where has_image=true."
            ),
        )

    total_bytes = 0
    processed_images: list[bytes] = []

    for upload in images:
        image_bytes = await upload.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="One or more images are empty")

        if len(image_bytes) > MAX_SINGLE_IMAGE_BYTES:
            raise HTTPException(
                status_code=413, detail="One or more images are too large"
            )

        total_bytes += len(image_bytes)
        if total_bytes > MAX_TOTAL_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Export payload too large")

        processed_images.append(_normalize_image_to_png(image_bytes))

    md_lines: list[str] = ["# Tutorial\n"]

    step_index_to_image: dict[int, bytes] = {}
    image_cursor = 0
    for step_idx, step in enumerate(parsed_steps, start=1):
        if step.has_image:
            if image_cursor >= len(processed_images):
                raise HTTPException(
                    status_code=400, detail="Missing image for one or more steps"
                )
            step_index_to_image[step_idx] = processed_images[image_cursor]
            image_cursor += 1

    for i, step in enumerate(parsed_steps, start=1):
        md_lines.append(f"## Passo {i}\n")
        description = step.description.strip() or "(sem descrição)"
        md_lines.append(description + "\n")
        if step.has_image:
            md_lines.append(f"[Imagem: Passo {i}]\n")

    md_content = "\n".join(md_lines).strip() + "\n"
    image_map = {
        f"Passo {i}": img_bytes for i, img_bytes in step_index_to_image.items()
    }

    if fmt == "plain":
        lines: list[str] = ["Tutorial", ""]
        for i, step in enumerate(parsed_steps, start=1):
            lines.append(f"Passo {i}")
            lines.append("-" * 7)
            lines.append((step.description or "").strip() or "(sem descrição)")
            if step.has_image:
                lines.append(f"[imagem: {prefix}{i:02d}.png]")
            lines.append("")

        txt = "\n".join(lines).rstrip() + "\n"
        buf = io.BytesIO(txt.encode("utf-8"))
        headers = {"Content-Disposition": 'attachment; filename="tutorial.txt"'}
        return StreamingResponse(
            buf, media_type="text/plain; charset=utf-8", headers=headers
        )

    if fmt == "html":
        try:
            from app.services.export_from_markdown import markdown_to_html
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="Dependência para HTML não instalada. Instale markdown (python-markdown) no backend.",
            ) from exc
        html_str = await _run_export(
            markdown_to_html,
            md_content,
            image_map=image_map,
            output_path=None,
            title="Tutorial",
        )
        html_bytes = html_str.encode("utf-8")
        buf = io.BytesIO(html_bytes)
        headers = {"Content-Disposition": 'attachment; filename="tutorial.html"'}
        return StreamingResponse(
            buf, media_type="text/html; charset=utf-8", headers=headers
        )

    if fmt == "docx":
        try:
            from app.services.export_from_markdown import markdown_to_docx
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="Dependências para DOCX não instaladas. Instale python-docx e Pillow no backend.",
            ) from exc
        out_bytes = await _run_export(markdown_to_docx, md_content, image_map=image_map)
        headers = {"Content-Disposition": 'attachment; filename="tutorial.docx"'}
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )

    if fmt == "pdf":
        try:
            from app.services.export_from_markdown import markdown_to_pdf
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="Dependências para PDF não instaladas. Instale reportlab e Pillow no backend.",
            ) from exc
        pdf_bytes = await _run_export(markdown_to_pdf, md_content, image_map=image_map)
        headers = {"Content-Disposition": 'attachment; filename="tutorial.pdf"'}
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers=headers,
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("tutorial.md", "\n".join(md_lines).strip() + "\n")
        for step_idx, image_bytes in step_index_to_image.items():
            zf.writestr(f"img/{prefix}{step_idx:02d}.png", image_bytes)

    zip_buffer.seek(0)

    headers = {"Content-Disposition": 'attachment; filename="clipbuilder_export.zip"'}
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)


# ---------------------------------------------------------------------------
# Document Enhancement with Gemini
# ---------------------------------------------------------------------------


@app.post("/enhance-document")
async def enhance_document(
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentAuthorizedUser,
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
    x_google_api_key: str | None = Header(default=None, alias="X-Google-Api-Key"),
):
    # Check Gemini permission
    _check_ai_permission(request.headers.get("authorization"), "gemini")

    # ── Credit debit (before AI call) ──
    _billing_user_id = _debit_user_credits(
        request.headers.get("authorization"), "/enhance-document"
    )

    """
    Transforma passos capturados em documento profissional estruturado usando Gemini.

    Espera JSON no body:
    {
        "title": "Título do Documento",
        "steps": [
            {"description": "Passo 1", "timestamp": "00:01:30", "has_image": true},
            {"description": "Passo 2", "timestamp": "00:02:15", "has_image": false}
        ]
    }

    Retorna:
    {
        "markdown": "# Documento estruturado em Markdown..."
    }

    O Markdown gerado segue o formato Doc Pro:
    - Cada passo com Objetivo e Procedimento
    - Callouts (> [!NOTE], > [!TIP], > [!WARNING])
    - Checklist de Verificação Final
    - Tabela de Problemas Comuns e Soluções
    """
    from app.services.enhance import enhance_document_with_gemini

    # Get API key (Gemini)
    api_key = _get_api_key(x_gemini_key or x_google_api_key)

    # Parse request body
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {exc}") from exc

    title = (body.get("title") or "Documento Sem Título").strip()
    template_id = body.get("template_id")  # wolbito_it, wolbito_pop, or None

    # ── Template permission enforcement ──
    if template_id:
        from app.admin.template_service import check_template_permission
        check_template_permission(user, template_id)

    logger.info(
        "[enhance-document] Received template_id=%r, title=%r", template_id, title
    )
    steps = body.get("steps", [])

    if not isinstance(steps, list):
        raise HTTPException(status_code=400, detail="Campo 'steps' deve ser uma lista")

    if len(steps) == 0:
        raise HTTPException(status_code=400, detail="Pelo menos um passo é necessário")

    # Validate steps — preserve all enriched fields so the AI prompt
    # receives title, userAction, expectedResult, observations, etc.
    validated_steps = []
    for i, step in enumerate(steps):
        if isinstance(step, str):
            validated_steps.append(
                {"description": step, "timestamp": "", "has_image": False}
            )
        elif isinstance(step, dict):
            validated_steps.append(
                {
                    "description": step.get("description", ""),
                    "has_image": step.get("has_image", False),
                    "title": step.get("title", ""),
                    "userAction": step.get("userAction", ""),
                    "expectedResult": step.get("expectedResult", ""),
                    "observations": step.get("observations", ""),
                }
            )
        else:
            raise HTTPException(status_code=400, detail=f"Passo {i + 1} inválido")

    # Call enhancement function (Gemini)
    try:
        enhanced_markdown = await _run_blocking(
            enhance_document_with_gemini,
            title=title,
            steps=validated_steps,
            api_key=api_key,
            model=DEFAULT_GEMINI_MODEL,
            template_id=template_id,
        )
    except RuntimeError as exc:
        _refund_user_credits(_billing_user_id, "/enhance-document")
        msg = str(exc).lower()
        if "quota" in msg or "limite" in msg or "429" in msg or "rate limit" in msg or "ratelimit" in msg:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        if "inválida" in msg or "permissão" in msg or "401" in msg or "403" in msg:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        _refund_user_credits(_billing_user_id, "/enhance-document")
        logger.error("Erro ao gerar documento com Gemini: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Erro ao gerar documento: {str(exc)[:200]}"
        ) from exc

    # Log Gemini usage for enhance_document
    background_tasks.add_task(
        log_ai_usage_background,
        user_id=user.get("sub") or user.get("id"),
        endpoint="/enhance-document",
        ai_provider="gemini",
        model=DEFAULT_GEMINI_MODEL,
    )
    return {"markdown": enhanced_markdown}


# ---------------------------------------------------------------------------
# Markdown to DOCX (conversion only, no Gemini)
# ---------------------------------------------------------------------------


@app.post("/markdown-to-docx")
async def markdown_to_docx_endpoint(
    request: Request,
    user: CurrentAuthorizedUser,
):
    """
    Converte markdown em ficheiro .docx.
    Body JSON: {
        "markdown": "...",
        "title": "opcional",
        "professional": true/false,
        "template_id": "clipbuilder_pro" | "wolbito_it" | "wolbito_pop" (opcional),
        "template_metadata": {                       (opcional – usado com templates corporativos)
            "document_code": "IT-TI-INF-0002",
            "revision": "00",
            "expiration_period": "1 ano",
            "elaboration_date": "14/08/2025",
            "responsible_elaboration": "Nome",
            "responsible_consensus": "Nome",
            "responsible_approval": "Nome"
        }
    }.

    Se template_id for um template corporativo (wolbito_it, wolbito_pop), usa o
    builder corporativo com cabeçalho, logo e rodapé de responsáveis.

    Se template_id for "clipbuilder_pro" ou ausente e professional=true (padrão),
    gera documento com formatação profissional (capa, sumário, títulos coloridos).

    Se professional=false, gera documento simples.

    Devolve o ficheiro .docx para download.
    """
    from app.services.export_from_markdown import markdown_to_docx, markdown_to_docx_pro

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {exc}") from exc

    markdown = body.get("markdown")
    if markdown is None:
        raise HTTPException(status_code=400, detail="Campo 'markdown' é obrigatório.")
    markdown = (markdown or "").strip()
    if not markdown:
        raise HTTPException(status_code=400, detail="O markdown está vazio.")

    title = (body.get("title") or "documento_profissional").strip()
    filename = f"{_safe_filename(title, 'documento_profissional')}.docx"

    # Default to professional mode (True)
    professional = body.get("professional", True)
    if isinstance(professional, str):
        professional = professional.lower() in ("true", "1", "yes", "sim")

    image_map = body.get("image_map")
    num_images = len(image_map) if isinstance(image_map, dict) else 0

    template_id = (body.get("template_id") or "").strip() or None
    template_metadata = body.get("template_metadata") or {}
    if not isinstance(template_metadata, dict):
        template_metadata = {}

    # ── Template permission enforcement ──
    if template_id:
        from app.admin.template_service import check_template_permission
        check_template_permission(user, template_id)

    logger.info(
        "[markdown-to-docx] template_id=%r, professional=%r, num_images=%d, body_size=%d bytes",
        template_id,
        professional,
        num_images,
        len(await request.body()),
    )

    try:
        if template_id and template_id != "clipbuilder_pro":
            # Use corporate template builder
            logger.info(
                "[markdown-to-docx] Using CORPORATE builder for template_id=%r",
                template_id,
            )
            from templates.corporate_docx import corporate_markdown_to_docx
            from templates.template_registry import get_template

            template = get_template(template_id)
            if template is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Template '{template_id}' não encontrado. Use GET /templates para listar os disponíveis.",
                )

            # Merge title into metadata
            meta = dict(template_metadata)
            meta.setdefault("title", title)

            out_bytes = await _run_export(
                corporate_markdown_to_docx,
                markdown=markdown,
                template=template,
                metadata=meta,
                image_map=image_map,
                title=title,
            )
        elif professional:
            logger.info(
                "[markdown-to-docx] Using PRO builder (template_id=%r, professional=True)",
                template_id,
            )
            out_bytes = await _run_export(
                markdown_to_docx_pro, markdown, title=title, image_map=image_map
            )
        else:
            logger.info(
                "[markdown-to-docx] Using BASIC builder (template_id=%r, professional=False)",
                template_id,
            )
            out_bytes = await _run_export(markdown_to_docx, markdown, image_map=image_map)
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Erro ao converter markdown para docx: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao exportar: {str(exc)[:200]}",
        ) from exc

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(out_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Markdown to PDF (conversion only, no Gemini)
# ---------------------------------------------------------------------------


@app.post("/markdown-to-pdf")
async def markdown_to_pdf_endpoint(request: Request):
    """
    Converte markdown em ficheiro .pdf.
    Body JSON: { "markdown": "...", "title": "opcional" }.
    Devolve o ficheiro .pdf para download.
    """
    from app.services.export_from_markdown import markdown_to_pdf_via_libreoffice

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {exc}") from exc

    markdown = body.get("markdown")
    if markdown is None:
        raise HTTPException(status_code=400, detail="Campo 'markdown' é obrigatório.")
    markdown = (markdown or "").strip()
    if not markdown:
        raise HTTPException(status_code=400, detail="O markdown está vazio.")

    title = (body.get("title") or "documento").strip()
    filename = f"{_safe_filename(title, 'documento')}.pdf"

    image_map = body.get("image_map")
    if image_map is not None and not isinstance(image_map, dict):
        image_map = None

    try:
        out_bytes = await _run_export(
            markdown_to_pdf_via_libreoffice,
            markdown,
            image_map=image_map,
            use_pro=True,
            title=title,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Erro ao converter markdown para pdf: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao exportar PDF: {str(exc)[:200]}",
        ) from exc

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(out_bytes),
        media_type="application/pdf",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Markdown to HTML (conversion only, no Gemini)
# ---------------------------------------------------------------------------


@app.post("/markdown-to-html")
async def markdown_to_html_endpoint(request: Request):
    """
    Converte markdown em ficheiro .html (capa, sumário, callouts, rodapé).
    Body JSON: { "markdown": "...", "title": "opcional", "subtitle": "opcional", "image_map": "opcional" }.
    Devolve o ficheiro .html para download.
    """
    try:
        from app.services.export_from_markdown import markdown_to_html
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Dependência para HTML não instalada. Instale markdown e beautifulsoup4 no backend.",
        ) from exc

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {exc}") from exc

    markdown = body.get("markdown")
    if markdown is None:
        raise HTTPException(status_code=400, detail="Campo 'markdown' é obrigatório.")
    markdown = (markdown or "").strip()

    title = (body.get("title") or "Documento").strip()
    subtitle = (body.get("subtitle") or "Documentação Técnica").strip()
    filename = f"{_safe_filename(title, 'Documento')}.html"
    image_map = body.get("image_map") or {}

    try:
        html_doc = await _run_export(
            markdown_to_html,
            markdown,
            image_map=image_map,
            output_path=None,
            title=title,
            subtitle=subtitle,
        )
    except Exception as exc:
        logger.error("Erro ao converter markdown para html: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Erro ao converter: {str(exc)[:200]}"
        ) from exc

    html_bytes = html_doc.encode("utf-8")
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(html_bytes),
        media_type="text/html; charset=utf-8",
        headers=headers,
    )


@app.post("/describe-gif")
async def describe_gif(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_context: str | None = Form(default=None),
    document_title: str | None = Form(default=None),
    model: str | None = Form(default=None),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
    x_google_api_key: str | None = Header(default=None, alias="X-Google-Api-Key"),
):
    """Analisa um GIF e devolve a legenda do passo gerada pelo Gemini.

    Multipart: file (GIF obrigatório), document_context e document_title
    opcionais.  A chave da API vem do header X-Gemini-Key ou da configuração do
    backend.  Resposta: {"description": "..."}
    """
    # Check Gemini permission
    _check_ai_permission(request.headers.get("authorization"), "gemini")

    # ── Credit debit (before AI call) ──
    _billing_user_id = _debit_user_credits(
        request.headers.get("authorization"), "/describe-gif"
    )

    """
    Analisa um GIF e devolve uma legenda/instrução de passo (Passo X) gerada pela IA Gemini.

    Multipart: file (GIF obrigatório), document_context (opcional), document_title (opcional).
    Header: X-Gemini-Api-Key (ou configuração no .env do backend).
    Resposta: { "description": "..." }
    """
    if not file.filename or not file.filename.lower().endswith((".gif",)):
        raise HTTPException(
            status_code=400,
            detail="Envie um arquivo GIF (extensão .gif).",
        )

    gif_bytes = await file.read()
    if len(gif_bytes) > MAX_GIF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"GIF muito grande. Máximo: {MAX_GIF_BYTES // (1024 * 1024)} MB.",
        )
    if len(gif_bytes) < 100:
        raise HTTPException(status_code=400, detail="Arquivo GIF inválido ou vazio.")

    api_key = _get_api_key(x_gemini_key or x_google_api_key)

    def work() -> str:
        return _describe_gif_with_gemini(
            gif_bytes=gif_bytes,
            api_key=api_key,
            model=model,
            document_context=document_context,
            document_title=document_title,
        )

    try:
        description = await anyio.to_thread.run_sync(work)
    except HTTPException:
        _refund_user_credits(_billing_user_id, "/describe-gif")
        raise
    except Exception as exc:
        _refund_user_credits(_billing_user_id, "/describe-gif")
        logger.error("describe-gif failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao analisar GIF com Gemini: {str(exc)[:200]}",
        ) from exc

    # Log Gemini usage for describe-gif
    background_tasks.add_task(
        log_ai_usage_background,
        authorization=request.headers.get("authorization"),
        endpoint="/describe-gif",
        ai_provider="gemini",
        model=model or "models/gemini-2.5-flash"
    )
    return {"description": (description or "").strip() or "GIF animado"}


# ---------------------------------------------------------------------------
# Format document like template (Gemini) and export as .docx or .pdf
# ---------------------------------------------------------------------------


@app.post("/format-and-export")
async def format_and_export(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None),
    markdown: str | None = Form(default=None),
    output_format: str = Form(default="docx"),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
    x_google_api_key: str | None = Header(default=None, alias="X-Google-Api-Key"),
):
    """Formata um documento no template passo a passo e exporta em .docx ou .pdf.

    Form: file (.md/.docx/.pdf) ou markdown, mais output_format (docx | pdf).
    """
    # Check Gemini permission
    _check_ai_permission(request.headers.get("authorization"), "gemini")

    # ── Credit debit (before AI call) ──
    _billing_user_id = _debit_user_credits(
        request.headers.get("authorization"), "/format-and-export"
    )

    """
    Lê documento (upload .md/.docx/.pdf ou texto markdown), formata via Gemini
    segundo o template passo a passo e devolve ficheiro .docx ou .pdf.

    Form: file (opcional), markdown (opcional), output_format (docx | pdf).
    Pelo menos um de file ou markdown é obrigatório.
    """
    from app.services.document_loader import extract_text_from_document
    from app.services.enhance import format_document_like_template
    from app.services.export_from_markdown import markdown_to_docx, markdown_to_pdf_via_libreoffice

    fmt = (output_format or "docx").strip().lower()
    if fmt not in ("docx", "pdf"):
        raise HTTPException(
            status_code=400,
            detail="output_format deve ser 'docx' ou 'pdf'.",
        )

    # Extrair texto (ficheiro ou markdown)
    try:
        raw_text = await extract_text_from_document(file=file, markdown_text=markdown)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not raw_text or not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail="O documento está vazio ou não foi possível extrair texto.",
        )

    # Formatar com Gemini (template passo a passo)
    api_key = _get_api_key(x_gemini_key or x_google_api_key)
    try:
        formatted_md = await _run_blocking(
            format_document_like_template,
            raw_text=raw_text,
            api_key=api_key,
        )
    except RuntimeError as exc:
        _refund_user_credits(_billing_user_id, "/format-and-export")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        _refund_user_credits(_billing_user_id, "/format-and-export")
        logger.error("Erro ao formatar documento com Gemini: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao formatar documento: {str(exc)[:200]}",
        ) from exc

    if not formatted_md or not formatted_md.strip():
        raise HTTPException(
            status_code=500,
            detail="Gemini devolveu resposta vazia.",
        )

    # Log Gemini usage for format-and-export
    background_tasks.add_task(
        log_ai_usage_background,
        authorization=request.headers.get("authorization"),
        endpoint="/format-and-export",
        ai_provider="gemini",
        model="gemini-format",
    )

    # Exportar para docx ou pdf
    try:
        if fmt == "docx":
            out_bytes = await _run_export(markdown_to_docx, formatted_md)
            filename = "manual.docx"
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            out_bytes = await _run_export(
                markdown_to_pdf_via_libreoffice,
                formatted_md,
                image_map=None,
                use_pro=True,
                title="Manual",
            )
            filename = "manual.pdf"
            media_type = "application/pdf"
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Erro ao exportar documento: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao exportar: {str(exc)[:200]}",
        ) from exc

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(out_bytes),
        media_type=media_type,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Generate Structured Documentation (Gemini JSON output)
# ---------------------------------------------------------------------------


@app.post("/generate-documentation")
async def generate_documentation(
    request: Request,
    background_tasks: BackgroundTasks,
    model: str = DEFAULT_GEMINI_MODEL,
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
    x_google_api_key: str | None = Header(default=None, alias="X-Google-Api-Key"),
):
    """Gera documentação técnica estruturada a partir dos passos capturados.

    Body JSON: title, steps (lista de {"description", "has_image"}) e
    output_format ("json" | "markdown" | "docx").
    """
    # Check Gemini permission
    _check_ai_permission(request.headers.get("authorization"), "gemini")

    # ── Credit debit (before AI call) ──
    _billing_user_id = _debit_user_credits(
        request.headers.get("authorization"), "/generate-documentation"
    )

    """
    Gera documentação técnica estruturada a partir de passos capturados.

    Body JSON:
    {
        "title": "Título do Documento",
        "steps": [{"description": "...", "has_image": true}],
        "output_format": "json" | "markdown" | "docx"
    }

    Retorna:
    - JSON: Objeto estruturado com visao_geral, passos, avisos, checklist, troubleshooting
    - Markdown: Documento formatado em Markdown
    - DOCX: Arquivo .docx para download
    """
    from app.services.enhance import generate_structured_documentation
    from app.services.export_from_markdown import structured_json_to_docx
    from templates.corporate_docx import corporate_structured_to_docx
    from templates.template_registry import get_template as get_doc_template

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {exc}") from exc

    title = (body.get("title") or "Documentação").strip()
    if not title:
        title = "Documentação"

    # ── Template support ──
    template_id = body.get("template_id")
    template_metadata = body.get("template_metadata") or {}
    logger.info(
        "[generate-documentation] template_id=%r, output_format=%s",
        template_id,
        body.get("output_format", "json"),
    )

    steps_raw = body.get("steps", [])
    if not steps_raw or not isinstance(steps_raw, list):
        raise HTTPException(
            status_code=400, detail="Campo 'steps' é obrigatório e deve ser uma lista."
        )

    # Validate and normalize steps
    validated_steps = []
    for i, step in enumerate(steps_raw):
        if isinstance(step, str):
            validated_steps.append({"description": step, "has_image": True})
        elif isinstance(step, dict):
            desc = step.get("description", "")
            if not isinstance(desc, str):
                raise HTTPException(
                    status_code=400,
                    detail=f"Passo {i + 1}: 'description' deve ser string.",
                )
            validated_steps.append(
                {
                    "description": desc,
                    "has_image": step.get("has_image", True),
                    "title": step.get("title", ""),
                    "userAction": step.get("userAction", ""),
                    "expectedResult": step.get("expectedResult", ""),
                    "observations": step.get("observations", ""),
                }
            )
        else:
            raise HTTPException(status_code=400, detail=f"Passo {i + 1} inválido.")

    # Extract images (base64) if provided
    images_raw = body.get("images")
    if images_raw and not isinstance(images_raw, list):
        # If single string, wrap in list? No, explicit list required.
        logger.warning("Campo 'images' recebido mas não é lista.")
        images_raw = None

    output_format = (body.get("output_format") or "json").strip().lower()
    if output_format not in ("json", "markdown", "docx"):
        raise HTTPException(
            status_code=400,
            detail="output_format deve ser 'json', 'markdown' ou 'docx'.",
        )

    # Get API key
    api_key = _get_api_key(x_gemini_key or x_google_api_key)

    # Generate structured documentation
    def work() -> dict:
        return generate_structured_documentation(
            title=title,
            steps=validated_steps,
            api_key=api_key,
            model=model,
            images_b64=images_raw,
        )

    try:
        structured_doc = await anyio.to_thread.run_sync(work)
    except RuntimeError as exc:
        _refund_user_credits(_billing_user_id, "/generate-documentation")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        _refund_user_credits(_billing_user_id, "/generate-documentation")
        logger.error("Erro ao gerar documentação estruturada: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Erro ao gerar documentação: {str(exc)[:200]}"
        ) from exc

    # Log Gemini usage for generate-documentation
    background_tasks.add_task(
        log_ai_usage_background,
        authorization=request.headers.get("authorization"),
        endpoint="/generate-documentation",
        ai_provider="gemini",
        model=model
    )

    # Return based on output_format
    if output_format == "json":
        return {"documentation": structured_doc}

    if output_format == "markdown":
        # Convert JSON to Markdown
        md_lines = []
        md_lines.append(f"# {title}")
        md_lines.append("")
        md_lines.append("## Visão Geral")
        md_lines.append(structured_doc.get("visao_geral", ""))
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

        for passo in structured_doc.get("passos", []):
            numero = passo.get("numero", 0)
            titulo = passo.get("titulo", f"Passo {numero}")
            md_lines.append(f"## Passo {numero}: {titulo}")
            md_lines.append("")
            md_lines.append("### Objetivo")
            md_lines.append(passo.get("objetivo", ""))
            md_lines.append("")
            md_lines.append("### Procedimento")
            for proc in passo.get("procedimento", []):
                md_lines.append(f"1. {proc}")
            md_lines.append("")
            if passo.get("imagem"):
                md_lines.append(f"![Passo {numero}]({passo['imagem']})")
                md_lines.append("")
            md_lines.append("---")
            md_lines.append("")

        # Avisos
        avisos = structured_doc.get("avisos", [])
        if avisos:
            for aviso in avisos:
                tipo = aviso.get("tipo", "NOTE").upper()
                texto = aviso.get("texto", "")
                md_lines.append(f"> [!{tipo}]")
                md_lines.append(f"> {texto}")
                md_lines.append("")

        # Checklist
        checklist = structured_doc.get("checklist", [])
        if checklist:
            md_lines.append("## Checklist de Verificação Final")
            md_lines.append("")
            md_lines.append("Antes de considerar o procedimento concluído, confirme:")
            md_lines.append("")
            for item in checklist:
                md_lines.append(f"- [ ] {item}")
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")

        # Troubleshooting
        troubleshooting = structured_doc.get("troubleshooting", [])
        if troubleshooting:
            md_lines.append("## Problemas Comuns e Soluções")
            md_lines.append("")
            md_lines.append("| Problema | Causa | Solução |")
            md_lines.append("|----------|-------|---------|")
            for item in troubleshooting:
                problema = item.get("problema", "")
                causa = item.get("causa", "")
                solucao = item.get("solucao", "")
                md_lines.append(f"| {problema} | {causa} | {solucao} |")
            md_lines.append("")

        return {"markdown": "\n".join(md_lines)}

    # DOCX output
    try:
        if template_id and template_id != "clipbuilder_pro":
            # Use corporate template builder
            corp_template = get_doc_template(template_id)
            if corp_template is not None:
                logger.info(
                    "[generate-documentation] Using CORPORATE structured builder for template_id=%r",
                    template_id,
                )
                meta = dict(template_metadata)
                meta.setdefault("title", title)
                out_bytes = await _run_export(
                    corporate_structured_to_docx,
                    data=structured_doc,
                    template=corp_template,
                    metadata=meta,
                    title=title,
                )
            else:
                logger.warning(
                    "[generate-documentation] Template '%s' not found, falling back to basic builder",
                    template_id,
                )
                out_bytes = await _run_export(
                    structured_json_to_docx, structured_doc, title=title
                )
        else:
            out_bytes = await _run_export(
                structured_json_to_docx, structured_doc, title=title
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Erro ao converter para DOCX: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Erro ao exportar DOCX: {str(exc)[:200]}"
        ) from exc

    filename = f"{_safe_filename(title, 'documentacao')}.docx"

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(out_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


def _describe_gif_with_gemini(
    *,
    gif_bytes: bytes,
    api_key: str,
    model: str | None = None,
    document_context: str | None = None,
    document_title: str | None = None,
) -> str:
    _configure_genai(api_key)
    import google.generativeai as genai
    model_name = model or DEFAULT_GEMINI_MODEL
    normalized = model_name if model_name.startswith("models/") else f"models/{model_name}"

    system_instruction = (
        "Você é um especialista em Documentação Técnica de Software. "
        "Seu objetivo é criar tutoriais passo a passo claros, diretos e CONTEXTUALIZADOS. "
        "Responda sempre em português do Brasil (pt-BR)."
    )
    task_instruction = (
        "Você está vendo uma sequência de imagens extraídas de um GIF animado. "
        "Analise para entender a ação sendo executada."
    )
    formatting_instruction = (
        "Gere UMA instrução em modo imperativo."
    )
    parts = [system_instruction, task_instruction, formatting_instruction]

    if document_context:
        parts.append(f"CONTEXTO:\n{document_context.strip()}")
    if document_title:
        parts.append(f"TÍTULO:\n{document_title.strip()}")

    prompt = "\n\n".join(parts)

    try:
        client = genai.GenerativeModel(model_name=normalized)
        content_parts = [prompt, {"mime_type": "image/gif", "data": gif_bytes}]
        response = client.generate_content(content_parts)
        return response.text or ""
    except Exception as exc:
        raise RuntimeError(f"Erro ao processar GIF com Gemini: {exc}") from exc
