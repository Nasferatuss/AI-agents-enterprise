"""Startup reconciliation: recover runs orphaned by a crash.

A run can be left non-terminal in the durable store when the process executing it
dies — an in-process asyncio task lost on a gateway restart, or a Redis job dropped
before a worker recorded terminal state. On startup we re-enqueue every `pending`/
`running` run whose kind still has a registered handler, so the work resumes instead
of hanging forever.

At-least-once: a run already being finished by a peer may be re-run; the run's own
terminal-state writes make that safe. Used by both the gateway lifespan (in-process
backend) and the Redis worker.
"""

import asyncio

from workbench_jobs import Job, registered_kinds

from workbench_observability import list_nonterminal_runs, sweep_stuck_runs
from workbench_shared.config import get_settings
from workbench_shared.logging import get_logger

log = get_logger(__name__)

# A run is swept as dead only after ttl_s without a heartbeat; if the TTL isn't well
# clear of the heartbeat interval, a slow-but-alive run can be wrongly failed.
_MIN_TTL_HEARTBEAT_RATIO = 3


async def reconcile_runs(queue) -> int:
    """Re-enqueue non-terminal runs with a registered handler. Returns the count."""
    runs = await list_nonterminal_runs()
    kinds = registered_kinds()
    n = 0
    for r in runs:
        if r.kind in kinds:
            await queue.enqueue(Job(kind=r.kind, run_id=r.run_id, payload=r.payload))
            n += 1
    if n:
        log.info("reconciled orphaned runs", count=n)
    return n


async def run_sweeper(interval_s: int, ttl_s: int) -> None:
    """Periodically fail runs that stopped heartbeating (a hung worker that neither
    crashed nor finished). Loops until cancelled; idempotent, so it's safe even if
    more than one replica runs it."""
    heartbeat_s = get_settings().run_heartbeat_interval_s
    if ttl_s < _MIN_TTL_HEARTBEAT_RATIO * heartbeat_s:
        # Misconfiguration footgun: the sweeper would fail live-but-slow runs.
        log.warning(
            "run_stuck_ttl_s is close to the heartbeat interval — alive runs may be swept",
            ttl_s=ttl_s,
            heartbeat_s=heartbeat_s,
            recommended_min_ttl_s=_MIN_TTL_HEARTBEAT_RATIO * heartbeat_s,
        )
    while True:
        await asyncio.sleep(interval_s)
        await sweep_stuck_runs(ttl_s)
