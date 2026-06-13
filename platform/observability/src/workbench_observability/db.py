"""Async SQLAlchemy engine for the trace store.

DB-agnostic by design (ADR-006/ADR-009): the same models run on Postgres in the
Docker stack (`postgresql+asyncpg://…`) and on a local sqlite file for Docker-less
dev (the default). `make up` overrides WB_TRACE_DB_URL to point at Postgres.

v0 creates tables via `metadata.create_all` (init_db); Alembic migrations are the
hardening step once the schema stabilizes.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from workbench_shared.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None


def _build_engine(url: str) -> AsyncEngine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            # share one in-process connection so every session sees the same DB (tests)
            kwargs["poolclass"] = StaticPool
    return create_async_engine(url, **kwargs)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings().trace_db_url)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (tests switching DB URLs)."""
    global _engine
    _engine = None


def get_sessionmaker() -> async_sessionmaker:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def init_db() -> None:
    """Bootstrap the schema for sqlite (local dev / tests). For Postgres the
    schema is owned by Alembic — run `make migrate` — so this is a no-op there to
    avoid racing create_all against the migration history."""
    engine = get_engine()
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
