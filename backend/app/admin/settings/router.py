"""Settings API router."""

from __future__ import annotations

import logging
import smtplib
import socket
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.admin.dependencies import RequireAdmin
from app.admin.settings.schemas import SettingItem, SettingsUpdate
from app.admin.settings.service import (
    get_setting_value,
    get_settings_by_category,
    seed_settings,
    update_settings,
)
from app.core.constants import (
    SMTP_CONNECTION_TIMEOUT_SECONDS,
    SMTP_SSL_CONNECTION_TIMEOUT_SECONDS,
)
from app.database import get_db

logger = logging.getLogger("clipbuilder")

router = APIRouter(prefix="/settings", tags=["admin-settings"])


# ── Settings CRUD ─────────────────────────────────────────────────────


@router.get("", response_model=list[SettingItem])
def list_settings(
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
    category: str | None = Query(
        None,
        description="Filter by category: smtp, ai, storage, security, features",
    ),
):
    seed_settings(db)
    rows = get_settings_by_category(db, category)
    return [SettingItem(**r) for r in rows]


@router.put("")
def update_settings_endpoint(
    body: SettingsUpdate,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    update_settings(db, body.settings)
    return {"ok": True}


# ── SMTP Diagnostic ──────────────────────────────────────────────────


class SmtpDiagnosticRequest(BaseModel):
    to_email: str
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    use_tls: bool | None = None
    from_email: str | None = None


class SmtpDiagnosticStep(BaseModel):
    step: int
    label: str
    status: str  # "running" | "success" | "error" | "warning" | "skipped"
    message: str
    duration_ms: int | None = None


class SmtpDiagnosticResponse(BaseModel):
    success: bool
    steps: list[SmtpDiagnosticStep]
    summary: str


def _resolve_smtp_config(body: SmtpDiagnosticRequest) -> dict:
    """Merge request body with saved DB/env settings as fallback."""
    import os

    def _db(key: str) -> str:
        try:
            return get_setting_value("smtp", key) or ""
        except Exception:
            return ""

    host = (
        (body.host or "").strip()
        or _db("host")
        or os.getenv("SMTP_HOST", "smtp.gmail.com")
    )
    port_str = (
        str(body.port)
        if body.port is not None
        else (_db("port") or os.getenv("SMTP_PORT", "587"))
    )
    try:
        port = int(port_str)
    except (ValueError, TypeError):
        port = 587
    username = (
        (body.username or "").strip() or _db("username") or os.getenv("SMTP_USER", "")
    )
    password = (
        (body.password or "").strip() or _db("password") or os.getenv("SMTP_PASS", "")
    )
    from_email = (
        (body.from_email or "").strip()
        or _db("from_email")
        or os.getenv("SMTP_FROM_EMAIL", "")
        or username
    )

    if body.use_tls is not None:
        use_tls = body.use_tls
    else:
        db_tls = _db("use_tls")
        use_tls = db_tls.lower() != "false" if db_tls else True

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "use_tls": use_tls,
        "from_email": from_email,
    }


def _is_office365(host: str) -> bool:
    """Detect if the SMTP host is Microsoft Office 365 / Exchange Online."""
    h = (host or "").lower()
    return any(
        keyword in h
        for keyword in (
            "office365",
            "outlook",
            "microsoft",
            "exchange",
            "hotmail",
            "live.com",
        )
    )


