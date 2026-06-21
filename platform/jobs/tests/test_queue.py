"""Job queue: in-process default path, dispatch safety, and the Redis backend (faked)."""

import asyncio
import contextlib

import pytest
from workbench_jobs import Job, get_queue, register_handler, reset_queue
from workbench_jobs import queue as q


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(q, "_HANDLERS", {})
    reset_queue()
    yield
    reset_queue()


async def test_inprocess_queue_runs_handler():
    seen: list[tuple[str, dict]] = []

    async def handler(run_id, payload):
        seen.append((run_id, payload))

    register_handler("demo", handler)
    iq = q.InProcessQueue()
    await iq.enqueue(Job(kind="demo", run_id="r1", payload={"x": 1}))
    for _ in range(20):
        await asyncio.sleep(0)
        if seen:
            break
    assert seen == [("r1", {"x": 1})]


async def test_dispatch_unknown_kind_is_noop():
    await q.dispatch(Job(kind="ghost", run_id="r1"))  # must not raise


async def test_dispatch_swallows_handler_error():
    async def boom(run_id, payload):
        raise RuntimeError("kaboom")

    register_handler("demo", boom)
    await q.dispatch(Job(kind="demo", run_id="r1"))  # must not propagate


def test_get_queue_defaults_to_inprocess(monkeypatch):
    monkeypatch.setenv("WB_JOB_BACKEND", "inprocess")
    from workbench_shared.config import get_settings

    get_settings.cache_clear()
    reset_queue()
    assert isinstance(get_queue(), q.InProcessQueue)
    get_settings.cache_clear()


class _FakeRedis:
    """Minimal in-memory stand-in. index 0 = LEFT/head, index -1 = RIGHT/tail."""

    def __init__(self):
        self.lists: dict[str, list] = {}

    async def lpush(self, key, val):
        self.lists.setdefault(key, []).insert(0, val)

    async def lpop(self, key):
        lst = self.lists.get(key)
        return lst.pop(0) if lst else None

    async def rpush(self, key, val):
        self.lists.setdefault(key, []).append(val)

    async def llen(self, key):
        return len(self.lists.get(key, []))

    def _pop(self, key, pos):
        lst = self.lists.get(key)
        if not lst:
            return None
        return lst.pop(0) if pos == "LEFT" else lst.pop()

    def _push(self, key, val, pos):
        lst = self.lists.setdefault(key, [])
        lst.insert(0, val) if pos == "LEFT" else lst.append(val)

    async def lmove(self, src, dst, src_pos="LEFT", dst_pos="RIGHT"):
        val = self._pop(src, src_pos)
        if val is not None:
            self._push(dst, val, dst_pos)
        return val

    async def blmove(self, src, dst, timeout, src_pos="LEFT", dst_pos="RIGHT"):  # noqa: ASYNC109
        await asyncio.sleep(0)  # real blmove awaits I/O; yield so the loop stays cooperative
        return await self.lmove(src, dst, src_pos, dst_pos)

    async def lrem(self, key, count, value):
        lst = self.lists.get(key, [])
        if value in lst:
            lst.remove(value)


def _install_fake_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    import redis.asyncio as redis_async

    monkeypatch.setattr(redis_async, "from_url", lambda url: fake)
    return fake


