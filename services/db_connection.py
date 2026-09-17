from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import Settings
from models.base import Base


_engine = None
_SessionLocal = None


def _resolve_database_url() -> str:
    settings = Settings(_env_file=".env")
    database_url = str(settings.DATABASE_URL or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return database_url


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            _resolve_database_url(),
            pool_size=20,
            max_overflow=40,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


@contextmanager
def get_db_session():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create all tables (development only, use Alembic for production)."""
    Base.metadata.create_all(bind=get_engine())
