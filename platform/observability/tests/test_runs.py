"""Durable run store: race-safe idempotency + non-terminal listing for reconcile."""

import datetime

from workbench_observability import (
    create_run,
    get_run,
    get_run_by_idempotency_key,
    list_nonterminal_runs,
    list_runs,
    sweep_stuck_runs,
    touch_run,
    upsert_run,
)
from workbench_observability.runs import _fmt


async def test_create_run_dedupes_on_idempotency_key(trace_db):
    r1 = await create_run(
        run_id="a",
        kind="autonomous",
        status="pending",
        payload={"goal": "x"},
        idempotency_key="k1",
    )
    assert r1.run_id == "a"
    # Second create with the SAME key (different run_id) must hit the UNIQUE and
    # return the original run, not create a duplicate.
    r2 = await create_run(
        run_id="b",
        kind="autonomous",
        status="pending",
        payload={"goal": "x"},
        idempotency_key="k1",
    )
    assert r2.run_id == "a"
    assert len(await list_runs("autonomous")) == 1
    assert (await get_run_by_idempotency_key("autonomous", "k1")).run_id == "a"


async def test_create_run_without_key_allows_many(trace_db):
    a = await create_run(run_id="a", kind="autonomous", status="pending", payload={})
    b = await create_run(run_id="b", kind="autonomous", status="pending", payload={})
    assert {a.run_id, b.run_id} == {"a", "b"}  # NULL keys are distinct


async def test_list_nonterminal_runs(trace_db):
    await create_run(run_id="p", kind="autonomous", status="pending", payload={})
    await create_run(run_id="r", kind="autonomous", status="pending", payload={})
    await upsert_run(run_id="r", kind="autonomous", status="running", payload={})
    await create_run(run_id="done", kind="autonomous", status="pending", payload={})
    await upsert_run(run_id="done", kind="autonomous", status="completed", payload={})

    ids = {r.run_id for r in await list_nonterminal_runs()}
    assert ids == {"p", "r"}  # pending + running, not completed


async def test_sweep_marks_stale_running_failed(trace_db):
    await upsert_run(run_id="hung", kind="autonomous", status="running", payload={})
    # Negative TTL puts the cutoff in the future, so a just-created run counts as stale.
    n = await sweep_stuck_runs(ttl_seconds=-10)
    assert n == 1
    swept = await get_run("hung")
    assert swept.status == "failed"
    assert "heartbeat" in swept.error


async def test_sweep_ignores_fresh_running(trace_db):
    await upsert_run(run_id="busy", kind="autonomous", status="running", payload={})
    assert await sweep_stuck_runs(ttl_seconds=3600) == 0
    assert (await get_run("busy")).status == "running"


async def test_sweep_does_not_clobber_completed_run(trace_db):
    # The atomic UPDATE ... WHERE status='running' must never touch a terminal run,
    # even with a cutoff in the future — a run that completed is not "stuck".
    await create_run(run_id="done", kind="autonomous", status="pending", payload={})
    await upsert_run(run_id="done", kind="autonomous", status="completed", payload={"r": 1})
    assert await sweep_stuck_runs(ttl_seconds=-10) == 0
    row = await get_run("done")
    assert row.status == "completed"  # not flipped to failed
    assert row.error is None and row.payload == {"r": 1}


def test_timestamp_format_is_fixed_width_and_chronological():
    # The whole-second case is where datetime.isoformat() drops the fractional part
    # and breaks string ordering; _fmt must keep a fixed width so "<" == chronological.
    whole_second = datetime.datetime(2026, 6, 21, 12, 0, 55, 0, tzinfo=datetime.UTC)
    just_after = whole_second + datetime.timedelta(microseconds=1)
    a, b = _fmt(whole_second), _fmt(just_after)
    assert len(a) == len(b)  # fixed width regardless of microseconds
    assert a.endswith("Z") and ".000000Z" in a  # zero micros NOT truncated
    assert a < b  # lexical order matches chronological order


async def test_touch_run_bumps_updated_at(trace_db):
    await upsert_run(run_id="r", kind="autonomous", status="running", payload={})
    before = (await get_run("r")).updated_at
    await touch_run("r")
    after = (await get_run("r")).updated_at
    assert after >= before  # heartbeat advanced (ISO sorts chronologically)
