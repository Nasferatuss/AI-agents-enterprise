"""Deterministic, network-free tests for the real MCP client/server pair.

Launches the bundled `mcp_server` over stdio (via `sys.executable -m ...`), so no
external servers are needed and the suite is CI-safe.
"""

import json
import sys

import httpx

from workbench_app_research.research import run_research
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter
from workbench_toolgateway.gateway import ToolGateway
from workbench_toolgateway.mcp_client import mcp_session, register_mcp_tools

_SERVER_ARGS = ["-m", "workbench_toolgateway.mcp_server"]


def _router(plan_subqs: list[str], report_text: str) -> ModelRouter:
    """Mirror of apps/deep_research/tests/test_research.py router stub."""

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


async def test_register_and_call_over_mcp():
    gateway = ToolGateway()
    async with mcp_session(sys.executable, _SERVER_ARGS) as session:
        names = await register_mcp_tools(gateway, session)
        assert set(names) == {"web_search", "fetch", "kb_search"}

        # web_search returns list[dict] matching the in-process connector output.
        search = await gateway.call(
            "web_search", {"query": "retrieval augmented generation"}, allowlist=set(names)
        )
        assert search.allowed and search.error is None
        assert isinstance(search.output, list) and search.output
        hit = search.output[0]
        assert set(hit) == {"title", "url", "snippet"}
        assert hit["url"].startswith("https://docs.local/")

        # fetch returns {url, title, text}.
        fetched = await gateway.call("fetch", {"url": hit["url"]}, allowlist=set(names))
        assert fetched.allowed and fetched.error is None
        assert set(fetched.output) == {"url", "title", "text"}
        assert fetched.output["url"] == hit["url"]

        # kb_search returns list of {source, text}.
        kb = await gateway.call("kb_search", {"query": "agents tools loop"}, allowlist=set(names))
        assert isinstance(kb.output, list) and kb.output
        assert set(kb.output[0]) == {"source", "text"}

        # allowlist denial is honored without executing the tool.
        denied = await gateway.call("web_search", {"query": "x"}, allowlist={"fetch"})
        assert denied.allowed is False and denied.error == "tool not permitted"

        # unknown tool follows the gateway contract.
        unknown = await gateway.call("does_not_exist", {}, allowlist=set(names))
        assert unknown.allowed is False and unknown.error == "unknown tool"

    # audit log recorded every call (allowed + denied + unknown).
    audited = [a.tool for a in gateway.audit]
    assert "web_search" in audited and "fetch" in audited and "kb_search" in audited
    assert "does_not_exist" in audited


async def test_run_research_over_mcp_backed_gateway():
    gateway = ToolGateway()
    async with mcp_session(sys.executable, _SERVER_ARGS) as session:
        names = await register_mcp_tools(gateway, session)
        router = _router(
            ["what is retrieval augmented generation", "how are agents observed"],
            "RAG grounds a model in documents [1]. Observability traces every run [2].",
        )
        report = await run_research(
            router, gateway, "How do you build reliable AI agents?", allowlist=set(names)
        )

    assert len(report.sources) >= 2
    assert all(s.url.startswith("https://docs.local/") for s in report.sources)
    tools_used = {a.tool for a in report.tool_calls}
    assert "web_search" in tools_used and "fetch" in tools_used
    assert "[1]" in report.report
