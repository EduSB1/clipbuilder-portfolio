"""Configuração compartilhada dos testes.

As variáveis de ambiente precisam existir ANTES de qualquer import de `app.*`,
porque `app.core.config` instancia as settings no momento da importação.
"""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-production")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://clipbuilder:test@localhost:5432/clipbuilder_test"
)
os.environ.setdefault("CLIPBUILDER_DATA_DIR", "/tmp/clipbuilder-test-data")
os.environ.setdefault("CLIPBUILDER_LOG_DIR", "/tmp/clipbuilder-test-logs")
