"""Background job queue with pluggable backends (durability hardening, ADR-010).

The async run model needs work to run *outside* the request that submits it. Two
backends, selected by config (`WB_JOB_BACKEND`):

* **in-process** (default, zero-config) — schedules the handler as an asyncio task
  in the same process. Fine for dev/demo/tests; needs no Redis. This is exactly
  the behavior the autonomous flagship had before, now behind the queue seam.
* **redis** — pushes the job onto a Redis list; a separate worker process
  (`python -m workbench_gateway.worker`) consumes and runs it. The horizontally-
  scalable path: submit on any gateway replica, execute on any worker, with
  back-pressure (the list) between them.

Handlers register by ``kind``; ``dispatch`` looks one up and runs it. A handler is
``async (run_id, payload) -> None`` and is responsible for recording terminal state
in the durable run store. Redis selection degrades to in-process if the client/URL
is unavailable, so a misconfigured deploy still works rather than dropping jobs.
"""

import asyncio
from collections.abc import Awaitable, Callable
from functools import lru_cache

from pydantic import BaseModel, Field

from workbench_shared.config import get_settings
from workbench_shared.logging import get_logger

log = get_logger(__name__)

JobHandler = Callable[[str, dict], Awaitable[None]]

_HANDLERS: dict[str, JobHandler] = {}
_REDIS_LIST_KEY = "workbench:jobs"
# In-flight jobs live here between pop and ack, so a worker crash mid-job leaves the
# job recoverable (reclaimed on the next worker start) instead of lost.
_REDIS_PROCESSING_KEY = "workbench:jobs:processing"
# A job that keeps getting orphaned (a poison message that crashes its worker every
# time, or an unparseable payload) is moved here after _MAX_ATTEMPTS reclaims, instead
# of looping forever. Inspect/drain out-of-band; nothing auto-consumes it.
_REDIS_DLQ_KEY = "workbench:jobs:dead"
_MAX_ATTEMPTS = 5


class Job(BaseModel):
    # Constrained so a job read off an (untrusted) Redis list can't carry a wild
    # kind/run_id; `dispatch` additionally only runs *registered* kinds (the real
    # allowlist), so an attacker can't invent a handler.
    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    payload: dict = {}
    # Reclaim count: bumped each time a worker crash leaves this job orphaned and the
    # next startup recovers it. Past _MAX_ATTEMPTS it goes to the dead-letter queue.
    attempts: int = 0


def register_handler(kind: str, handler: JobHandler) -> None:
    """Register the worker for a job ``kind`` (idempotent; last registration wins)."""
    _HANDLERS[kind] = handler


def registered_kinds() -> set[str]:
    """The job kinds with a handler in this process — the dispatch allowlist."""
    return set(_HANDLERS)


async def dispatch(job: Job) -> None:
    """Run the handler for ``job.kind``. Never raises — a bad job must not kill a worker."""
    handler = _HANDLERS.get(job.kind)
    if handler is None:
        log.warning("no handler for job kind", kind=job.kind, run_id=job.run_id)
        return
    try:
        await handler(job.run_id, job.payload)
    except Exception as exc:  # noqa: BLE001 — one failed job must not crash the worker loop
        log.warning("job handler failed", kind=job.kind, run_id=job.run_id, error=str(exc))


class InProcessQueue:
    """Runs jobs as asyncio tasks in the current process (default backend).

    Concurrency is bounded by a semaphore (``WB_MAX_INFLIGHT_JOBS``) so a burst of
    submits can't fan out into unbounded parallel LLM runs on the event loop — each
    task waits for a slot before dispatching. ``aclose`` drains in-flight tasks on
    shutdown so runs reach a terminal state instead of being silently abandoned
    (any straggler past the grace period is recovered by the startup reconciler).
    """

    def __init__(self, max_inflight: int = 8) -> None:
        # Hold strong refs so tasks aren't garbage-collected mid-run.
        self._tasks: set[asyncio.Task] = set()
        self._sem = asyncio.Semaphore(max_inflight)

    async def _run(self, job: Job) -> None:
        async with self._sem:  # back-pressure: at most max_inflight dispatch concurrently
            await dispatch(job)

    async def enqueue(self, job: Job) -> None:
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def aclose(self, drain_timeout: float = 10.0) -> None:
        """Wait up to ``drain_timeout`` for in-flight jobs to finish (graceful
        shutdown). Stragglers are left for the reconciler to recover on restart."""
        if not self._tasks:
            return
        pending = list(self._tasks)
        done, still = await asyncio.wait(pending, timeout=drain_timeout)
        if still:
            log.warning("job drain timed out; stragglers left for reconcile", pending=len(still))


