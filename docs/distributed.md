# Distributed job queue — delivery guarantees, demonstrated

The async run model (ADR-010) runs work *outside* the request that submits it.
Two backends, one config switch (`WB_JOB_BACKEND`):

| Backend | Topology | When |
|---|---|---|
| `inprocess` (default) | **single-replica** — handler runs as an `asyncio` task in the gateway process | dev, demo, tests; zero-config |
| `redis` | **horizontally scalable** — submit on any gateway replica, execute on any worker; the Redis list is the back-pressure buffer | production / load |

> **Topology boundary (be explicit):** the in-process backend is correct only on
> a *single* gateway replica. Its startup reconciler and sweeper run per-process,
> so N replicas would each re-enqueue the same orphaned runs → up to N concurrent
> re-executions (effectively-once only protects runs already terminal). Horizontal
> scaling is the Redis backend with dedicated workers — there the worker owns
> reclaim/reconcile/sweep, and the gateway replicas only submit. See ADR-010.

## The guarantee

**At-least-once delivery + effectively-once execution.**

- `enqueue` → `LPUSH workbench:jobs`.
- `consume_forever` → `BLMOVE workbench:jobs → workbench:jobs:processing` (atomic;
  the job is never in *neither* list), `dispatch`, then `LREM` from processing
  (the ack). A crash between `BLMOVE` and `LREM` leaves the job in *processing*.
- `reclaim()` on worker startup moves anything stranded in *processing* back onto
  the main queue → orphaned jobs are retried, not lost.
- The handler is **idempotent**: it skips a run that is already in a terminal
  state (`apps/autonomous_agent/.../api.py` → `_execute_run` returns early when
  `get_run` is terminal). So a redelivered, already-finished job does no costly
  work twice.

Net: a job is delivered *at least* once, but the expensive LLM run happens
*effectively* once. This is **not** true exactly-once (a job that crashes
*mid-flight*, before persisting terminal state, is correctly re-run) — see the
boundary section of ADR-010 for why that line is drawn here.

## Proven in CI (deterministic, network-free)

`platform/jobs/tests/test_queue.py::test_two_workers_crash_midjob_reclaim_reruns_without_double_work`
replays the exact crash narrative against a shared fake Redis: worker A pops a
job, runs the side effect, then **dies before the ack**; worker B reclaims the
orphan and re-delivers it. The assertions pin the guarantee:

```
deliveries    == ["run-1", "run-1"]   # at-least-once: handler invoked twice
expensive_runs == ["run-1"]           # effectively-once: executed once
processing list empty                 # finally acked
```

Run it:

```bash
uv run pytest platform/jobs/tests/test_queue.py -q
```

## Reproduce it for real (two workers + one Redis)

```bash
# 1. Bring up the stack with the Redis backend and scale to two workers.
WB_JOB_BACKEND=redis docker compose -f infra/docker/docker-compose.yml \
  --profile redis-jobs up -d --build --scale worker=2
#   (single worker: `make up-distributed`; local worker w/o Docker: `make worker`)

# 2. Submit a long autonomous run (returns 202 + a run_id immediately).
curl -s -X POST localhost:8000/v1/apps/autonomous/runs \
  -H 'Content-Type: application/json' \
  -d '{"goal":"research X and write a short brief"}'
#   → {"run_id":"<id>","status":"pending"}

# 3. While it is "running", kill the worker that picked it up (SIGKILL, no cleanup).
docker compose -f infra/docker/docker-compose.yml ps        # find the worker holding it
docker kill <worker_container_id>

# 4. Watch the surviving worker reclaim the orphan on its next startup/loop and
#    finish the run. Poll the run — it reaches a terminal status, executed once.
curl -s localhost:8000/v1/apps/autonomous/runs/<id>
docker compose -f infra/docker/docker-compose.yml logs -f worker   # "reclaimed orphaned jobs"
```

What you should observe: the run does **not** get stuck or silently dropped when
its worker dies; the other worker picks it up via `reclaim()` and drives it to a
terminal state, and the costly work is not duplicated. If the killed worker had
already finished (terminal state persisted) before dying, the redelivery is a
no-op by the effectively-once guard.

## Crash-recovery layers (where each failure is caught)

| Failure | Caught by |
|---|---|
| Worker dies **between pop and ack** | `reclaim()` on the next worker start moves it from *processing* back to the queue |
| Gateway/worker restarts with `pending`/`running` runs in the store | `reconcile_runs` re-enqueues those that have a registered handler (paused HITL is left alone) |
| Worker **hangs** (alive, not crashed, stops progressing) | heartbeat (`touch_run` bumps `updated_at`) + `run_sweeper` fails runs idle past `WB_RUN_STUCK_TTL_S` |
| Redelivery of an **already-finished** run | effectively-once: handler skips a terminal run |
| Concurrent duplicate submit (same idempotency key) | `UNIQUE(kind, idempotency_key)` + `create_run` catching `IntegrityError` returns the race winner |
| **Poison message** (keeps getting orphaned, or unparseable) | each reclaim bumps `Job.attempts`; past `_MAX_ATTEMPTS` (5) it's moved to the **dead-letter queue** (`workbench:jobs:dead`) instead of looping forever — `dead_letter_count()` surfaces the depth for ops |

## Not done on purpose

Per-job **visibility-timeout/lease** (reclaiming only jobs whose lease expired, vs.
all of `processing` on startup) and true **exactly-once** with partial-result
checkpointing are out of scope — at that point the right move is a purpose-built
engine (Temporal/arq), not more bespoke Redis choreography. A bounded **dead-letter
queue + max-retries** *is* implemented (above), since that is standard queue hygiene
rather than durable-execution machinery. ADR-010 records this boundary.

**Related:** [ADR-010](../wiki/decisions/adr-010-durable-async-runs.md) ·
`platform/jobs/src/workbench_jobs/queue.py` ·
`platform/gateway/src/workbench_gateway/worker.py` ·
`platform/gateway/src/workbench_gateway/reconcile.py`