async def test_redis_queue_enqueue_pushes_json(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    rq = q.RedisQueue("redis://x")
    await rq.enqueue(Job(kind="demo", run_id="r1", payload={"x": 1}))
    assert fake.lists[q._REDIS_LIST_KEY]
    raw = fake.lists[q._REDIS_LIST_KEY][0]
    assert Job.model_validate_json(raw).run_id == "r1"


async def test_redis_worker_consumes_and_dispatches(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    seen: list[str] = []

    async def handler(run_id, payload):
        seen.append(run_id)

    register_handler("demo", handler)
    rq = q.RedisQueue("redis://x")
    await rq.enqueue(Job(kind="demo", run_id="r1"))

    worker = asyncio.create_task(rq.consume_forever())
    for _ in range(50):
        await asyncio.sleep(0)
        if seen:
            break
    worker.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker  # let the cancellation settle so no task leaks past the test
    assert seen == ["r1"]
    # at-least-once: the job is acked (removed from the processing list) after dispatch
    assert not fake.lists.get(q._REDIS_PROCESSING_KEY)


async def test_redis_reclaim_returns_orphaned_jobs(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    rq = q.RedisQueue("redis://x")
    # Simulate a worker that died mid-job: a job stuck in the processing list.
    fake.lists[q._REDIS_PROCESSING_KEY] = [Job(kind="demo", run_id="r1").model_dump_json()]
    moved = await rq.reclaim()
    assert moved == 1
    assert not fake.lists.get(q._REDIS_PROCESSING_KEY)  # processing drained
    assert fake.lists[q._REDIS_LIST_KEY]  # back on the main queue


async def test_two_workers_crash_midjob_reclaim_reruns_without_double_work(monkeypatch):
    """End-to-end distributed proof — the reviewer's exact scenario.

    Worker A dies *after* the costly side effect but *before* the ack; worker B,
    a fresh process on the SAME Redis, reclaims the stranded job and re-delivers
    it. At-least-once means the handler is invoked twice; the effectively-once
    guard (skip a run already in a terminal state) means the expensive work runs
    exactly ONCE. Two deliveries, one execution — that is the whole guarantee.

    The real autonomous handler does the same terminal-status check against the
    durable run store (apps/autonomous_agent .../api.py: ``_execute_run`` returns
    early when ``get_run`` is already terminal). Here a dict stands in for that
    store so the proof stays at the queue layer and network-free.
    """
    fake = _install_fake_redis(monkeypatch)
    run_status: dict[str, str] = {}  # the durable run store's status column, in miniature
    deliveries: list[str] = []  # every handler invocation (at-least-once may repeat)
    expensive_runs: list[str] = []  # the costly side effect (must happen once)

    async def handler(run_id, payload):
        deliveries.append(run_id)
        if run_status.get(run_id) in ("completed", "failed"):
            return  # effectively-once: already done — don't redo the expensive run
        expensive_runs.append(run_id)  # the one costly LLM run
        run_status[run_id] = "completed"  # persist terminal state

    register_handler("autonomous", handler)

    # --- Worker A: pop → run side effect → CRASH before the lrem ack ---
    qa = q.RedisQueue("redis://shared")
    await qa.enqueue(Job(kind="autonomous", run_id="run-1", payload={"goal": "x"}))
    raw = await fake.blmove(q._REDIS_LIST_KEY, q._REDIS_PROCESSING_KEY, 5, "RIGHT", "LEFT")
    await q.dispatch(Job.model_validate_json(raw))  # side effect happens here
    # process dies now: no ack. The job is stranded in the processing list.
    assert expensive_runs == ["run-1"]
    assert fake.lists[q._REDIS_PROCESSING_KEY] == [raw]  # orphaned, not acked

    # --- Worker B: fresh process on the same Redis → reclaim + re-deliver ---
    qb = q.RedisQueue("redis://shared")
    assert await qb.reclaim() == 1  # orphan moved back onto the main queue
    worker = asyncio.create_task(qb.consume_forever())
    for _ in range(50):
        await asyncio.sleep(0)
        drained = not fake.lists.get(q._REDIS_LIST_KEY) and not fake.lists.get(
            q._REDIS_PROCESSING_KEY
        )
        if drained and len(deliveries) >= 2:
            break
    worker.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker

    assert deliveries == ["run-1", "run-1"]  # at-least-once: delivered twice
    assert expensive_runs == ["run-1"]  # effectively-once: executed once
    assert not fake.lists.get(q._REDIS_PROCESSING_KEY)  # finally acked
    assert run_status == {"run-1": "completed"}


async def test_reclaim_bumps_attempts(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    rq = q.RedisQueue("redis://x")
    fake.lists[q._REDIS_PROCESSING_KEY] = [Job(kind="demo", run_id="r1").model_dump_json()]
    assert await rq.reclaim() == 1
    requeued = Job.model_validate_json(fake.lists[q._REDIS_LIST_KEY][0])
    assert requeued.attempts == 1  # one orphan-recovery recorded


async def test_poison_job_goes_to_dead_letter_after_max_attempts(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    rq = q.RedisQueue("redis://x")
    # A job already at the attempt ceiling: the next reclaim must dead-letter it,
    # not re-queue it — so a poison message can't loop forever.
    poisoned = Job(kind="demo", run_id="r1", attempts=q._MAX_ATTEMPTS)
    fake.lists[q._REDIS_PROCESSING_KEY] = [poisoned.model_dump_json()]
    assert await rq.reclaim() == 0  # not re-queued
    assert not fake.lists.get(q._REDIS_LIST_KEY)  # main queue stays empty
    assert await rq.dead_letter_count() == 1  # parked in the DLQ instead


async def test_unparseable_orphan_is_dead_lettered(monkeypatch):
    fake = _install_fake_redis(monkeypatch)
    rq = q.RedisQueue("redis://x")
    fake.lists[q._REDIS_PROCESSING_KEY] = ["{not valid json"]
    assert await rq.reclaim() == 0
    assert await rq.dead_letter_count() == 1


def test_job_rejects_untrusted_kind_and_run_id():
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError):
        Job(kind="Bad Kind!", run_id="r1")  # spaces/caps/punct not allowed
    with _pytest.raises(ValidationError):
        Job(kind="demo", run_id="../etc/passwd")  # only [A-Za-z0-9_-]


async def test_get_queue_redis_backend(monkeypatch):
    _install_fake_redis(monkeypatch)
    monkeypatch.setenv("WB_JOB_BACKEND", "redis")
    from workbench_shared.config import get_settings

    get_settings.cache_clear()
    reset_queue()
    assert isinstance(get_queue(), q.RedisQueue)
    get_settings.cache_clear()
    reset_queue()
