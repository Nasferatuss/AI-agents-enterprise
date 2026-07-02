"""Async run model: submit → 202 + run_id, background execution, poll, idempotency.

The agent itself is stubbed (this exercises the run lifecycle/persistence, not the
LLM loop), against a fresh in-memory durable store.
"""

import asyncio

import pytest
from workbench_app_autonomous import api
from workbench_app_autonomous.agent import AutonomousResult

from workbench_observability import init_db, reset_engine


@pytest.fixture
async def run_store(monkeypatch):
    monkeypatch.setenv("WB_TRACE_DB_URL", "sqlite+aiosqlite:///:memory:")
    reset_engine()
    await init_db()
    yield
    reset_engine()


def _fake_result(goal: str) -> AutonomousResult:
    return AutonomousResult(
        goal=goal,
        iterations=[],
        memory=["did the thing"],
        final_answer="done",
        completed=True,
        cost_usd=0.01,
    )


async def _drain(run_id: str, *, tries: int = 50) -> api.RunView:
    """Yield control so the background task runs, then poll to a terminal status."""
    terminal = {"completed", "max_steps_reached", "failed"}
    for _ in range(tries):
        await asyncio.sleep(0)
        view = await api.get_run_status(run_id)
        if view.status in terminal:
            return view
    return await api.get_run_status(run_id)


async def test_submit_returns_202_and_completes_in_background(run_store, monkeypatch):
    calls = {"n": 0}

    async def fake_run(router, goal):
        calls["n"] += 1
        return _fake_result(goal)

    monkeypatch.setattr(api, "run_autonomous", fake_run)

    handle = await api.submit(api.RunRequest(goal="summarize Q3"))
    assert handle.status == "pending"
    assert handle.run_id

    view = await _drain(handle.run_id)
    assert view.status == "completed"
    assert view.goal == "summarize Q3"
    assert view.result is not None and view.result.final_answer == "done"
    assert calls["n"] == 1


async def test_unknown_run_404(run_store):
    with pytest.raises(Exception):  # noqa: B017 — HTTPException(404) surfaces here
        await api.get_run_status("does-not-exist")


async def test_idempotent_submit_dedupes(run_store, monkeypatch):
    calls = {"n": 0}

    async def fake_run(router, goal):
        calls["n"] += 1
        return _fake_result(goal)

    monkeypatch.setattr(api, "run_autonomous", fake_run)

    h1 = await api.submit(api.RunRequest(goal="x"), idempotency_key="k1")
    await _drain(h1.run_id)
    h2 = await api.submit(api.RunRequest(goal="x"), idempotency_key="k1")
    assert h2.run_id == h1.run_id  # same run, not a second launch
    assert calls["n"] == 1

    h3 = await api.submit(api.RunRequest(goal="x"), idempotency_key="k2")
    await _drain(h3.run_id)
    assert h3.run_id != h1.run_id
    assert calls["n"] == 2


async def test_execute_run_skips_already_terminal(run_store, monkeypatch):
    from workbench_observability import upsert_run

    calls = {"n": 0}

    async def fake_run(router, goal):
        calls["n"] += 1
        return _fake_result(goal)

    monkeypatch.setattr(api, "run_autonomous", fake_run)
    # A run re-delivered by reclaim/reconcile that already finished must NOT be redone:
    # the atomic claim rejects a terminal row (at-least-once delivery + idempotent claim).
    await upsert_run(run_id="done", kind="autonomous", status="completed", payload={"goal": "x"})
    await api._execute_run("done", "x")
    assert calls["n"] == 0


async def test_failed_run_records_error(run_store, monkeypatch):
    async def boom(router, goal):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(api, "run_autonomous", boom)

    handle = await api.submit(api.RunRequest(goal="x"))
    view = await _drain(handle.run_id)
    assert view.status == "failed"
    assert "provider exploded" in (view.error or "")
