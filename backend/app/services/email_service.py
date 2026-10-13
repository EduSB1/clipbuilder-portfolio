import base64
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger("clipbuilder")


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
    server: smtplib.SMTP | smtplib.SMTP_SSL,
    username: str,
    password: str,
    host: str,
) -> None:
    """Login with explicit AUTH method selection.

    Office 365 (and some other providers) advertise CRAM-MD5 but reject it,
    causing Python's default ``server.login()`` to fail with 535.  This helper
    tries AUTH methods in an order that works for O365:
        1. AUTH LOGIN
        2. AUTH PLAIN
        3. Default (fallback to ``server.login()``)
    """
    if _is_office365(host):
        logger.info("SMTP auth: Office 365 detected — forcing AUTH LOGIN (skip CRAM-MD5)")

        # Try AUTH LOGIN first (most reliable for O365)
        try:
            code, resp = server.docmd("AUTH", "LOGIN")
            if code == 334:
                code, resp = server.docmd(base64.b64encode(username.encode()).decode())
            if code == 334:
                code, resp = server.docmd(base64.b64encode(password.encode()).decode())
            if code == 235:
                logger.info("SMTP auth: AUTH LOGIN succeeded for %s", username)
                return
            raise smtplib.SMTPAuthenticationError(code, resp)
        except smtplib.SMTPAuthenticationError:
            raise
        except Exception as exc_login:
            logger.warning("SMTP auth: AUTH LOGIN failed (%s), trying AUTH PLAIN...", exc_login)

        # Try AUTH PLAIN as fallback
        try:
            credentials = base64.b64encode(f"\x00{username}\x00{password}".encode()).decode()
            code, resp = server.docmd("AUTH", f"PLAIN {credentials}")
            if code == 235:
                logger.info("SMTP auth: AUTH PLAIN succeeded for %s", username)
                return
            raise smtplib.SMTPAuthenticationError(code, resp)
        except smtplib.SMTPAuthenticationError:
            raise
        except Exception as exc_plain:
            logger.warning("SMTP auth: AUTH PLAIN also failed (%s), falling back to default login", exc_plain)

    # Default: let smtplib pick the best method (works for Gmail and most others)
    server.login(username, password)
    logger.info("SMTP auth: default login() succeeded for %s", username)


def _db_smtp(key: str) -> str:
    """Read a single SMTP setting from the database. Returns '' on any error."""
    try:
        from app.admin.settings.service import get_setting_value
        return get_setting_value("smtp", key) or ""
    except Exception:
        return ""


class EmailService:
    def __init__(self):
        # Priority: Database (admin panel) → .env / environment variables
        # The SMTP Diagnostic modal uses the DB; the email service must do the same.
        db_host = _db_smtp("host")
        db_port = _db_smtp("port")
        db_user = _db_smtp("username")
        db_pass = _db_smtp("password")
        db_from = _db_smtp("from_email")
        db_frontend_url = _db_smtp("frontend_url")

        self.smtp_host = db_host or settings.smtp_host
        self.smtp_port = int(db_port) if db_port else settings.smtp_port
        self.smtp_user = db_user or settings.smtp_user
        self.smtp_pass = db_pass or settings.smtp_pass
        # from_email must match the authenticated account (Gmail Sender policy)
        self.smtp_from = db_from or settings.smtp_from_email or self.smtp_user
        # frontend_url: DB setting → env var → default (used in reset password link)
        self.frontend_url = db_frontend_url or settings.frontend_url

        logger.debug(
            "EmailService initialised: host=%s port=%s user=%s from=%s (db_host=%r db_user=%r db_from=%r)",
            self.smtp_host, self.smtp_port, self.smtp_user, self.smtp_from,
            db_host, db_user, db_from,
        )

    def send_email(self, to_email: str, subject: str, html_content: str):
        if not self.smtp_user or not self.smtp_pass:
            logger.warning("SMTP not configured (SMTP_USER/SMTP_PASS missing). Email to %s NOT sent.", to_email)
            return

        logger.info(
            "Preparing to send email to=%s subject='%s' host=%s:%s user=%s from=%s",
            to_email, subject, self.smtp_host, self.smtp_port, self.smtp_user, self.smtp_from
        )

        msg = MIMEMultipart()
        msg["From"] = self.smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(html_content, "html"))

        try:
            if self.smtp_port == 465:
                logger.debug("Connecting via SMTP_SSL to %s:%s", self.smtp_host, self.smtp_port)
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    logger.debug("Logging in as %s...", self.smtp_user)
                    _smtp_login_robust(server, self.smtp_user, self.smtp_pass, self.smtp_host)

                    logger.debug("Sending message...")
                    server.send_message(msg)
            else:
                logger.debug("Connecting via SMTP (STARTTLS) to %s:%s", self.smtp_host, self.smtp_port)
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.ehlo()

                    if server.has_extn("STARTTLS"):
                        logger.debug("Starting TLS...")
                        server.starttls()
                        server.ehlo()

                    logger.debug("Logging in as %s...", self.smtp_user)
                    _smtp_login_robust(server, self.smtp_user, self.smtp_pass, self.smtp_host)

                    logger.debug("Sending message...")
                    server.send_message(msg)

            logger.info("SUCCESS: Email '%s' sent to %s", subject, to_email)

        except smtplib.SMTPAuthenticationError as e:
            logger.error("SMTP Auth Error: Failed to login. Check SMTP_USER/SMTP_PASS. Details: %s", e)
            raise
        except smtplib.SMTPConnectError as e:
            logger.error("SMTP Connect Error: Failed to connect to %s:%s. Details: %s", self.smtp_host, self.smtp_port, e)
            raise
        except smtplib.SMTPException as e:
            logger.error("SMTP Generic Error: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected Error sending email to %s: %s", to_email, str(e), exc_info=True)
            raise

    def send_password_reset_email(self, user_email: str, token: str):
        reset_link = f"{self.frontend_url}/reset-password?token={token}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f5; color: #1f2937; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 40px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
                .header {{ background-color: #1a1a1a; padding: 24px; text-align: center; }}
                .header h1 {{ color: #ffffff; margin: 0; font-size: 24px; font-weight: 600; }}
                .content {{ padding: 32px; }}
                .button {{ display: inline-block; background-color: #3b82f6; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 500; margin-top: 24px; }}
                .footer {{ background-color: #f4f4f5; padding: 16px; text-align: center; font-size: 12px; color: #71717a; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>ClipBuilder</h1>
                </div>
                <div class="content">
                    <h2>Recuperação de Senha</h2>
                    <p>Olá,</p>
                    <p>Recebemos uma solicitação para redefinir a senha da sua conta no ClipBuilder.</p>
                    <p>Para criar uma nova senha, clique no botão abaixo:</p>
                    <p style="text-align: center;">
                        <a href="{reset_link}" class="button">Redefinir Senha</a>
                    </p>
                    <p>Se você não solicitou esta alteração, pode ignorar este e-mail com segurança.</p>
                    <p>O link expirará em breve.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2024 ClipBuilder. Todos os direitos reservados.</p>
                </div>
            </div>
        </body>
        </html>
        """
        self.send_email(user_email, "Recuperação de Senha - ClipBuilder", html_content)
