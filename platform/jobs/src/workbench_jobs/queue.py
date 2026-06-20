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

from pydantic import BaseModel

from workbench_shared.config import get_settings
from workbench_shared.logging import get_logger

log = get_logger(__name__)

JobHandler = Callable[[str, dict], Awaitable[None]]

_HANDLERS: dict[str, JobHandler] = {}
_REDIS_LIST_KEY = "workbench:jobs"


class Job(BaseModel):
    kind: str
    run_id: str
    payload: dict = {}


def register_handler(kind: str, handler: JobHandler) -> None:
    """Register the worker for a job ``kind`` (idempotent; last registration wins)."""
    _HANDLERS[kind] = handler


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
    """Runs jobs as asyncio tasks in the current process (default backend)."""

    def __init__(self) -> None:
        # Hold strong refs so tasks aren't garbage-collected mid-run.
        self._tasks: set[asyncio.Task] = set()

    async def enqueue(self, job: Job) -> None:
        task = asyncio.create_task(dispatch(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


class RedisQueue:
    """Pushes jobs to a Redis list; a separate worker process consumes them."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # lazy: only the redis path needs the client

        self._redis = redis.from_url(url)

    async def enqueue(self, job: Job) -> None:
        await self._redis.lpush(_REDIS_LIST_KEY, job.model_dump_json())

    async def consume_forever(self) -> None:
        """Worker loop: block-pop jobs and dispatch them until cancelled."""
        log.info("job worker started", backend="redis", key=_REDIS_LIST_KEY)
        while True:
            popped = await self._redis.brpop([_REDIS_LIST_KEY], timeout=5)
            if popped is None:
                continue  # idle timeout — loop so cancellation can be observed
            _, raw = popped
            try:
                job = Job.model_validate_json(raw)
            except Exception as exc:  # noqa: BLE001 — skip a malformed payload, keep serving
                log.warning("dropping malformed job", error=str(exc))
                continue
            await dispatch(job)


@lru_cache
def get_queue():
    """The configured queue singleton (in-process unless WB_JOB_BACKEND=redis)."""
    settings = get_settings()
    if settings.job_backend == "redis":
        try:
            return RedisQueue(settings.redis_url)
        except Exception as exc:  # noqa: BLE001 — never drop jobs on a bad Redis config
            log.warning("redis queue unavailable, using in-process", error=str(exc))
    return InProcessQueue()


def reset_queue() -> None:
    """Drop the cached queue (tests switching backends)."""
    get_queue.cache_clear()
