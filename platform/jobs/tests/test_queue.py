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
    def __init__(self):
        self.lists: dict[str, list] = {}

    async def lpush(self, key, val):
        self.lists.setdefault(key, []).insert(0, val)

    async def brpop(self, keys, timeout=0):  # noqa: ASYNC109 — mirrors redis-py's API
        await asyncio.sleep(0)  # real brpop awaits I/O; yield so the loop stays cooperative
        for key in keys:
            if self.lists.get(key):
                return (key, self.lists[key].pop())
        return None


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
    _install_fake_redis(monkeypatch)
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


async def test_get_queue_redis_backend(monkeypatch):
    _install_fake_redis(monkeypatch)
    monkeypatch.setenv("WB_JOB_BACKEND", "redis")
    from workbench_shared.config import get_settings

    get_settings.cache_clear()
    reset_queue()
    assert isinstance(get_queue(), q.RedisQueue)
    get_settings.cache_clear()
    reset_queue()
