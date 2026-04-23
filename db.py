"""Database engine + session helpers.

Uses SQLAlchemy 2.x. Default ``DATABASE_URL`` points at a SQLite file in
``/tmp`` so the service can run on Cloud Run without an attached database;
set a managed database URL (e.g. Cloud SQL) in production.

All writes use the ORM with bound parameters — no string-concatenated SQL.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _build_engine() -> Engine:
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def init_engine() -> Engine:
    """Build the engine (idempotent) and ensure tables exist.

    ``Base.metadata.create_all`` is safe to run on every boot — it only
    issues DDL for tables that are missing, and it is never destructive.
    """

    global _engine, _SessionLocal

    if _engine is None:
        _engine = _build_engine()
        Base.metadata.create_all(bind=_engine)
        _SessionLocal = sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a database session with commit/rollback + close semantics."""

    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None  # for type checkers
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