def _smtp_login_robust(
    server: smtplib.SMTP | smtplib.SMTP_SSL, username: str, password: str, host: str
) -> None:
    """Login with explicit AUTH method selection.

    Office 365 (and some other providers) advertise CRAM-MD5 but reject it,
    causing Python's default ``server.login()`` to fail with 535.  This helper
    tries AUTH methods in an order that works for O365:
        1. AUTH LOGIN
        2. AUTH PLAIN
        3. Default (fallback to ``server.login()``)
    """
    import base64

    # If it's an Office 365 host, skip CRAM-MD5 entirely and use LOGIN/PLAIN.
    if _is_office365(host):
        logger.info(
            "SMTP auth: Office 365 detected — forcing AUTH LOGIN (skip CRAM-MD5)"
        )

        # Try AUTH LOGIN first (most reliable for O365)
        try:
            # AUTH LOGIN is a two-step exchange
            code, resp = server.docmd("AUTH", "LOGIN")
            if code == 334:
                code, resp = server.docmd(base64.b64encode(username.encode()).decode())
            if code == 334:
                code, resp = server.docmd(base64.b64encode(password.encode()).decode())
            if code == 235:
                logger.info("SMTP auth: AUTH LOGIN succeeded for %s", username)
                return
            # If we got here with a non-235 code, raise an error
            raise smtplib.SMTPAuthenticationError(code, resp)
        except smtplib.SMTPAuthenticationError:
            raise  # re-raise auth errors as-is
        except Exception as exc_login:
            logger.warning(
                "SMTP auth: AUTH LOGIN failed (%s), trying AUTH PLAIN...", exc_login
            )

        # Try AUTH PLAIN as fallback
        try:
            credentials = base64.b64encode(
                f"\x00{username}\x00{password}".encode()
            ).decode()
            code, resp = server.docmd("AUTH", f"PLAIN {credentials}")
            if code == 235:
                logger.info("SMTP auth: AUTH PLAIN succeeded for %s", username)
                return
            raise smtplib.SMTPAuthenticationError(code, resp)
        except smtplib.SMTPAuthenticationError:
            raise
        except Exception as exc_plain:
            logger.warning(
                "SMTP auth: AUTH PLAIN also failed (%s), falling back to default login",
                exc_plain,
            )

    # Default: let smtplib pick the best method (works for Gmail and most others)
    server.login(username, password)
    logger.info("SMTP auth: default login() succeeded for %s", username)


