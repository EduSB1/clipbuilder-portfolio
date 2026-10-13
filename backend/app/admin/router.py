"""Admin API router – user management, dashboard, groups, settings."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from datetime import UTC
from pathlib import Path

import anyio
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.admin import crud
from app.admin.dashboard.router import router as dashboard_router
from app.admin.dependencies import RequireAdmin
from app.admin.groups.router import router as groups_router
from app.admin.schemas import (
    CreditAdjustRequest,
    CreditInfoResponse,
    PermissionUpdate,
    PlanUpdate,
    RoleUpdate,
    TransactionOut,
    UsageStatsOut,
    UserCreate,
    UserListResponse,
    UserOut,
    UserUpdate,
    YoutubeCookieUploadResponse,
)
from app.admin.settings.router import router as settings_router
from app.auth import clerk_client
from app.billing import service as credit_service
from app.core.constants import (
    ADMIN_DEFAULT_PAGE_SIZE,
    ADMIN_MAX_PAGE_SIZE,
    BGUTIL_DIAGNOSTIC_TIMEOUT_SECONDS,
    CLERK_SYNC_USER_LIMIT,
    CREDIT_ADJUSTMENT_TRANSACTION_LIMIT,
    DEFAULT_CREDIT_TRANSACTION_LIMIT,
    MAX_CREDIT_TRANSACTION_LIMIT,
    YTDLP_DIAGNOSTIC_TIMEOUT_SECONDS,
)
from app.database import get_db

logger = logging.getLogger("clipbuilder")

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(dashboard_router)
router.include_router(groups_router)
router.include_router(settings_router)


# ── List / Detail ─────────────────────────────────────────────────────


@router.get("/users", response_model=UserListResponse)
def list_users(
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(ADMIN_DEFAULT_PAGE_SIZE, ge=1, le=ADMIN_MAX_PAGE_SIZE),
    search: str | None = Query(None),
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
    status: str | None = Query(
        None,
        description="Filter: ativos | desativados | excluidos | todos",
    ),
):
    users, total = crud.get_users(
        db,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        is_active=is_active,
        status=status,
    )
    return UserListResponse(users=users, total=total, page=page, page_size=page_size)


@router.get("/users/clerk-pending")
def get_clerk_pending_users(_admin: RequireAdmin, db: Session = Depends(get_db)):
    """Return Clerk users not yet imported into the local database.

    Polls the Clerk API and cross-checks against the local DB so that
    admins can review who registered via Clerk but hasn't been approved/synced yet.
    """
    from datetime import datetime

    clerk_users = clerk_client.list_clerk_users(limit=CLERK_SYNC_USER_LIMIT)

    pending = []
    for cu in clerk_users:
        emails = cu.get("email_addresses", [])
        if not emails:
            continue
        email = emails[0].get("email_address")
        if not email:
            continue

        # Skip users already present in the local DB
        if crud.get_user_by_email(db, email):
            continue

        # Convert Clerk millisecond timestamps to ISO strings
        def _ms_to_iso(ms: int | None) -> str | None:
            if not ms:
                return None
            return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()

        pending.append(
            {
                "clerk_id": cu.get("id"),
                "email": email,
                "full_name": f"{cu.get('first_name') or ''} {cu.get('last_name') or ''}".strip(),
                "created_at": _ms_to_iso(cu.get("created_at")),
                "last_sign_in_at": _ms_to_iso(cu.get("last_sign_in_at")),
                "image_url": cu.get("image_url"),
                "username": cu.get("username"),
            }
        )

    return {"pending": pending, "total": len(pending)}


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: str, _admin: RequireAdmin, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user


# ── Create / Update ───────────────────────────────────────────────────


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, _admin: RequireAdmin, db: Session = Depends(get_db)):
    existing = crud.get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=400, detail="E-mail já registrado")

    # Smart Creation: Find clerk_id if they exist in Clerk
    clerk_user = clerk_client.get_clerk_user_by_email(body.email)
    clerk_id = clerk_user.get("id") if clerk_user else None

    # Bidirectional Sync: Create in Clerk if it doesn't exist
    if not clerk_id:
        try:
            clerk_id = clerk_client.create_clerk_user(
                email=body.email, password=body.password, full_name=body.full_name
            )
        except ValueError as e:
            # Re-raise Clerk validation errors (like weak password) to the frontend
            raise HTTPException(status_code=400, detail=str(e)) from e

    user = crud.create_user(
        db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        role=body.role,
        clerk_id=clerk_id,
    )
    return user


@router.post("/users/sync")
def sync_clerk_users(_admin: RequireAdmin, db: Session = Depends(get_db)):
    """Sync users from Clerk to local DB.

    Logic:
    - If user exists in DB: link clerk_id if missing.
    - If user doesn't exist: create new entry ONLY if not soft-deleted.
    """
    clerk_users = clerk_client.list_clerk_users(limit=CLERK_SYNC_USER_LIMIT)
    synced_count = 0
    linked_count = 0

    for cu in clerk_users:
        emails = cu.get("email_addresses", [])
        if not emails:
            continue
        email = emails[0].get("email_address")
        if not email:
            continue

        clerk_id = cu.get("id")

        # Check if user already exists
        user = crud.get_user_by_email(db, email)
        if user:
            # If they exist but have no clerk_id, link them
            if not user.clerk_id:
                crud.update_user(db, user, clerk_id=clerk_id)
                linked_count += 1
            continue

        # Ensure they aren't soft-deleted (get_user_by_email might return deleted records)
        # We only want to create new records for people NOT in the trash.
        if user and user.deleted_at is not None:
            continue

        crud.create_user(
            db,
            email=email,
            full_name=f"{cu.get('first_name', '')} {cu.get('last_name', '')}".strip(),
            clerk_id=clerk_id,
        )
        synced_count += 1

    return {
        "message": "Sincronização concluída",
        "synced": synced_count,
        "linked": linked_count,
    }


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdate,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Check email uniqueness if changing
    if body.email is not None:
        other = crud.get_user_by_email(db, body.email)
        if other and other.id != user.id:
            raise HTTPException(
                status_code=400, detail="E-mail já em uso por outro usuário"
            )

    user = crud.update_user(
        db, user, email=body.email, password=body.password, full_name=body.full_name
    )
    return user


# ── Status Management (Deactivate / Reactivate / Soft Delete / Restore) ──


@router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: str, _admin: RequireAdmin, db: Session = Depends(get_db)):
    """Set user status to 'desativado'. Prevents login."""
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.deleted_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Usuário está na lixeira. Restaure-o antes de desativar.",
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuário já está desativado")
    if user.role == "admin" and _admin.id == user.id:
        raise HTTPException(
            status_code=400, detail="Você não pode desativar a si mesmo"
        )
    user = crud.deactivate_user(db, user)
    return user


@router.post("/users/{user_id}/reactivate", response_model=UserOut)
def reactivate_user(user_id: str, _admin: RequireAdmin, db: Session = Depends(get_db)):
    """Re-enable a deactivated or soft-deleted user back to 'ativo'."""
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.is_active and user.deleted_at is None:
        raise HTTPException(status_code=400, detail="Usuário já está ativo")
    user = crud.reactivate_user(db, user)
    return user


@router.delete("/users/{user_id}", response_model=UserOut)
def soft_delete_user(user_id: str, _admin: RequireAdmin, db: Session = Depends(get_db)):
    """Soft delete – fills deleted_at. User disappears from default listings."""
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Usuário já está na lixeira")
    if user.role == "admin" and _admin.id == user.id:
        raise HTTPException(status_code=400, detail="Você não pode remover a si mesmo")
    user = crud.soft_delete_user(db, user)
    return user


@router.post("/users/{user_id}/restore", response_model=UserOut)
def restore_user(user_id: str, _admin: RequireAdmin, db: Session = Depends(get_db)):
    """Undo soft delete – clears deleted_at and reactivates."""
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.deleted_at is None:
        raise HTTPException(status_code=400, detail="Usuário não está na lixeira")
    user = crud.restore_user(db, user)
    return user


# ── Permissions / Role ────────────────────────────────────────────────


@router.put("/users/{user_id}/permissions", response_model=UserOut)
def update_permissions(
    user_id: str,
    body: PermissionUpdate,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    crud.update_permissions(
        db,
        user,
        can_use_gemini=body.can_use_gemini,
        can_use_whisper=body.can_use_whisper,
        max_video_size_gb=body.max_video_size_gb,
        can_export_html=body.can_export_html,
        can_export_docx=body.can_export_docx,
        can_export_md=body.can_export_md,
        can_export_pdf=body.can_export_pdf,
        allowed_templates=body.allowed_templates,
    )
    db.refresh(user)
    return user


@router.put("/users/{user_id}/role", response_model=UserOut)
def update_role(
    user_id: str,
    body: RoleUpdate,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user = crud.update_role(db, user, body.role)
    return user


@router.put("/users/{user_id}/plan", response_model=UserOut)
def update_plan(
    user_id: str,
    body: PlanUpdate,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user = crud.update_plan(db, user, body.plan)
    return user


# ── Credit Management ─────────────────────────────────────────────────


@router.get("/users/{user_id}/credits", response_model=CreditInfoResponse)
def get_user_credits(
    user_id: str,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
    limit: int = Query(
        DEFAULT_CREDIT_TRANSACTION_LIMIT, ge=1, le=MAX_CREDIT_TRANSACTION_LIMIT
    ),
):
    """Return credit balance and transaction history for a user."""
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    account = credit_service.get_or_create_account(db, user_id)
    transactions = credit_service.get_transactions(db, user_id, limit=limit)

    return CreditInfoResponse(
        user_id=user_id,
        credits_balance=account.credits_balance,
        total_credits_purchased=account.total_credits_purchased,
        total_credits_used=account.total_credits_used,
        transactions=[TransactionOut.model_validate(t) for t in transactions],
    )


@router.post("/users/{user_id}/credits", response_model=CreditInfoResponse)
def adjust_user_credits(
    user_id: str,
    body: CreditAdjustRequest,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    """Admin manually adds or removes credits for a user."""
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if body.amount == 0:
        raise HTTPException(status_code=400, detail="Valor não pode ser zero")

    if body.amount > 0:
        credit_service.add_credits(
            db,
            user_id=user_id,
            amount=body.amount,
            type_=body.type,
            description=body.description,
        )
    else:
        # Negative amount — debit (force, no 402 check: admin override)
        account = credit_service.get_or_create_account(db, user_id)
        from app.admin.models import CreditTransaction

        account.credits_balance += body.amount  # body.amount is negative
        account.total_credits_used += abs(body.amount)
        tx = CreditTransaction(
            user_id=user_id,
            amount=body.amount,
            type=body.type,
            description=body.description,
        )
        db.add(tx)
        db.commit()
        db.refresh(account)

    account = credit_service.get_or_create_account(db, user_id)
    transactions = credit_service.get_transactions(
        db, user_id, limit=CREDIT_ADJUSTMENT_TRANSACTION_LIMIT
    )

    return CreditInfoResponse(
        user_id=user_id,
        credits_balance=account.credits_balance,
        total_credits_purchased=account.total_credits_purchased,
        total_credits_used=account.total_credits_used,
        transactions=[TransactionOut.model_validate(t) for t in transactions],
    )


# ── Usage Stats ───────────────────────────────────────────────────────


@router.get("/users/{user_id}/usage-stats", response_model=UsageStatsOut)
def usage_stats(user_id: str, _admin: RequireAdmin, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return crud.get_usage_stats(db, user_id)


# ── YouTube / yt-dlp Diagnostic ──────────────────────────────────────


def _ytdlp_cmd_diagnostic() -> list[str]:
    """Return the yt-dlp command (binary or python module)."""
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]


@router.get("/youtube-diagnostic")
def youtube_diagnostic(_admin: RequireAdmin):
    """Return a comprehensive diagnostic of the YouTube / yt-dlp configuration.

    Checks yt-dlp version, cookies file, PO Token plugin, proxy, and browser
    cookies.  Returns a recommended action when the configuration is incomplete.

    The most reliable long-term fix for VPS IP bans is configuring
    CLIPBUILDER_YTDLP_PROXY with a residential proxy.
    Providers: Bright Data, Oxylabs, Smartproxy.
    Format: http://user:pass@host:port  or  socks5://user:pass@host:port
    """

    # ── 1. yt-dlp version ────────────────────────────────────────────
    ytdlp_version: str | None = None
    try:
        cmd = _ytdlp_cmd_diagnostic() + ["--version"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=YTDLP_DIAGNOSTIC_TIMEOUT_SECONDS,
        )
        if proc.returncode == 0:
            ytdlp_version = (proc.stdout or "").strip() or None
    except Exception as exc:
        logger.debug("youtube-diagnostic: yt-dlp version check failed: %s", exc)

    # ── 2. Cookies file ──────────────────────────────────────────────
    cookies_file_env = (os.getenv("CLIPBUILDER_YTDLP_COOKIES_FILE") or "").strip()
    cookies_file_configured = bool(cookies_file_env)
    cookies_file_exists = False
    cookies_file_lines = 0
    if cookies_file_configured:
        try:
            p = Path(cookies_file_env).expanduser()
            if not p.is_absolute():
                # Resolve relative to the backend directory (where main.py lives)
                backend_dir = Path(__file__).resolve().parent.parent
                p = (backend_dir / p).resolve()
            if p.exists() and p.is_file():
                cookies_file_exists = True
                cookies_file_lines = sum(
                    1 for _ in p.open(encoding="utf-8", errors="ignore")
                )
        except Exception as exc:
            logger.debug("youtube-diagnostic: cookies file check failed: %s", exc)

    # ── 3. Browser cookies ───────────────────────────────────────────
    browser_cookies_configured = bool(
        (os.getenv("CLIPBUILDER_YTDLP_COOKIES_FROM_BROWSER") or "").strip()
    )

    # ── 4. Proxy ─────────────────────────────────────────────────────
    proxy_env = (os.getenv("CLIPBUILDER_YTDLP_PROXY") or "").strip()
    proxy_configured = bool(proxy_env)

    # ── 5. PO Token plugin ───────────────────────────────────────────
    po_token_plugin_installed = False
    try:
        import importlib

        importlib.import_module("yt_dlp_plugins")
        po_token_plugin_installed = True
    except ImportError:
        pass

    if not po_token_plugin_installed:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "show", "bgutil-ytdlp-pot-provider"],
                capture_output=True,
                text=True,
                timeout=BGUTIL_DIAGNOSTIC_TIMEOUT_SECONDS,
            )
            po_token_plugin_installed = proc.returncode == 0
        except Exception:
            pass

    # ── 6. PO Token extractor URL ────────────────────────────────────
    po_token_extractor_url = (
        os.getenv("CLIPBUILDER_YTDLP_PO_TOKEN_EXTRACTOR_URL") or ""
    ).strip()
    po_token_extractor_configured = bool(po_token_extractor_url)

    # ── Build recommended action ─────────────────────────────────────
    recommended_action: str | None = None
    if (
        not cookies_file_exists
        and not browser_cookies_configured
        and not proxy_configured
    ):
        recommended_action = (
            "Nenhuma estratégia de autenticação forte está configurada. "
            "Recomendação: configure um proxy residencial via CLIPBUILDER_YTDLP_PROXY "
            "(ex: http://user:pass@host:port ou socks5://user:pass@host:port). "
            "Provedores: Bright Data, Oxylabs, Smartproxy. "
            "Alternativa: instale cookies via ./setup_youtube_cookies.sh"
        )
    elif cookies_file_configured and not cookies_file_exists:
        recommended_action = (
            f"Arquivo de cookies configurado ({cookies_file_env}) mas não encontrado. "
            "Execute ./setup_youtube_cookies.sh para instalar os cookies."
        )
    elif cookies_file_exists and not proxy_configured:
        recommended_action = (
            "Cookies instalados. Para maior confiabilidade, adicione também "
            "um proxy residencial via CLIPBUILDER_YTDLP_PROXY."
        )
    elif proxy_configured and not cookies_file_exists:
        recommended_action = (
            "Proxy configurado. Para maior confiabilidade, instale também "
            "cookies via ./setup_youtube_cookies.sh"
        )

    return {
        "ytdlp_version": ytdlp_version,
        "ytdlp_installed": ytdlp_version is not None,
        "cookies_file_configured": cookies_file_configured,
        "cookies_file_exists": cookies_file_exists,
        "cookies_file_lines": cookies_file_lines,
        "browser_cookies_configured": browser_cookies_configured,
        "proxy_configured": proxy_configured,
        "po_token_plugin_installed": po_token_plugin_installed,
        "po_token_extractor_configured": po_token_extractor_configured,
        "recommended_action": recommended_action,
    }


@router.post("/youtube-cookies", response_model=YoutubeCookieUploadResponse)
async def upload_youtube_cookies(
    _admin: RequireAdmin,
    file: UploadFile = File(...),
):
    """Upload a cookies.txt file for YouTube authentication.

    The file is saved to /app/data/cookies.txt (the path expected by yt-dlp
    as configured in docker-compose).
    """
    if not file.filename.endswith(".txt"):
        raise HTTPException(
            status_code=400, detail="O arquivo deve ser um .txt (formato Netscape)."
        )

    # Resolve target path (standard location in Docker volume)
    target_path = Path("/app/data/cookies.txt")

    # Ensure directory exists (should be ensured by Docker, but let's be safe)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        content = await file.read()
        # Basic validation of Netscape format
        text = content.decode("utf-8", errors="ignore")
        if not any(
            k in text.lower() for k in ["youtube.com", "google.com", "# netscape"]
        ):
            raise HTTPException(
                status_code=400,
                detail="O arquivo não parece ser um cookies.txt do YouTube válido. Certifique-se de que exportou no formato Netscape.",
            )

        # Arquivo pequeno, mas a escrita sai do event loop por consistência com
        # o restante da API — nenhum handler async toca o disco diretamente.
        await anyio.to_thread.run_sync(Path(target_path).write_bytes, content)

        line_count = text.count("\n")

        logger.info("Admin: YouTube cookies updated via UI (%d lines)", line_count)

        return {
            "success": True,
            "message": f"Cookies instalados com sucesso ({line_count} linhas).",
            "lines": line_count,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to upload YouTube cookies: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Erro ao salvar cookies: {str(exc)}"
        ) from exc


# ── Template Management (Admin) ──────────────────────────────────────


@router.get("/templates")
def admin_list_templates(
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    """List all templates with user access counts."""
    from app.admin.template_service import get_template_with_user_count

    templates = get_template_with_user_count(db)
    return {"templates": templates}


@router.post("/templates")
def admin_create_template(
    _admin: RequireAdmin,
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Create a new custom template."""
    from app.admin.template_service import _row_to_dict, create_template

    row = create_template(db, body)
    return {"template": _row_to_dict(row), "message": "Template criado com sucesso."}


@router.delete("/templates/{template_id}")
def admin_delete_template(
    template_id: str,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    """Soft-delete a custom template (built-in templates cannot be deleted)."""
    from app.admin.template_service import delete_template

    delete_template(db, template_id)
    return {"message": f"Template '{template_id}' excluído com sucesso."}

