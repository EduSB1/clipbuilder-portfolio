"""SQLAlchemy database engine, session factory, and declarative Base."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def _with_explicit_driver(url: str) -> str:
    """Força o driver psycopg2 na URL de conexão.

    A partir do SQLAlchemy 2.1 o esquema genérico ``postgresql://`` passou a
    resolver para o dialeto ``psycopg`` (psycopg 3), que não faz parte das
    dependências do projeto — a aplicação subiria e morreria com
    ``ModuleNotFoundError: No module named 'psycopg'``.

    Como a URL é montada pelo docker-compose e por ambientes externos, não dá
    para confiar que ela venha qualificada; normalizamos aqui.  Migrar para
    psycopg 3 é possível no futuro: basta trocar o driver nesta função e a
    dependência em requirements.txt.
    """
    prefix = "postgresql://"
    if url.startswith(prefix):
        return "postgresql+psycopg2://" + url[len(prefix) :]
    return url


engine = create_engine(
    _with_explicit_driver(settings.database_url),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all models."""

    pass


def get_db():
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
