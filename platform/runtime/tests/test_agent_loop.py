import json

import httpx
import pytest
from pydantic import BaseModel, Field

from workbench_runtime.agent import Agent, run_agent
from workbench_runtime.clients import to_anthropic_messages, to_openai_messages
from workbench_runtime.demo import DEMO_AGENT, CalculatorInput, calculator
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter
from workbench_runtime.tools import Tool, execute_tool
from workbench_runtime.types import (
    AssistantMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


class EchoInput(BaseModel):
    value: str = Field(description="Value to echo")


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


def _provider() -> Provider:
    return Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )


def _router_with(responses: list[dict]) -> ModelRouter:
    calls = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(calls))

    router = ModelRouter(
        registry={"fake": _provider()},
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    router.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]
    return router


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


async def test_agent_loop_executes_tool_and_finishes():
    router = _router_with(
        [_tool_call_response("echo", {"value": "hi"}), _text_response("done: echo:hi")]
    )
    run = await run_agent(make_agent(), "please echo hi", router=router)

    assert run.status == "completed"
    assert run.final_text == "done: echo:hi"
    assert len(run.steps) == 2
    execution = run.steps[0].tool_executions[0]
    assert execution.result == "echo:hi"
    assert execution.is_error is False
    assert run.usage.input_tokens == 30
    assert run.usage.output_tokens == 12


async def test_agent_loop_reports_unknown_tool_and_recovers():
    router = _router_with([_tool_call_response("nope", {}), _text_response("recovered")])
    run = await run_agent(make_agent(), "x", router=router)

    assert run.status == "completed"
    assert run.steps[0].tool_executions[0].is_error is True
    assert "Unknown tool" in run.steps[0].tool_executions[0].result


async def test_agent_loop_stops_at_max_steps():
    router = _router_with([_tool_call_response("echo", {"value": "loop"})] * 3)
    run = await run_agent(make_agent(max_steps=3), "x", router=router)

    assert run.status == "max_steps_reached"
    assert len(run.steps) == 3


async def test_execute_tool_validates_arguments():
    tool = make_agent().tools[0]
    result, is_error = await execute_tool(tool, {"wrong_field": 1})
    assert is_error is True
    assert "Invalid arguments" in result


def test_transcript_renders_to_both_wire_formats():
    transcript = [
        UserMessage(content="hi"),
        AssistantMessage(
            content="", tool_calls=[ToolCall(id="t1", name="echo", arguments={"value": "x"})]
        ),
        ToolResultMessage(tool_call_id="t1", name="echo", content="echo:x"),
    ]

    oai = to_openai_messages(transcript, system="sys")
    assert oai[0] == {"role": "system", "content": "sys"}
    assert oai[2]["tool_calls"][0]["function"]["name"] == "echo"
    assert oai[3] == {"role": "tool", "tool_call_id": "t1", "content": "echo:x"}

    ant = to_anthropic_messages(transcript)
    assert ant[1]["content"][0] == {
        "type": "tool_use",
        "id": "t1",
        "name": "echo",
        "input": {"value": "x"},
    }
    assert ant[2]["content"][0]["tool_use_id"] == "t1"
    assert ant[2]["role"] == "user"


def test_wire_renderers_reject_non_transcript_items():
    # A ChatMessage (the /v1/chat type) is NOT a Transcript item. If one slips into
    # step(), both renderers must fail loudly rather than drop the user turn — which
    # silently makes OpenAI answer from the system prompt alone and Anthropic 400.
    from workbench_runtime.types import ChatMessage

    bogus = [ChatMessage(role="user", content="hi")]
    with pytest.raises(ValueError, match="produced no messages"):
        to_openai_messages(bogus, system="sys")
    with pytest.raises(ValueError, match="produced no messages"):
        to_anthropic_messages(bogus)


def test_demo_calculator_is_safe():
    assert calculator(CalculatorInput(expression="2 * (3 + 4) / 5")) == "2.8"
    with pytest.raises(ValueError):
        calculator(CalculatorInput(expression="__import__('os').system('id')"))
    assert DEMO_AGENT.tool("calculator") is not None
