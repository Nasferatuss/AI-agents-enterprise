import json

import httpx
from pydantic import BaseModel

from workbench_runtime.agent import Agent, run_agent
from workbench_runtime.context import (
    ContextEngine,
    ContextPolicy,
    choose_cut,
    estimate_tokens,
    render_transcript,
)
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter
from workbench_runtime.tools import Tool
from workbench_runtime.types import (
    AssistantMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


class EchoInput(BaseModel):
    value: str


def make_agent(**overrides) -> Agent:
    defaults = dict(
        name="test",
        instructions="You are a test agent.",
        tools=[
            Tool(
                name="echo",
                description="Echo a value",
                input_model=EchoInput,
                handler=lambda inp: f"echo:{inp.value}",
            )
        ],
    )
    return Agent(**{**defaults, **overrides})


def _tool_call_response(name: str, arguments: dict) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def _text_response(text: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 7},
    }


def _transcript(n_pairs: int):
    items = [UserMessage(content="start " + "x" * 200)]
    for i in range(n_pairs):
        items.append(
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(id=f"t{i}", name="echo", arguments={"value": "v" * 100})],
            )
        )
        items.append(ToolResultMessage(tool_call_id=f"t{i}", name="echo", content="r" * 200))
    return items


def test_estimate_tokens_grows_with_content():
    small = estimate_tokens(_transcript(1))
    large = estimate_tokens(_transcript(10))
    assert large > small > 0


def test_choose_cut_never_lands_on_tool_result():
    transcript = _transcript(5)  # user, (assistant, tool) * 5
    for keep in range(1, len(transcript)):
        cut = choose_cut(transcript, keep)
        assert cut == len(transcript) or not isinstance(transcript[cut], ToolResultMessage)


def test_bundle_renders_stable_sections():
    engine = ContextEngine(router=None)  # build() doesn't touch the router
    bundle = engine.build(
        "Be helpful.", memory=["likes terse answers"], retrieved=None, task_state="step 2 of 5"
    )
    system = bundle.render_system()
    assert system.index("<instructions>") < system.index("<memory>") < system.index("<task_state>")
    assert "<retrieved_context>" not in system  # empty parts skipped


def _summarizing_router(summary_text: str) -> ModelRouter:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # summarizer call carries the compression system prompt
        if any(m.get("role") == "system" and "compress" in m["content"] for m in body["messages"]):
            return httpx.Response(200, json=_text_response(summary_text))
        return httpx.Response(200, json=_text_response("unexpected"))

    provider = Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )
    router = ModelRouter(
        registry={"fake": provider},
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    router.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]
    return router


async def test_maybe_compact_replaces_old_turns_with_summary():
    router = _summarizing_router("the user asked to echo things")
    policy = ContextPolicy(max_context_tokens=100, compact_trigger_ratio=0.5, keep_recent_items=3)
    engine = ContextEngine(router, policy)
    transcript = _transcript(6)

    compacted, event = await engine.maybe_compact(transcript, step=2)

    assert event is not None
    assert event.tokens_after < event.tokens_before
    assert event.summarized_items == len(transcript) - len(compacted) + 1
    assert "conversation summary" in compacted[0].content
    assert "the user asked to echo things" in compacted[0].content
    assert compacted[1:] == transcript[-(len(compacted) - 1) :]


async def test_maybe_compact_noop_under_budget():
    engine = ContextEngine(router=None, policy=ContextPolicy(max_context_tokens=10_000_000))
    transcript = _transcript(2)
    out, event = await engine.maybe_compact(transcript, step=0)
    assert out is transcript
    assert event is None


async def test_run_agent_records_context_and_compactions():
    responses = [
        _tool_call_response("echo", {"value": "a" * 400}),
        _tool_call_response("echo", {"value": "b" * 400}),
        _text_response("final"),
    ]
    calls = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if any(m.get("role") == "system" and "compress" in m["content"] for m in body["messages"]):
            return httpx.Response(200, json=_text_response("summary of earlier steps"))
        return httpx.Response(200, json=next(calls))

    provider = Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )
    router = ModelRouter(
        registry={"fake": provider},
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    router.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]

    agent = make_agent(
        context_policy=ContextPolicy(
            max_context_tokens=120, compact_trigger_ratio=0.5, keep_recent_items=2
        )
    )
    run = await run_agent(agent, "echo a lot", router=router, memory=["user prefers brevity"])

    assert run.status == "completed"
    assert run.final_text == "final"
    assert [p.name for p in run.context.parts] == ["instructions", "memory"]
    assert len(run.context.compactions) >= 1
    assert run.context.compactions[0].tokens_after < run.context.compactions[0].tokens_before


def test_render_transcript_readable():
    text = render_transcript(_transcript(1))
    assert "user: start" in text
    assert "assistant → tool echo" in text
    assert "tool echo [ok]" in text
