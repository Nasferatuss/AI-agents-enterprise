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

from workbench_jobs import Job, registered_kinds

from workbench_observability import list_nonterminal_runs
from workbench_shared.logging import get_logger

log = get_logger(__name__)


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
