from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _engine_kwargs(database_url: str) -> dict[str, object]:
    return {"future": True}


def _normalize_database_url(url: str) -> str:
    # Managed-Postgres providers hand out postgres:// or postgresql:// URLs;
    # only psycopg 3 is installed, so pin the driver instead of crashing on psycopg2.
    for bare_scheme in ("postgresql://", "postgres://"):
        if url.startswith(bare_scheme):
            return "postgresql+psycopg://" + url[len(bare_scheme) :]
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("SignalDeck requires PostgreSQL with the psycopg driver")
    return url


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    resolved_url = _normalize_database_url(database_url or get_settings().database_url)
    return create_engine(resolved_url, **_engine_kwargs(resolved_url))


@lru_cache
def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(database_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_db_session() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_db_caches() -> None:
    get_session_factory.cache_clear()
    get_engine.cache_clear()