def _friendly_smtp_error(exc: Exception, cfg: dict) -> str:
    """Map SMTP / socket exceptions to user-friendly Portuguese messages."""
    msg = str(exc).lower()
    exc_str = str(exc)

    # Authentication errors
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        code = getattr(exc, "smtp_code", 0)
        if cfg["host"] == "smtp.gmail.com":
            return (
                f"Autenticação falhou (código {code}). "
                "Para Gmail, use uma Senha de App de 16 dígitos "
                "(não a senha normal da conta). "
                "Verifique se a Verificação em 2 Etapas está ativada."
            )
        if _is_office365(cfg["host"]):
            return (
                f"Autenticação falhou (código {code}). "
                "Para Office 365 / Outlook, verifique:\n"
                "1) A senha está correta (se acabou de redefinir, aguarde 1-2 min para propagar).\n"
                "2) 'Authenticated SMTP' está habilitado no admin do M365 "
                "(Admin Center → Usuários → Mail → Manage email apps).\n"
                "3) 'Security Defaults' NÃO estão ativados no Azure AD/Entra ID "
                "(Security Defaults bloqueiam autenticação básica SMTP).\n"
                "4) Não há política de Acesso Condicional bloqueando Legacy Authentication.\n"
                "5) Se MFA está ativo, crie uma App Password em https://mysignins.microsoft.com/security-info"
            )
        return (
            f"Autenticação falhou (código {code}). "
            "Verifique o usuário e senha SMTP. "
            "Se seu provedor exige senha de aplicativo, gere uma nas configurações de segurança."
        )

    # Connection refused
    if isinstance(exc, (ConnectionRefusedError, smtplib.SMTPConnectError)):
        return (
            f"Conexão recusada em {cfg['host']}:{cfg['port']}. "
            "A porta pode estar bloqueada pelo firewall do servidor ou o host SMTP está incorreto."
        )

    # Timeout
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return (
            f"Timeout: O servidor SMTP ({cfg['host']}:{cfg['port']}) "
            "demorou muito para responder. "
            "Verifique se o host e porta estão corretos e se não há firewall bloqueando."
        )

    # DNS / hostname resolution
    if isinstance(exc, socket.gaierror):
        return (
            f"Não foi possível resolver o host '{cfg['host']}'. "
            "Verifique se o endereço do servidor SMTP está correto."
        )

    # SSL/TLS errors
    if isinstance(exc, ssl.SSLError):
        return (
            f"Erro de SSL/TLS ao conectar em {cfg['host']}:{cfg['port']}. "
            "Verifique se a porta é compatível com o tipo de conexão "
            "(porta 465 = SSL implícito, porta 587 = STARTTLS)."
        )

    # Connection reset
    if isinstance(exc, ConnectionResetError):
        return (
            f"Conexão resetada pelo servidor {cfg['host']}:{cfg['port']}. "
            "O servidor pode ter rejeitado a conexão. Verifique host, porta e configuração TLS."
        )

    # SMTP sender/recipient rejected
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "O servidor rejeitou o(s) destinatário(s). Verifique o endereço de e-mail de destino."

    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (
            "O servidor rejeitou o remetente. "
            "Verifique se o 'Email remetente' corresponde a uma conta autorizada."
        )

    # Generic SMTP
    if isinstance(exc, smtplib.SMTPException):
        # Try to extract meaningful info
        if "starttls" in msg:
            return (
                "O servidor não suporta STARTTLS nesta porta. "
                "Tente desabilitar TLS ou usar a porta 465 (SSL direto)."
            )
        if "authentication" in msg or "auth" in msg:
            return f"Erro de autenticação SMTP: {exc_str[:200]}"
        return f"Erro SMTP: {exc_str[:200]}"

    # OS-level errors
    if isinstance(exc, OSError):
        if "errno 111" in msg or "connection refused" in msg:
            return (
                f"Porta {cfg['port']} bloqueada pelo firewall do servidor "
                f"ou serviço indisponível em {cfg['host']}."
            )
        if "errno 110" in msg or "timed out" in msg:
            return (
                f"Timeout: O servidor SMTP ({cfg['host']}:{cfg['port']}) "
                "demorou muito para responder."
            )
        return f"Erro de rede: {exc_str[:200]}"

    return f"Erro inesperado: {exc_str[:200]}"


