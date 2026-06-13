"""Alembic environment — async, driven off the observability engine/settings.

The DB URL comes from WB_TRACE_DB_URL (the same async SQLAlchemy URL the app
uses), so `alembic upgrade head` migrates whatever the trace store points at —
sqlite locally, Postgres in the stack.
"""

import asyncio

from alembic import context

import workbench_observability.models  # noqa: F401 — registers Trace on Base.metadata
from workbench_observability.db import Base, get_engine

target_metadata = Base.metadata


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    engine = get_engine()
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async_migrations())
