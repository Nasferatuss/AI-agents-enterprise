import json

import httpx
import pytest
from workbench_app_autonomous.agent import _parse_reflection, run_autonomous

from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter


@pytest.mark.parametrize("text", ["not json at all", "", "{}", '{"missing": "x"}'])
def test_parse_reflection_broken_json_does_not_complete(text):
    # A reflection we can't parse must NOT be read as success — that would let a
    # broken model response declare the goal met and stop the loop prematurely.
    assert _parse_reflection(text).goal_met is False


def _router() -> ModelRouter:
    """Stub: PLAN → JSON plan, REFLECT → goal_met true (terminates loop),
    ACT → one calculator tool call then a final answer."""
    act_turns = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator",
                                        "arguments": json.dumps({"expression": "2 + 2"}),
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
            {
                "choices": [{"message": {"role": "assistant", "content": "The answer is 4."}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 7},
            },
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = next((m["content"] for m in body["messages"] if m["role"] == "system"), "")
        if "autonomous planner" in system:
            text = json.dumps({"steps": ["compute 2 + 2", "report the result"]})
        elif "progress judge" in system:
            text = json.dumps({"goal_met": True, "missing": "", "next_focus": ""})
        else:
            # ACT turn — return the next scripted tool/text response verbatim.
            return httpx.Response(200, json=next(act_turns))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            },
        )

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


async def test_autonomous_loop_plans_acts_reflects_and_completes():
    result = await run_autonomous(_router(), "What is 2 + 2?")

    assert result.completed is True
    assert result.goal == "What is 2 + 2?"
    # at least one iteration, each with a plan + reflection
    assert len(result.iterations) >= 1
    first = result.iterations[0]
    assert first.plan.steps == ["compute 2 + 2", "report the result"]
    assert first.reflection.goal_met is True
    # the acting loop produced a final answer and recorded memory
    assert result.final_answer == "The answer is 4."
    assert any("The answer is 4." in m for m in result.memory)
    # loop terminated on first reflection (goal_met) — exactly one iteration
    assert len(result.iterations) == 1
