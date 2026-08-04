import json

import httpx
import pytest

from workbench_runtime.pricing import estimate_cost_usd
from workbench_runtime.providers import Provider, build_registry
from workbench_runtime.router import ModelRouter, NoProviderAvailableError
from workbench_runtime.types import ChatMessage
from workbench_shared.config import get_settings

ALL_KEY_ENVS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY"]


@pytest.fixture
def clean_env(monkeypatch):
    for env in ALL_KEY_ENVS:
        monkeypatch.delenv(env, raising=False)
    return monkeypatch


def test_suite_is_hermetic_provider_keys_stripped():
    # Sentinel for the root conftest's hermetic env (the P0 fix). Runs in CI on every
    # pytest. If a change ever lets a developer's real .env leak provider keys into the
    # test process, this fails loudly here — instead of silently flipping the
    # "no provider -> 503" tests green-in-CI / red-on-a-laptop-with-keys.
    import os

    for env in ALL_KEY_ENVS + ["MIMO_API_KEY"]:
        assert os.environ.get(env) is None, f"{env} leaked into the test environment"
    enabled = {name for name, p in build_registry().items() if p.enabled}
    assert enabled == {"local"}, f"only the keyless local provider should be enabled, got {enabled}"


def test_suite_is_hermetic_dotenv_detached():
    # The companion sentinel: provider keys are read from os.environ, but every
    # WB_* setting comes from pydantic-settings, which reads .env on its own.
    # Nothing in a developer's .env may reach the suite — WB_ROUTE_STANDARD_VIA_LOCAL
    # alone silently rewrites the routing chain the tests below assert on.
    from workbench_shared.config import Settings

    assert Settings.model_config["env_file"] is None
    assert get_settings().route_standard_via_local is False


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


async def test_zero_cooldown_never_skips(monkeypatch):
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


async def test_cooldown_expires_and_provider_retried(monkeypatch):
    # True time-based expiry: a provider marked unhealthy is skipped WHILE in cooldown
    # and retried once the deadline passes. Drive time via a fake monotonic clock so
    # the test is deterministic (no sleeps).
    import workbench_runtime.router as router_mod

    monkeypatch.setattr(router_mod, "_HEALTH_COOLDOWN_S", 30.0)
    clock = {"t": 1000.0}
    monkeypatch.setattr(router_mod.time, "monotonic", lambda: clock["t"])

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

    # t=1000: "a" fails → unhealthy until 1030; "b" serves.
    await router.complete([ChatMessage(role="user", content="1")])
    assert calls == {"a": 1, "b": 1}

    # t=1010: still within cooldown → "a" skipped entirely.
    clock["t"] = 1010.0
    await router.complete([ChatMessage(role="user", content="2")])
    assert calls == {"a": 1, "b": 2}

    # t=1041: cooldown expired → "a" is tried again (fails), then falls back to "b".
    clock["t"] = 1041.0
    await router.complete([ChatMessage(role="user", content="3")])
    assert calls == {"a": 2, "b": 3}


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
    assert captured[0].read == get_settings().local_read_timeout_s
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


async def test_local_read_timeout_is_configurable(monkeypatch):
    # A cold 30B model takes longer to answer than the API default allows; without
    # a way to raise the read budget the router writes the box off and pays an API.
    import workbench_runtime.clients as clients
    from workbench_runtime.types import UserMessage

    monkeypatch.setenv("WB_LOCAL_READ_TIMEOUT_S", "600")
    get_settings.cache_clear()
    captured: list[object] = []

    async def fake_post(url, **kwargs):
        captured.append(kwargs["timeout"])
        return httpx.Response(200, json=_completion_payload("ok"))

    http = httpx.AsyncClient()
    http.post = fake_post  # type: ignore[method-assign]
    await clients.step_openai_compatible(
        http, _fake_provider("local", "local"), "m", [UserMessage(content="hi")], [], None, 16
    )

    assert captured[0].read == 600.0
    assert captured[0].connect == clients._LOCAL_CONNECT_TIMEOUT_S  # still fails fast when offline


async def test_local_reasoning_model_retried_without_thinking():
    # Ollama puts a reasoning model's chain of thought in "reasoning" and leaves
    # "content" empty. Retry without thinking instead of returning "" — which
    # the callers report as an unexplainable parse failure.
    import workbench_runtime.clients as clients
    from workbench_runtime.types import UserMessage

    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "reasoning_effort" not in body:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "", "reasoning": "…"}}
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 512},
                },
            )
        return httpx.Response(200, json=_completion_payload('{"action":"finish"}'))

    out = await clients.step_openai_compatible(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        _fake_provider("local", "local"),
        "qwen3:4b",
        [UserMessage(content="hi")],
        [],
        None,
        512,
    )

    assert out.text == '{"action":"finish"}'
    assert "reasoning_effort" not in bodies[0]
    assert bodies[1]["reasoning_effort"] == "none"


async def test_local_reasoning_model_that_never_answers_is_an_error():
    # If the retry is still all thought, fail loudly so the router falls back
    # and the log says why, rather than passing "" down the stack.
    import workbench_runtime.clients as clients
    from workbench_runtime.types import UserMessage

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "", "reasoning": "…"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 512},
            },
        )

    with pytest.raises(clients.ProviderCallError, match="chain-of-thought"):
        await clients.step_openai_compatible(
            httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            _fake_provider("local", "local"),
            "qwen3:4b",
            [UserMessage(content="hi")],
            [],
            None,
            512,
        )


async def test_hosted_provider_is_never_asked_to_skip_thinking():
    # reasoning_effort="none" is an Ollama-ism; hosted APIs reject it. An empty
    # answer from a hosted provider stays empty.
    import workbench_runtime.clients as clients
    from workbench_runtime.types import UserMessage

    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "", "reasoning": "…"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 512},
            },
        )

    hosted = Provider(
        name="ds", kind="openai_compatible", base_url="http://y/v1", api_key_env="X", models={}
    )
    out = await clients.step_openai_compatible(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        hosted,
        "m",
        [UserMessage(content="hi")],
        [],
        None,
        512,
    )

    assert out.text == ""
    assert len(bodies) == 1


async def _noop_sleep(_seconds):
    return None


def test_pricing():
    assert estimate_cost_usd("claude-haiku-4-5", 1_000_000, 0) == 1.00
    assert estimate_cost_usd("qwen2.5:3b-instruct", 1000, 1000) == 0.0
    assert estimate_cost_usd("totally-unknown-model", 1000, 1000) is None
