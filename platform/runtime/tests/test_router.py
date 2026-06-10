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


def test_pricing():
    assert estimate_cost_usd("claude-haiku-4-5", 1_000_000, 0) == 1.00
    assert estimate_cost_usd("qwen2.5:3b-instruct", 1000, 1000) == 0.0
    assert estimate_cost_usd("totally-unknown-model", 1000, 1000) is None
