"""Settings service - load, save, seed defaults."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.admin.models import SystemSetting

logger = logging.getLogger("clipbuilder")

DEFAULT_SEED = [
    ("smtp", "host", "", "string", "Servidor SMTP"),
    ("smtp", "port", "587", "number", "Porta SMTP"),
    ("smtp", "username", "", "string", "E-mail de Autenticação"),
    ("smtp", "password", "", "string", "Senha SMTP"),
    ("smtp", "use_tls", "true", "boolean", "Usar TLS"),
    ("smtp", "from_email", "", "string", "Email remetente (deve ser igual ao e-mail de autenticação)"),
    ("smtp", "frontend_url", "", "string", "URL pública do frontend (ex: http://192.168.18.200:8081)"),
    ("storage", "max_video_size_gb", "6", "number", "Tamanho máximo de vídeo (GB)"),
    ("storage", "cleanup_days", "30", "number", "Dias para limpar vídeos antigos"),
    ("storage", "total_quota_gb", "1000", "number", "Quota total de storage (GB)"),
    ("security", "jwt_expiration_hours", "24", "number", "Expiração do JWT (horas)"),
    ("security", "password_min_length", "8", "number", "Tamanho mínimo de senha"),
    (
        "security",
        "require_email_verification",
        "true",
        "boolean",
        "Exigir verificação de email",
    ),
    ("security", "max_login_attempts", "5", "number", "Tentativas máximas de login"),
    (
        "features",
        "allow_youtube_import",
        "true",
        "boolean",
        "Permitir importação do YouTube",
    ),
    (
        "features",
        "enable_gif_generation",
        "true",
        "boolean",
        "Habilitar geração de GIFs",
    ),
    (
        "features",
        "max_steps_per_document",
        "100",
        "number",
        "Máximo de passos por documento",
    ),
    (
        "features",
        "template_permissions_enabled",
        "false",
        "boolean",
        "Habilitar restrição de templates por usuário",
    ),
]


def seed_settings(db: Session) -> None:
    """Insert default settings if missing."""
    from sqlalchemy import select

    for cat, key, val, vtype, desc in DEFAULT_SEED:
        exists = db.scalar(
            select(SystemSetting).where(
                SystemSetting.category == cat, SystemSetting.key == key
            )
        )
        if not exists:
            s = SystemSetting(
                category=cat, key=key, value=val, value_type=vtype, description=desc
            )
            db.add(s)
            logger.info("Seeded missing setting: %s/%s", cat, key)
    db.commit()


def get_settings_by_category(db: Session, category: str | None = None) -> list[dict]:
    """Return settings as list of dicts, optionally filtered by category."""
    from sqlalchemy import select

    q = select(SystemSetting)
    if category:
        q = q.where(SystemSetting.category == category)
    q = q.order_by(SystemSetting.category, SystemSetting.key)
    rows = db.scalars(q).all()
    return [
        {
            "key": r.key,
            "value": r.value,
            "value_type": r.value_type,
            "description": r.description,
            "is_encrypted": r.is_encrypted,
        }
        for r in rows
    ]


def get_setting_value(category: str, key: str) -> str | None:
    """Return a single setting value by category+key, or None if not found/empty.

    Opens its own DB session so it can be called from anywhere (e.g. main.py
    helpers that resolve API keys).
    """
    from sqlalchemy import select

    from app.database import SessionLocal

    try:
        with SessionLocal() as db:
            from app.admin.models import SystemSetting as SS

            row = db.scalar(select(SS).where(SS.category == category, SS.key == key))
            if row and row.value and str(row.value).strip():
                return str(row.value).strip()
    except Exception:
        pass
    return None


def update_settings(
    db: Session, updates: list[dict], user_id: str | None = None
) -> None:
    """Update multiple settings."""
    from sqlalchemy import select

    for item in updates:
        cat = item.get("category")
        key = item.get("key")
        value = item.get("value")
        if not cat or not key:
            continue
        s = db.scalar(
            select(SystemSetting).where(
                SystemSetting.category == cat,
                SystemSetting.key == key,
            )
        )
        if s:
            s.value = str(value) if value is not None else ""
            s.last_modified_by = user_id
    db.commit()