@router.post("/smtp-diagnostic", response_model=SmtpDiagnosticResponse)
def smtp_diagnostic(body: SmtpDiagnosticRequest, _admin: RequireAdmin):
    """Run a step-by-step SMTP diagnostic and optionally send a test email.

    Returns detailed log entries for each phase:
    1. Validar configuração
    2. Conectar ao servidor
    3. Negociar TLS/SSL
    4. Autenticar
    5. Enviar e-mail de teste
    """
    steps: list[SmtpDiagnosticStep] = []
    step_num = 0
    overall_success = False

    cfg = _resolve_smtp_config(body)
    to_email = (body.to_email or "").strip()

    # ── Step 1: Validate configuration ────────────────────────────────
    step_num += 1
    t0 = time.monotonic()

    validation_warnings: list[str] = []
    validation_errors: list[str] = []

    if not cfg["host"]:
        validation_errors.append("Host SMTP não configurado.")
    if not cfg["username"]:
        validation_errors.append("Usuário SMTP não configurado.")
    if not cfg["password"]:
        validation_errors.append("Senha SMTP não configurada.")
    if not to_email:
        validation_errors.append("E-mail de destino não informado.")
    elif "@" not in to_email or "." not in to_email.split("@")[-1]:
        validation_errors.append(f"E-mail de destino inválido: {to_email}")
    if not cfg["from_email"]:
        validation_warnings.append(
            "Email remetente não configurado. Usando o usuário SMTP como remetente."
        )
        cfg["from_email"] = cfg["username"]

    # Gmail-specific warnings
    if cfg["host"] == "smtp.gmail.com":
        pwd = cfg["password"]
        # App passwords are 16 chars (with or without spaces)
        clean_pwd = pwd.replace(" ", "")
        if len(clean_pwd) != 16 and pwd:
            validation_warnings.append(
                "Gmail detectado: A senha não parece ser uma Senha de App (16 dígitos). "
                "Senhas normais são bloqueadas pelo Google. "
                "Gere uma em: https://myaccount.google.com/apppasswords"
            )
        if cfg["port"] not in (587, 465):
            validation_warnings.append(
                f"Gmail detectado: Porta {cfg['port']} é incomum. "
                "O Gmail usa 587 (STARTTLS) ou 465 (SSL)."
            )

    elapsed = int((time.monotonic() - t0) * 1000)

    if validation_errors:
        steps.append(
            SmtpDiagnosticStep(
                step=step_num,
                label="Validar configuração",
                status="error",
                message="Configuração incompleta: " + " | ".join(validation_errors),
                duration_ms=elapsed,
            )
        )
        return SmtpDiagnosticResponse(
            success=False,
            steps=steps,
            summary="Diagnóstico interrompido: configuração SMTP incompleta.",
        )

    status_1 = "warning" if validation_warnings else "success"
    msg_1 = (
        f"Host: {cfg['host']}:{cfg['port']} | Usuário: {cfg['username']} | "
        f"TLS: {'Sim' if cfg['use_tls'] else 'Não'} | "
        f"Remetente: {cfg['from_email']} | Destino: {to_email}"
    )
    if validation_warnings:
        msg_1 += " ⚠ " + " | ".join(validation_warnings)

    steps.append(
        SmtpDiagnosticStep(
            step=step_num,
            label="Validar configuração",
            status=status_1,
            message=msg_1,
            duration_ms=elapsed,
        )
    )

    # ── Step 2: Connect to SMTP server ────────────────────────────────
    step_num += 1
    t0 = time.monotonic()
    server: smtplib.SMTP | smtplib.SMTP_SSL | None = None
    use_implicit_ssl = cfg["port"] == 465

    try:
        if use_implicit_ssl:
            logger.info(
                "SMTP diagnostic: connecting via SMTP_SSL to %s:%s",
                cfg["host"],
                cfg["port"],
            )
            server = smtplib.SMTP_SSL(
                cfg["host"], cfg["port"], timeout=SMTP_SSL_CONNECTION_TIMEOUT_SECONDS
            )
        else:
            logger.info(
                "SMTP diagnostic: connecting via SMTP to %s:%s",
                cfg["host"],
                cfg["port"],
            )
            server = smtplib.SMTP(
                cfg["host"], cfg["port"], timeout=SMTP_CONNECTION_TIMEOUT_SECONDS
            )

        server.ehlo()
        elapsed = int((time.monotonic() - t0) * 1000)
        conn_type = "SSL" if use_implicit_ssl else "SMTP"
        steps.append(
            SmtpDiagnosticStep(
                step=step_num,
                label="Conectar ao servidor",
                status="success",
                message=f"Conectado via {conn_type} a {cfg['host']}:{cfg['port']} ({elapsed}ms)",
                duration_ms=elapsed,
            )
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        friendly = _friendly_smtp_error(exc, cfg)
        steps.append(
            SmtpDiagnosticStep(
                step=step_num,
                label="Conectar ao servidor",
                status="error",
                message=friendly,
                duration_ms=elapsed,
            )
        )
        logger.warning("SMTP diagnostic connection failed: %s", exc)
        return SmtpDiagnosticResponse(
            success=False,
            steps=steps,
            summary=f"Falha na conexão com {cfg['host']}:{cfg['port']}.",
        )

    # ── Step 3: TLS negotiation ───────────────────────────────────────
    step_num += 1
    t0 = time.monotonic()

    if use_implicit_ssl:
        elapsed = int((time.monotonic() - t0) * 1000)
        steps.append(
            SmtpDiagnosticStep(
                step=step_num,
                label="Negociar TLS/SSL",
                status="success",
                message="SSL implícito já ativo (porta 465).",
                duration_ms=elapsed,
            )
        )
    elif cfg["use_tls"]:
        try:
            if server.has_extn("STARTTLS"):
                server.starttls()
                server.ehlo()
                elapsed = int((time.monotonic() - t0) * 1000)
                steps.append(
                    SmtpDiagnosticStep(
                        step=step_num,
                        label="Negociar TLS/SSL",
                        status="success",
                        message=f"STARTTLS negociado com sucesso ({elapsed}ms).",
                        duration_ms=elapsed,
                    )
                )
            else:
                elapsed = int((time.monotonic() - t0) * 1000)
                steps.append(
                    SmtpDiagnosticStep(
                        step=step_num,
                        label="Negociar TLS/SSL",
                        status="warning",
                        message=(
                            "O servidor não anunciou suporte a STARTTLS. "
                            "A conexão prosseguirá sem criptografia. "
                            "Considere usar porta 465 (SSL) se disponível."
                        ),
                        duration_ms=elapsed,
                    )
                )
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            friendly = _friendly_smtp_error(exc, cfg)
            steps.append(
                SmtpDiagnosticStep(
                    step=step_num,
                    label="Negociar TLS/SSL",
                    status="error",
                    message=friendly,
                    duration_ms=elapsed,
                )
            )
            logger.warning("SMTP diagnostic TLS failed: %s", exc)
            try:
                server.quit()
            except Exception:
                pass
            return SmtpDiagnosticResponse(
                success=False,
                steps=steps,
                summary="Falha na negociação TLS/SSL.",
            )
    else:
        elapsed = int((time.monotonic() - t0) * 1000)
        steps.append(
            SmtpDiagnosticStep(
                step=step_num,
                label="Negociar TLS/SSL",
                status="warning",
                message="TLS desabilitado. A conexão não é criptografada.",
                duration_ms=elapsed,
            )
        )

    # ── Step 4: Authenticate ──────────────────────────────────────────
    step_num += 1
    t0 = time.monotonic()

    try:
        _smtp_login_robust(server, cfg["username"], cfg["password"], cfg["host"])
        elapsed = int((time.monotonic() - t0) * 1000)
        masked_user = cfg["username"]
        steps.append(
            SmtpDiagnosticStep(
                step=step_num,
                label="Autenticar",
                status="success",
                message=f"Autenticado como {masked_user} ({elapsed}ms).",
                duration_ms=elapsed,
            )
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        friendly = _friendly_smtp_error(exc, cfg)
        steps.append(
            SmtpDiagnosticStep(
                step=step_num,
                label="Autenticar",
                status="error",
                message=friendly,
                duration_ms=elapsed,
            )
        )
        logger.warning("SMTP diagnostic auth failed: %s", exc)
        try:
            server.quit()
        except Exception:
            pass
        return SmtpDiagnosticResponse(
            success=False,
            steps=steps,
            summary="Falha na autenticação SMTP.",
        )

    # ── Step 5: Send test email ───────────────────────────────────────
    step_num += 1
    t0 = time.monotonic()

    try:
        msg = MIMEMultipart()
        msg["From"] = cfg["from_email"]
        msg["To"] = to_email
        msg["Subject"] = "ClipBuilder - Teste SMTP \u2705"

        html_body = (
            """
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 500px; margin: 40px auto; padding: 0; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 28px 24px; text-align: center;">
                <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 600; letter-spacing: 0.5px;">ClipBuilder</h1>
                <p style="color: #94a3b8; margin: 8px 0 0; font-size: 13px;">Diagnóstico SMTP</p>
            </div>
            <div style="padding: 32px 24px;">
                <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin-bottom: 20px; text-align: center;">
                    <span style="font-size: 32px;">✅</span>
                    <h2 style="color: #15803d; margin: 8px 0 4px; font-size: 18px;">SMTP Funcionando!</h2>
                    <p style="color: #166534; margin: 0; font-size: 14px;">Configuração validada com sucesso.</p>
                </div>
                <p style="color: #374151; font-size: 14px; line-height: 1.6;">
                    Se você está lendo este e-mail, sua configuração SMTP no
                    <strong>ClipBuilder</strong> está correta e o envio de e-mails
                    (recuperação de senha, notificações, etc.) funcionará normalmente.
                </p>
                <table style="width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px;">
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="padding: 8px 0; color: #6b7280; width: 100px;">Servidor</td>
                        <td style="padding: 8px 0; color: #111827; font-family: monospace;">"""
            + f"{cfg['host']}:{cfg['port']}"
            + """</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="padding: 8px 0; color: #6b7280;">Remetente</td>
                        <td style="padding: 8px 0; color: #111827; font-family: monospace;">"""
            + cfg["from_email"]
            + """</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6b7280;">Destino</td>
                        <td style="padding: 8px 0; color: #111827; font-family: monospace;">"""
            + to_email
            + """</td>
                    </tr>
                </table>
            </div>
            <div style="background: #f8fafc; padding: 16px 24px; text-align: center; border-top: 1px solid #e2e8f0;">
                <p style="color: #94a3b8; font-size: 11px; margin: 0;">
                    ClipBuilder &bull; E-mail de teste automático &bull; Diagnóstico SMTP
                </p>
            </div>
        </div>
        """
        )

        msg.attach(MIMEText(html_body, "html"))
        server.send_message(msg)

        elapsed = int((time.monotonic() - t0) * 1000)
        steps.append(
            SmtpDiagnosticStep(
                step=step_num,
                label="Enviar e-mail de teste",
                status="success",
                message=f"E-mail enviado para {to_email} com sucesso ({elapsed}ms).",
                duration_ms=elapsed,
            )
        )
        overall_success = True
        logger.info(
            "SMTP diagnostic: test email sent to %s via %s:%s",
            to_email,
            cfg["host"],
            cfg["port"],
        )

    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        friendly = _friendly_smtp_error(exc, cfg)
        steps.append(
            SmtpDiagnosticStep(
                step=step_num,
                label="Enviar e-mail de teste",
                status="error",
                message=friendly,
                duration_ms=elapsed,
            )
        )
        logger.warning("SMTP diagnostic send failed: %s", exc)
    finally:
        try:
            server.quit()
        except Exception:
            pass

    summary = (
        f"Diagnóstico concluído com sucesso! E-mail de teste enviado para {to_email}."
        if overall_success
        else "Diagnóstico falhou. Verifique os erros acima e corrija a configuração."
    )

    return SmtpDiagnosticResponse(
        success=overall_success,
        steps=steps,
        summary=summary,
    )


# ── Legacy test-email (kept for backward compat) ─────────────────────


@router.post("/test-email")
def test_email(_admin: RequireAdmin):
    """Send a quick test email using env-configured SMTP. Prefer /smtp-diagnostic."""
    from app.services.email_service import EmailService

    svc = EmailService()
    if not svc.smtp_user or not svc.smtp_pass:
        raise HTTPException(
            status_code=400,
            detail="SMTP não configurado. Defina SMTP_USER e SMTP_PASS no .env",
        )
    try:
        svc.send_email(
            svc.smtp_from,
            "ClipBuilder - Teste SMTP ✅",
            """
            <div style="font-family: sans-serif; max-width: 500px; margin: 40px auto; padding: 32px; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <h2 style="color: #22c55e;">✅ SMTP configurado com sucesso!</h2>
                <p>Se você está lendo este email, a configuração SMTP do ClipBuilder está funcionando corretamente.</p>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 16px 0;">
                <p style="color: #71717a; font-size: 12px;">ClipBuilder &bull; Email de teste automático</p>
            </div>
            """,
        )
        return {"ok": True, "message": "Email de teste enviado com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao enviar email: {str(e)}") from e
