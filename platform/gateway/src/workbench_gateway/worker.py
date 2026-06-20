"""Background job worker — the Redis-backed execution process (ADR-010).

Run as a separate process: ``python -m workbench_gateway.worker`` (the compose
``worker`` service / ``make worker``). It imports the gateway app so every demo
app registers its job handlers, then block-pops jobs from Redis and dispatches
them — submit on any gateway replica, execute on any worker.

With the default in-process backend (``WB_JOB_BACKEND=inprocess``) you do **not**
run this: the gateway executes jobs itself as asyncio tasks. This entrypoint only
does work when ``WB_JOB_BACKEND=redis``.
"""

import asyncio
import contextlib

from workbench_jobs import get_queue
from workbench_jobs.queue import RedisQueue

import workbench_gateway.app  # noqa: F401 — import side effect: registers app handlers
from workbench_gateway.reconcile import reconcile_runs, run_sweeper
from workbench_observability import init_db
from workbench_shared.config import get_settings
from workbench_shared.logging import get_logger

log = get_logger(__name__)


async def _main() -> None:
    settings = get_settings()
    if settings.job_backend != "redis":
        log.warning(
            "worker started but WB_JOB_BACKEND is not 'redis' — nothing to consume",
            backend=settings.job_backend,
        )
        return
    await init_db()  # workers persist run state to the same trace DB
    queue = get_queue()
    if not isinstance(queue, RedisQueue):
        log.warning("redis queue unavailable — worker exiting")
        return
    await queue.reclaim()  # recover jobs orphaned in the processing list
    await reconcile_runs(queue)  # recover runs orphaned in the durable store
    sweeper = asyncio.create_task(  # fail runs that hang without a heartbeat
        run_sweeper(settings.run_sweep_interval_s, settings.run_stuck_ttl_s)
    )
    try:
        await queue.consume_forever()
    except asyncio.CancelledError:  # graceful shutdown (SIGTERM)
        log.info("job worker stopped")
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
