"""Startup reconciler re-enqueues non-terminal runs (crash recovery)."""

import asyncio

import pytest
from workbench_jobs import InProcessQueue, register_handler

from workbench_gateway.reconcile import reconcile_runs
from workbench_observability import create_run, init_db, reset_engine, upsert_run


@pytest.fixture
async def db(monkeypatch):
    monkeypatch.setenv("WB_TRACE_DB_URL", "sqlite+aiosqlite:///:memory:")
    from workbench_shared.config import get_settings

    get_settings.cache_clear()
    reset_engine()
    await init_db()
    yield
    reset_engine()
    get_settings.cache_clear()


async def test_reconcile_reenqueues_only_nonterminal(db):
    seen: list[tuple[str, str]] = []

    async def handler(run_id, payload):
        seen.append((run_id, payload.get("goal", "")))

    register_handler("recontest", handler)

    # An orphaned, still-running run — must be picked up.
    await create_run(run_id="x", kind="recontest", status="running", payload={"goal": "resume me"})
    # A finished run — must NOT be re-enqueued.
    await create_run(run_id="done", kind="recontest", status="pending", payload={})
    await upsert_run(run_id="done", kind="recontest", status="completed", payload={})

    n = await reconcile_runs(InProcessQueue())
    for _ in range(50):
        await asyncio.sleep(0)
        if seen:
            break

    assert n == 1
    assert seen == [("x", "resume me")]
