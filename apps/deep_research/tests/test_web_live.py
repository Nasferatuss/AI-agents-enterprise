"""Network-free tests for the live web connectors + pipeline wiring.

The real DDGS/httpx calls are monkeypatched with fakes returning canned,
real-looking results — the suite never hits the internet. Mirrors the router
stub from test_research.py.
"""

import json

import httpx
from workbench_capabilities import web
from workbench_capabilities.web import build_live_gateway

from workbench_app_research.research import run_research
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter

_FAKE_HITS = {
    "https://example.com/rag": {
        "title": "Retrieval-Augmented Generation — Example",
        "text": "RAG grounds a language model in retrieved documents from a vector store.",
    },
    "https://example.org/agents": {
        "title": "Building Agents — Example",
        "text": "An agent is a model in a loop with tools behind a governed gateway.",
    },
}


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


def _patch_live(monkeypatch):
    """Replace DDGS/httpx so web.web_search/web.fetch return canned real-looking data."""

    class _FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def text(self, query, max_results=5):
            return [
                {"title": d["title"], "href": url, "body": d["text"][:80]}
                for url, d in _FAKE_HITS.items()
            ][:max_results]

    def _fake_get(url, **kwargs):
        d = _FAKE_HITS[url]
        html = (
            f"<html><head><title>{d['title']}</title></head><body><p>{d['text']}</p></body></html>"
        )
        return httpx.Response(200, text=html, request=httpx.Request("GET", url))

    monkeypatch.setattr(web, "DDGS", _FakeDDGS)
    monkeypatch.setattr(web, "safe_get", _fake_get)
    web.BODY_CACHE.clear()


def test_live_web_search_and_fetch_shapes(monkeypatch):
    _patch_live(monkeypatch)
    hits = web.web_search({"query": "retrieval augmented generation"})
    assert hits and set(hits[0]) == {"title", "url", "snippet"}
    assert hits[0]["url"].startswith("https://example.")

    fetched = web.fetch({"url": hits[0]["url"]})
    assert set(fetched) == {"url", "title", "text"}
    assert "vector store" in fetched["text"] or "tools" in fetched["text"]
    # body cached for the report stage
    assert web.BODY_CACHE[hits[0]["url"]]["text"]


def test_live_fetch_bad_url_returns_empty(monkeypatch):
    def _boom(url, **kwargs):
        raise httpx.ConnectError("no network", request=httpx.Request("GET", url))

    monkeypatch.setattr(web, "safe_get", _boom)
    out = web.fetch({"url": "https://93.184.216.34/x"})
    assert out == {"url": "https://93.184.216.34/x", "title": "", "text": ""}


def test_live_fetch_rejects_metadata_and_localhost():
    # Real safe_get guards SSRF: metadata IP (literal, no DNS) and loopback host.
    web.BODY_CACHE.clear()
    for bad in ("http://169.254.169.254/latest/meta-data/", "http://localhost:8000/admin"):
        out = web.fetch({"url": bad})
        assert out == {"url": bad, "title": "", "text": ""}
        assert bad not in web.BODY_CACHE


def test_body_cache_bounded():
    from workbench_capabilities.web import _BODY_CACHE_MAX

    web.BODY_CACHE.clear()
    for i in range(_BODY_CACHE_MAX + 50):
        web.BODY_CACHE[f"https://example.com/{i}"] = {"title": "t", "text": "x"}
    assert len(web.BODY_CACHE) == _BODY_CACHE_MAX
    assert "https://example.com/0" not in web.BODY_CACHE  # oldest evicted
    assert f"https://example.com/{_BODY_CACHE_MAX + 49}" in web.BODY_CACHE  # newest kept


async def test_pipeline_cites_real_urls_with_live_connectors(monkeypatch):
    _patch_live(monkeypatch)
    gw = build_live_gateway()
    router = _router(
        ["what is rag", "how are agents built"],
        "RAG grounds a model in documents [1]. Agents loop with tools [2].",
    )
    report = await run_research(router, gw, "How do you build reliable AI agents?")

    # cites the live (fake) real URLs, not the corpus
    assert len(report.sources) >= 2
    assert all(s.url.startswith("https://example.") for s in report.sources)
    assert not any(s.url.startswith("https://docs.local/") for s in report.sources)

    # the live tool path was used and recorded in the audit trace
    tools_used = {a.tool for a in report.tool_calls}
    assert "web_search" in tools_used and "fetch" in tools_used
    assert all(a.allowed for a in report.tool_calls)
    assert "[1]" in report.report

    # the report's numbered sources carried real fetched text (via BODY_CACHE)
    from workbench_app_research.research import _source_text

    for s in report.sources:
        assert _source_text(gw, s.url).strip()
