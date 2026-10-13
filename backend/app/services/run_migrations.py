"""Run migrations for admin expansion. Add new columns to existing tables if missing.

Also handles table creation for the credit system (credit_accounts, credit_transactions).
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.database import engine

logger = logging.getLogger("clipbuilder")

MIGRATIONS = [
    (
        "users",
        "primary_group_id",
        "ALTER TABLE users ADD COLUMN primary_group_id INTEGER REFERENCES user_groups(id) ON DELETE SET NULL",
    ),
    (
        "api_usage_logs",
        "group_id",
        "ALTER TABLE api_usage_logs ADD COLUMN group_id INTEGER REFERENCES user_groups(id) ON DELETE SET NULL",
    ),
    (
        "api_usage_logs",
        "video_duration_seconds",
        "ALTER TABLE api_usage_logs ADD COLUMN video_duration_seconds INTEGER",
    ),
    (
        "api_usage_logs",
        "cost_usd",
        "ALTER TABLE api_usage_logs ADD COLUMN cost_usd DECIMAL(10,4)",
    ),
    # User management: soft delete support
    (
        "users",
        "deleted_at",
        "ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL",
    ),
    # Clerk integration
    (
        "users",
        "clerk_id",
        "ALTER TABLE users ADD COLUMN clerk_id VARCHAR(255) UNIQUE",
    ),
    # Temporary credential flag
    (
        "users",
        "must_change_password",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE NOT NULL",
    ),
    # Plan field for subscription tiers
    (
        "users",
        "plan",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan VARCHAR(20) DEFAULT 'free' NOT NULL",
    ),
    # Template permissions
    (
        "user_permissions",
        "allowed_templates",
        "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS allowed_templates TEXT DEFAULT NULL",
    ),
    # AI permissions
    (
        "user_permissions",
        "can_use_gemini",
        "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS can_use_gemini BOOLEAN DEFAULT TRUE NOT NULL",
    ),
    (
        "user_permissions",
        "can_use_whisper",
        "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS can_use_whisper BOOLEAN DEFAULT TRUE NOT NULL",
    ),
    (
        "user_permissions",
        "max_video_size_gb",
        "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS max_video_size_gb FLOAT DEFAULT 6.0 NOT NULL",
    ),
    # Export permissions
    (
        "user_permissions",
        "can_export_html",
        "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS can_export_html BOOLEAN DEFAULT FALSE NOT NULL",
    ),
    (
        "user_permissions",
        "can_export_docx",
        "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS can_export_docx BOOLEAN DEFAULT TRUE NOT NULL",
    ),
    (
        "user_permissions",
        "can_export_md",
        "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS can_export_md BOOLEAN DEFAULT FALSE NOT NULL",
    ),
    (
        "user_permissions",
        "can_export_pdf",
        "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS can_export_pdf BOOLEAN DEFAULT FALSE NOT NULL",
    ),
]

# SQL statements to create credit system tables (idempotent — uses IF NOT EXISTS)
CREDIT_TABLE_MIGRATIONS = [
    # credit_accounts table
    """
    CREATE TABLE IF NOT EXISTS credit_accounts (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        credits_balance INTEGER NOT NULL DEFAULT 0,
        total_credits_purchased INTEGER NOT NULL DEFAULT 0,
        total_credits_used INTEGER NOT NULL DEFAULT 0,
        stripe_customer_id VARCHAR(255),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )
    """,
    # Index on user_id for credit_accounts
    """
    CREATE INDEX IF NOT EXISTS ix_credit_accounts_user_id ON credit_accounts(user_id)
    """,
    # Index on stripe_customer_id for credit_accounts
    """
    CREATE INDEX IF NOT EXISTS ix_credit_accounts_stripe_customer_id ON credit_accounts(stripe_customer_id)
    """,
    # credit_transactions table
    """
    CREATE TABLE IF NOT EXISTS credit_transactions (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(36) NOT NULL REFERENCES users(id),
        amount INTEGER NOT NULL,
        type VARCHAR(30) NOT NULL,
        description VARCHAR(255),
        stripe_payment_intent_id VARCHAR(255),
        endpoint VARCHAR(100),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )
    """,
    # Index on user_id for credit_transactions
    """
    CREATE INDEX IF NOT EXISTS ix_credit_transactions_user_id ON credit_transactions(user_id)
    """,
]

# SQL to ensure every existing user gets a credit_accounts row with balance=0
SEED_CREDIT_ACCOUNTS_SQL = """
    INSERT INTO credit_accounts (id, user_id, credits_balance, total_credits_purchased, total_credits_used, created_at, updated_at)
    SELECT
        gen_random_uuid()::varchar(36),
        u.id,
        0,
        0,
        0,
        NOW(),
        NOW()
    FROM users u
    LEFT JOIN credit_accounts ca ON ca.user_id = u.id
    WHERE ca.id IS NULL
"""


def _column_exists(conn, table: str, column: str) -> bool:
    r = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :t AND column_name = :c
    """),
        {"t": table, "c": column},
    )
    return r.scalar() is not None


def _table_exists(conn, table: str) -> bool:
    r = conn.execute(
        text("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = :t
    """),
        {"t": table},
    )
    return r.scalar() is not None


def run_migrations() -> None:
    """Execute migration SQL."""
    with engine.connect() as conn:
        # ── Column-level migrations ──────────────────────────────────────
        for table, column, sql in MIGRATIONS:
            try:
                if _column_exists(conn, table, column):
                    logger.debug("Column %s.%s already exists, skipping", table, column)
                    continue
                conn.execute(text(sql))
                conn.commit()
                logger.info("Migration applied: %s.%s", table, column)
            except Exception as exc:
                msg = str(exc).lower()
                if "already exists" in msg or "duplicate" in msg:
                    logger.debug("Column already exists: %s", exc)
                else:
                    logger.warning("Migration failed for %s.%s: %s", table, column, exc)

        # ── Credit system table migrations ───────────────────────────────
        for i, ddl in enumerate(CREDIT_TABLE_MIGRATIONS):
            try:
                conn.execute(text(ddl))
                conn.commit()
                logger.debug("Credit migration %d applied", i)
            except Exception as exc:
                msg = str(exc).lower()
                if "already exists" in msg or "duplicate" in msg:
                    logger.debug("Credit migration %d already applied: %s", i, exc)
                else:
                    logger.warning("Credit migration %d failed: %s", i, exc)

        # ── Seed credit accounts for existing users ──────────────────────
        if _table_exists(conn, "credit_accounts"):
            try:
                result = conn.execute(text(SEED_CREDIT_ACCOUNTS_SQL))
                conn.commit()
                rows = result.rowcount if result.rowcount else 0
                if rows > 0:
                    logger.info("Seeded %d credit account(s) for existing users", rows)
            except Exception as exc:
                logger.warning("Failed to seed credit accounts: %s", exc)

        # ── Template logo migration ──────────────────────────────────────
        if _table_exists(conn, "document_templates"):
            try:
                # Upgrading logo_path from VARCHAR(500) to TEXT
                conn.execute(text("ALTER TABLE document_templates ALTER COLUMN logo_path TYPE TEXT"))
                conn.commit()
                logger.info("Upgraded document_templates.logo_path to TEXT")
            except Exception as exc:
                logger.warning("Failed to upgrade logo_path to TEXT: %s", exc)

        # ── Seed system settings ──────────────────────────────────────
        try:
            from sqlalchemy.orm import Session

            from app.admin.settings.service import seed_settings
            with Session(engine) as db:
                seed_settings(db)
            logger.info("System settings seeded/checked")
        except Exception as exc:
            logger.warning("Failed to seed system settings: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
