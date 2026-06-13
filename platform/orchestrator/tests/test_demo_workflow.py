import json

import httpx

from workbench_orchestrator.demo import CONTENT_BRIEF
from workbench_orchestrator.engine import execute
from workbench_runtime import router as router_module
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter


def _text_response(text: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def _install_router(monkeypatch, handler) -> None:
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
    monkeypatch.setattr(router_module, "get_router", lambda: router)
    import workbench_orchestrator.demo as demo_module

    monkeypatch.setattr(demo_module, "get_router", lambda: router)


async def test_content_brief_passes_review_first_try(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        prompt = json.loads(request.content)["messages"][-1]["content"]
        if "Review this executive brief" in prompt:
            return httpx.Response(
                200, json=_text_response('{"score": 0.9, "passed": true, "feedback": "solid"}')
            )
        return httpx.Response(200, json=_text_response("- point one\n- point two"))

    _install_router(monkeypatch, handler)
    run = await execute(CONTENT_BRIEF, {"topic": "AI agents in banking"})

    assert run.status == "completed"
    assert run.state["review_passed"] is True
    assert run.state["brief"].startswith("# Executive brief: AI agents in banking")
    assert [a.step for a in run.attempts] == ["validate", "draft", "review", "finalize"]


async def test_content_brief_revises_once_then_ships(monkeypatch):
    reviews = iter(
        [
            '{"score": 0.3, "passed": false, "feedback": "too shallow"}',
            '{"score": 0.4, "passed": false, "feedback": "still shallow"}',
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        prompt = json.loads(request.content)["messages"][-1]["content"]
        if "Review this executive brief" in prompt:
            return httpx.Response(200, json=_text_response(next(reviews)))
        if "Improve this executive brief" in prompt:
            return httpx.Response(200, json=_text_response("- improved point"))
        return httpx.Response(200, json=_text_response("- weak point"))

    _install_router(monkeypatch, handler)
    run = await execute(CONTENT_BRIEF, {"topic": "supply chain"})

    assert run.status == "completed"
    assert run.state["revisions"] == 1
    assert "max revisions" in run.state["brief"]
    assert [a.step for a in run.attempts] == [
        "validate",
        "draft",
        "review",
        "revise",
        "review",
        "finalize",
    ]


async def test_content_brief_rejects_empty_topic(monkeypatch):
    _install_router(monkeypatch, lambda r: httpx.Response(500))
    run = await execute(CONTENT_BRIEF, {"topic": "   "})

    assert run.status == "failed"
    assert "validate" in run.error
