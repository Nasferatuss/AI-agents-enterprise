"""Sample MCP-style connectors registered on a gateway: web_search, fetch, kb_search.

All three are typed functions over JSON args — no shell, no eval. They operate
over the bundled research corpus so the deep-research flow is deterministic.
"""

import re

from workbench_toolgateway.corpus import CORPUS
from workbench_toolgateway.gateway import ToolGateway
from workbench_toolgateway.types import ToolSpec

_WORD = re.compile(r"\w+", re.UNICODE)


def _score(query: str, text: str) -> int:
    terms = set(_WORD.findall(query.lower()))
    words = _WORD.findall(text.lower())
    return sum(1 for w in words if w in terms)


def web_search(args: dict) -> list[dict]:
    query = str(args.get("query", ""))
    ranked = sorted(
        CORPUS.items(),
        key=lambda kv: _score(query, kv[1]["title"] + " " + kv[1]["text"]),
        reverse=True,
    )
    top = [(url, d) for url, d in ranked if _score(query, d["title"] + " " + d["text"]) > 0][:3]
    return [{"title": d["title"], "url": url, "snippet": d["text"][:160]} for url, d in top]


def fetch(args: dict) -> dict:
    url = str(args.get("url", ""))
    if url not in CORPUS:
        raise ValueError(f"unknown url: {url}")
    return {"url": url, "title": CORPUS[url]["title"], "text": CORPUS[url]["text"]}


def kb_search(args: dict) -> list[dict]:
    """Passage-level lookup (different surface from web_search's discovery view)."""
    query = str(args.get("query", ""))
    hits = [
        {"source": url, "text": d["text"]}
        for url, d in CORPUS.items()
        if _score(query, d["text"]) > 0
    ]
    return sorted(hits, key=lambda h: _score(query, h["text"]), reverse=True)[:3]


_SPECS = {
    "web_search": (
        web_search,
        "Search the web for sources. Returns [{title, url, snippet}]. Call this first.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
    "fetch": (
        fetch,
        "Fetch the full text of a source by its url. Returns {url, title, text}.",
        {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    ),
    "kb_search": (
        kb_search,
        "Search the internal knowledge base for passages. Returns [{source, text}].",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
}


def build_default_gateway() -> ToolGateway:
    gw = ToolGateway()
    for name, (handler, desc, schema) in _SPECS.items():
        gw.register(ToolSpec(name=name, description=desc, input_schema=schema), handler)
    return gw
