"""Diagnostic Service — Database session factory"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.core.db_timezone import utc_connect_args


# The pool of one worker.  ``sync_work_slots`` (config) is kept below their sum - see src/core/sync_slots.py.
POOL_SIZE = 5
MAX_OVERFLOW = 10


def _make_engine():
    s = get_settings()
    return create_engine(
        s.database_url,
        echo=s.debug,
        pool_pre_ping=True,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        connect_args=utc_connect_args(s.database_url),  # session TimeZone=UTC on every connection (ROADMAP #49)
    )


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a scoped SQLAlchemy Session."""
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager for scripts and background tasks."""
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