class RedisQueue:
    """Pushes jobs to a Redis list; a separate worker process consumes them."""

    def __init__(self, url: str, max_inflight: int = 8) -> None:
        import redis.asyncio as redis  # lazy: only the redis path needs the client

        self._redis = redis.from_url(url)
        # Bound how many jobs one worker runs at once — a single slow job no longer
        # blocks the whole queue, but a worker still can't fan out without limit.
        self._max_inflight = max_inflight

    async def enqueue(self, job: Job) -> None:
        await self._redis.lpush(_REDIS_LIST_KEY, job.model_dump_json())

    async def reclaim(self) -> int:
        """Move jobs orphaned in the processing list (a worker died between pop and
        ack) back onto the main queue, so they're retried rather than lost. Call on
        worker startup. Returns how many were re-queued (excludes dead-lettered).

        Each reclaim bumps the job's ``attempts``; once it exceeds ``_MAX_ATTEMPTS``
        (or its payload is unparseable) the job is moved to the dead-letter queue
        instead of looping forever — a poison message can't wedge the worker."""
        moved = 0
        while True:
            raw = await self._redis.lpop(_REDIS_PROCESSING_KEY)
            if raw is None:
                break
            try:
                job = Job.model_validate_json(raw)
            except Exception as exc:  # noqa: BLE001 — an unparseable orphan goes straight to DLQ
                log.warning("dead-lettering unparseable orphan", error=str(exc))
                await self._redis.rpush(_REDIS_DLQ_KEY, raw)
                continue
            job.attempts += 1
            if job.attempts > _MAX_ATTEMPTS:
                log.warning(
                    "job exceeded max attempts → dead-letter",
                    kind=job.kind,
                    run_id=job.run_id,
                    attempts=job.attempts,
                )
                await self._redis.rpush(_REDIS_DLQ_KEY, job.model_dump_json())
                continue
            await self._redis.rpush(_REDIS_LIST_KEY, job.model_dump_json())
            moved += 1
        if moved:
            log.info("reclaimed orphaned jobs", count=moved)
        return moved

    async def dead_letter_count(self) -> int:
        """How many jobs are parked in the dead-letter queue (for ops/monitoring)."""
        return int(await self._redis.llen(_REDIS_DLQ_KEY))

    async def _process(self, raw, sem: asyncio.Semaphore) -> None:
        """Dispatch one popped job and ack it (LREM from processing). Releases the
        concurrency slot when done. Runs as its own task so a slow job doesn't block
        the pop loop from filling the other slots."""
        try:
            try:
                job = Job.model_validate_json(raw)
            except Exception as exc:  # noqa: BLE001 — skip a malformed payload, keep serving
                log.warning("dropping malformed job", error=str(exc))
                await self._redis.lrem(_REDIS_PROCESSING_KEY, 1, raw)
                return
            # dispatch never raises and persists terminal state itself, so once it
            # returns the job is genuinely done and safe to ack.
            await dispatch(job)
            await self._redis.lrem(_REDIS_PROCESSING_KEY, 1, raw)
        finally:
            sem.release()

    async def consume_forever(self) -> None:
        """Worker loop (at-least-once): atomically move a job to the processing list,
        dispatch it, then ack by removing it from processing. A crash before the ack
        leaves the job in processing for the next worker's reclaim().

        Up to ``max_inflight`` jobs run concurrently: a slot is acquired *before* the
        blocking pop, so the loop never holds more than the bound in flight and a
        single slow job no longer stalls the queue. A concurrent redelivery is still
        safe — the run-level ``claim_run`` lets only one worker execute a given run."""
        log.info("job worker started", backend="redis", key=_REDIS_LIST_KEY)
        sem = asyncio.Semaphore(self._max_inflight)
        tasks: set[asyncio.Task] = set()
        while True:
            await sem.acquire()
            # BLMOVE is atomic: the job is never in neither list. src=RIGHT keeps FIFO
            # (enqueue LPUSHes to the head).
            raw = await self._redis.blmove(
                _REDIS_LIST_KEY, _REDIS_PROCESSING_KEY, 5, "RIGHT", "LEFT"
            )
            if raw is None:
                sem.release()  # idle timeout — free the slot, loop so cancellation is seen
                continue
            task = asyncio.create_task(self._process(raw, sem))
            tasks.add(task)
            task.add_done_callback(tasks.discard)


@lru_cache
def get_queue():
    """The configured queue singleton (in-process unless WB_JOB_BACKEND=redis)."""
    settings = get_settings()
    if settings.job_backend == "redis":
        try:
            return RedisQueue(settings.redis_url, max_inflight=settings.max_inflight_jobs)
        except Exception as exc:  # noqa: BLE001 — never drop jobs on a bad Redis config
            log.warning("redis queue unavailable, using in-process", error=str(exc))
    return InProcessQueue(max_inflight=settings.max_inflight_jobs)


def reset_queue() -> None:
    """Drop the cached queue (tests switching backends)."""
    get_queue.cache_clear()
