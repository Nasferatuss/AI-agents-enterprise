"""Autonomous Agent endpoints (mounted by the gateway).

Exposes the plan→act→reflect→repeat engine (agent.py) over HTTP, two ways:

* ``POST /run`` — synchronous: runs to completion in the request (simple, used by
  the demo console; fine for short goals, but a long run can outlast an LB/ingress
  timeout).
* ``POST /runs`` → ``202 {run_id}`` — asynchronous: the run executes in the
  background and is persisted to the durable run store; the client polls
  ``GET /runs/{run_id}``. This is the production-shaped path — it survives long
  horizons, is idempotent (``Idempotency-Key``), and the run state is queryable
  from any replica, not just the one that accepted the request.
"""

import asyncio
import contextlib
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from workbench_jobs import Job, get_queue, register_handler

from workbench_app_autonomous.agent import AutonomousResult, run_autonomous
from workbench_observability import (
    create_run,
    get_run,
    get_run_by_idempotency_key,
    safe_record,
    touch_run,
    upsert_run,
)
from workbench_runtime import get_router
from workbench_runtime.router import NoProviderAvailableError
from workbench_shared.config import get_settings

router = APIRouter(prefix="/v1/apps/autonomous", tags=["autonomous-agent"])

_KIND = "autonomous"
_TERMINAL_STATUSES = {"completed", "max_steps_reached", "failed"}


class RunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


class RunHandle(BaseModel):
    run_id: str
    status: str  # pending on submit


class RunView(BaseModel):
    run_id: str
    status: str  # pending | running | completed | max_steps_reached | failed
    goal: str | None = None
    result: AutonomousResult | None = None
    error: str | None = None


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/run", response_model=AutonomousResult)
async def run(req: RunRequest) -> AutonomousResult:
    started = time.monotonic()
    try:
        result = await run_autonomous(get_router(), req.goal)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await safe_record(
        kind="agent",
        name="autonomous_agent",
        status="completed" if result.completed else "max_steps_reached",
        latency_ms=int((time.monotonic() - started) * 1000),
        cost_usd=result.cost_usd,
        num_steps=len(result.iterations),
        payload=result.model_dump(),
    )
    return result


async def _heartbeat(run_id: str, interval: float) -> None:
    """Bump the run's updated_at while it works, so the stuck-run sweeper can tell a
    live (slow) run from a hung one. Cancelled when the run finishes."""
    try:
        while True:
            await asyncio.sleep(interval)
            await touch_run(run_id)
    except asyncio.CancelledError:
        pass


async def _execute_run(run_id: str, goal: str) -> None:
    """Background worker: run the agent and persist terminal state. Never raises."""
    # Effectively-once: at-least-once delivery can re-deliver a run (reclaim, a
    # reconcile re-enqueue). If it already finished, don't redo the costly work.
    existing = await get_run(run_id)
    if existing is not None and existing.status in _TERMINAL_STATUSES:
        return

    started = time.monotonic()
    await upsert_run(run_id=run_id, kind=_KIND, status="running", payload={"goal": goal})
    heartbeat = asyncio.create_task(_heartbeat(run_id, get_settings().run_heartbeat_interval_s))
    try:
        try:
            result = await run_autonomous(get_router(), goal)
        except Exception as exc:  # noqa: BLE001 — a background run records failure, not crash
            await upsert_run(
                run_id=run_id, kind=_KIND, status="failed", payload={"goal": goal}, error=str(exc)
            )
            return
        status = "completed" if result.completed else "max_steps_reached"
        await upsert_run(
            run_id=run_id,
            kind=_KIND,
            status=status,
            payload={"goal": goal, "result": result.model_dump()},
        )
        await safe_record(
            kind="agent",
            name="autonomous_agent",
            status=status,
            latency_ms=int((time.monotonic() - started) * 1000),
            cost_usd=result.cost_usd,
            num_steps=len(result.iterations),
            payload=result.model_dump(),
        )
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat


async def _autonomous_job(run_id: str, payload: dict) -> None:
    """Job handler: the worker (in-process or Redis) calls this to run the agent."""
    await _execute_run(run_id, str(payload.get("goal", "")))


# Registered at import; the gateway worker imports the app, so the handler is
# available in the worker process too.
register_handler(_KIND, _autonomous_job)


@router.post("/runs", response_model=RunHandle, status_code=202)
async def submit(
    req: RunRequest,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> RunHandle:
    # Idempotency: a retry with the same key returns the original run, never a second.
    # Fast path (already finished/seen) + a race-safe create backed by the DB UNIQUE.
    if idempotency_key:
        existing = await get_run_by_idempotency_key(_KIND, idempotency_key)
        if existing is not None:
            return RunHandle(run_id=existing.run_id, status=existing.status)
    run_id = uuid.uuid4().hex[:16]
    record = await create_run(
        run_id=run_id,
        kind=_KIND,
        status="pending",
        payload={"goal": req.goal},
        idempotency_key=idempotency_key,
    )
    if record.run_id != run_id:
        # We lost an idempotency race: another submit already created this run.
        # Return the existing handle WITHOUT enqueuing a duplicate job.
        return RunHandle(run_id=record.run_id, status=record.status)
    # Hand off to the queue: in-process (asyncio) by default, or Redis → a separate
    # worker process when WB_JOB_BACKEND=redis.
    await get_queue().enqueue(Job(kind=_KIND, run_id=run_id, payload={"goal": req.goal}))
    return RunHandle(run_id=run_id, status="pending")


@router.get("/runs/{run_id}", response_model=RunView)
async def get_run_status(run_id: str) -> RunView:
    record = await get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    payload = record.payload or {}
    result = (
        AutonomousResult.model_validate(payload["result"])
        if payload.get("result") is not None
        else None
    )
    return RunView(
        run_id=record.run_id,
        status=record.status,
        goal=payload.get("goal"),
        result=result,
        error=record.error,
    )
