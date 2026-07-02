"""Async SQLAlchemy engine for the trace store.

DB-agnostic by design (ADR-006/ADR-009): the same models run on Postgres in the
Docker stack (`postgresql+asyncpg://…`) and on a local sqlite file for Docker-less
dev (the default). `make up` overrides WB_TRACE_DB_URL to point at Postgres.

v0 creates tables via `metadata.create_all` (init_db); Alembic migrations are the
hardening step once the schema stabilizes.
"""

import tempfile
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from workbench_shared.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
# Temp files backing ":memory:" test engines (see _build_engine); removed on reset.
_tmp_db_paths: list[Path] = []


def _build_engine(url: str) -> AsyncEngine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            # A single shared in-memory connection (StaticPool) is unsafe here: the
            # run store is exercised by CONCURRENT async sessions (a background run
            # writing terminal state while a client polls). Interleaving their awaits
            # on one connection lets a reader's rollback-on-close clobber the writer's
            # in-flight transaction — a lost update. Production never hits this (each
            # session gets its own pooled connection). Back ":memory:" with a private
            # temp FILE so every session connects independently, matching production
            # connection-per-session semantics while staying disk-cheap and isolated.
            tmp = Path(tempfile.gettempdir()) / f"wb-testdb-{uuid.uuid4().hex}.sqlite"
            _tmp_db_paths.append(tmp)
            url = f"sqlite+aiosqlite:///{tmp}"
    return create_async_engine(url, **kwargs)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings().trace_db_url)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (tests switching DB URLs), removing any temp DB files
    created to back a ":memory:" URL."""
    global _engine
    _engine = None
    while _tmp_db_paths:
        path = _tmp_db_paths.pop()
        path.unlink(missing_ok=True)


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
