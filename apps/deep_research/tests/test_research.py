import json

import httpx

from workbench_app_research.research import run_research
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter
from workbench_toolgateway import build_default_gateway


def _router(plan_subqs: list[str], report_text: str) -> ModelRouter:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = next(m["content"] for m in body["messages"] if m["role"] == "system")
        if "research planner" in system:
            text = json.dumps({"sub_questions": plan_subqs})
        else:
            text = report_text
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


async def test_research_gathers_sources_and_cites():
    gw = build_default_gateway()
    router = _router(
        ["what is retrieval augmented generation", "how are agents observed"],
        "RAG grounds a model in documents [1]. Observability traces every run [2].",
    )
    report = await run_research(router, gw, "How do you build reliable AI agents?")

    # gathered real sources through the gateway
    assert len(report.sources) >= 2
    assert all(s.url.startswith("https://docs.local/") for s in report.sources)
    # the gateway audit log is the tool trace — shows web_search + fetch calls
    tools_used = {a.tool for a in report.tool_calls}
    assert "web_search" in tools_used and "fetch" in tools_used
    assert all(a.allowed for a in report.tool_calls)
    # the report text came back
    assert "[1]" in report.report
    assert report.sub_questions == [
        "what is retrieval augmented generation",
        "how are agents observed",
    ]


async def test_research_falls_back_to_question_when_plan_unparseable():
    gw = build_default_gateway()
    router = _router([], "report")  # empty sub_questions → fallback to the question
    report = await run_research(router, gw, "what is evaluation of LLM systems")
    assert report.sub_questions == ["what is evaluation of LLM systems"]
    assert len(report.sources) >= 1  # still researched the question itself
