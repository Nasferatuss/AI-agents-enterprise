import httpx
import pytest

from workbench_runtime.pricing import estimate_cost_usd
from workbench_runtime.providers import Provider, build_registry
from workbench_runtime.router import ModelRouter, NoProviderAvailableError
from workbench_runtime.types import ChatMessage

ALL_KEY_ENVS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY"]


@pytest.fixture
def clean_env(monkeypatch):
    for env in ALL_KEY_ENVS:
        monkeypatch.delenv(env, raising=False)
    return monkeypatch


def test_chain_local_only_without_keys(clean_env):
    router = ModelRouter(registry=build_registry())
    assert router.chain("simple") == [("local", "default")]
    assert router.chain("standard") == []  # local excluded until a stronger model is pulled
    assert router.chain("complex") == []


def test_chain_local_first_then_cheap_then_frontier(clean_env):
    clean_env.setenv("DEEPSEEK_API_KEY", "x")
    clean_env.setenv("ANTHROPIC_API_KEY", "x")
    router = ModelRouter(registry=build_registry())

    assert router.chain("simple") == [
        ("local", "default"),
        ("deepseek", "default"),
        ("anthropic", "small"),
    ]
    assert router.chain("standard") == [("deepseek", "default"), ("anthropic", "default")]
    assert router.chain("complex") == [("anthropic", "default")]
    assert router.chain("judge") == [("anthropic", "default")]


def _fake_provider(name: str, host: str) -> Provider:
    return Provider(
        name=name,
        kind="openai_compatible",
        base_url=f"http://{host}/v1",
        api_key_env="",
        models={"default": f"{name}-model"},
    )


def _completion_payload(text: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


async def test_fallback_to_next_provider_on_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a":
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=_completion_payload("hello"))

    registry = {"a": _fake_provider("a", "a"), "b": _fake_provider("b", "b")}
    router = ModelRouter(
        registry=registry, http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    router.chain = lambda complexity: [("a", "default"), ("b", "default")]  # type: ignore[method-assign]

    completion = await router.complete([ChatMessage(role="user", content="hi")])

    assert completion.provider == "b"
    assert completion.text == "hello"
    assert completion.attempts == ["a/a-model"]
    assert completion.usage.input_tokens == 10


async def test_all_providers_failing_raises():
    handler = lambda request: httpx.Response(503, text="down")  # noqa: E731
    registry = {"a": _fake_provider("a", "a")}
    router = ModelRouter(
        registry=registry, http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    router.chain = lambda complexity: [("a", "default")]  # type: ignore[method-assign]

    with pytest.raises(NoProviderAvailableError):
        await router.complete([ChatMessage(role="user", content="hi")])


async def test_unhealthy_provider_skipped_until_cooldown(monkeypatch):
    import workbench_runtime.router as router_mod

    monkeypatch.setattr(router_mod, "_HEALTH_COOLDOWN_S", 30.0)
    calls = {"a": 0, "b": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls[request.url.host] += 1
        if request.url.host == "a":
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=_completion_payload("ok"))

    registry = {"a": _fake_provider("a", "a"), "b": _fake_provider("b", "b")}
    router = ModelRouter(
        registry=registry, http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    router.chain = lambda complexity: [("a", "default"), ("b", "default")]  # type: ignore[method-assign]

    await router.complete([ChatMessage(role="user", content="1")])
    await router.complete([ChatMessage(role="user", content="2")])

    # "a" failed once and is now in cooldown — the second request skips it entirely.
    assert calls["a"] == 1
    assert calls["b"] == 2


async def test_cooldown_clears_after_expiry(monkeypatch):
    import workbench_runtime.router as router_mod

    monkeypatch.setattr(router_mod, "_HEALTH_COOLDOWN_S", 0.0)  # never cools down → never skipped

    calls = {"a": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["a"] += 1
        return httpx.Response(500, text="boom")

    registry = {"a": _fake_provider("a", "a")}
    router = ModelRouter(
        registry=registry, http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    router.chain = lambda complexity: [("a", "default")]  # type: ignore[method-assign]

    for _ in range(3):
        with pytest.raises(NoProviderAvailableError):
            await router.complete([ChatMessage(role="user", content="x")])
    # With cooldown disabled, "a" is retried every request rather than skipped.
    assert calls["a"] == 3


async def test_local_provider_uses_short_connect_timeout():
    # An offline local box must fail fast (short connect timeout) so fallback is
    # quick, while API providers keep the full timeout.
    import workbench_runtime.clients as clients
    from workbench_runtime.types import UserMessage

    captured: list[object] = []

    async def fake_post(url, **kwargs):
        captured.append(kwargs["timeout"])
        return httpx.Response(200, json=_completion_payload("ok"))

    local = Provider(
        name="local", kind="openai_compatible", base_url="http://x/v1", api_key_env="", models={}
    )
    api = Provider(
        name="ds", kind="openai_compatible", base_url="http://y/v1", api_key_env="X", models={}
    )
    http = httpx.AsyncClient()
    http.post = fake_post  # type: ignore[method-assign]
    transcript = [UserMessage(content="hi")]

    await clients.step_openai_compatible(http, local, "m", transcript, [], None, 16)
    await clients.step_openai_compatible(http, api, "m", transcript, [], None, 16)

    assert isinstance(captured[0], httpx.Timeout)  # local → granular timeout w/ short connect
    assert captured[0].connect == clients._LOCAL_CONNECT_TIMEOUT_S
    assert captured[1] == clients._TIMEOUT_S  # API → plain full timeout


async def test_retry_on_503_then_success(monkeypatch):
    import workbench_runtime.clients as clients

    monkeypatch.setattr(clients.asyncio, "sleep", _noop_sleep)
    seq = iter([503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(seq)
        if status == 200:
            return httpx.Response(200, json=_completion_payload("recovered"))
        return httpx.Response(503, text="overloaded")

    provider = _fake_provider("a", "a")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from workbench_runtime.types import UserMessage

    out = await clients.step_openai_compatible(
        http, provider, "m", [UserMessage(content="hi")], [], None, 16
    )
    assert out.text == "recovered"


async def _noop_sleep(_seconds):
    return None


def test_pricing():
    assert estimate_cost_usd("claude-haiku-4-5", 1_000_000, 0) == 1.00
    assert estimate_cost_usd("qwen2.5:3b-instruct", 1000, 1000) == 0.0
    assert estimate_cost_usd("totally-unknown-model", 1000, 1000) is None
