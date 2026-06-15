"""Real web connectors for the deep-research pipeline: live web_search + fetch.

Opt-in (``WB_RESEARCH_LIVE_WEB=true``) alternative to the in-process corpus
connectors. ``web_search`` discovers sources via DuckDuckGo; ``fetch`` downloads
a URL and extracts readable text. Both keep the exact output shapes of the
corpus connectors so ``research.py`` is unchanged, and both degrade gracefully:
a network/parse failure yields empty results rather than killing the run.

Fetched bodies are cached by URL (``BODY_CACHE``) so the report stage can cite
the real text it already retrieved without a second network round-trip.
"""

import re

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

from workbench_shared.logging import get_logger
from workbench_toolgateway import ToolGateway, ToolSpec

log = get_logger(__name__)

# url -> {"title", "text"} for bodies fetched this process; read by research.py's
# report step (the live analogue of the corpus lookup).
BODY_CACHE: dict[str, dict[str, str]] = {}

_MAX_TEXT = 8000
_TIMEOUT = 10.0
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_WS = re.compile(r"\s+")


def web_search(args: dict) -> list[dict]:
    """Live DuckDuckGo search. Returns [{title, url, snippet}] (corpus shape)."""
    query = str(args.get("query", "")).strip()
    if not query:
        return []
    max_results = int(args.get("max_results", 5))
    try:
        with DDGS() as ddgs:
            hits = ddgs.text(query, max_results=max_results)
    except Exception as exc:  # noqa: BLE001 — a failed search must not kill the run
        log.warning("live web_search failed", query=query, error=str(exc))
        return []
    out: list[dict] = []
    for h in hits or []:
        url = h.get("href") or h.get("url") or ""
        if not url:
            continue
        out.append(
            {
                "title": h.get("title", ""),
                "url": url,
                "snippet": h.get("body", h.get("snippet", "")),
            }
        )
    return out


def _extract(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    text = _WS.sub(" ", soup.get_text(" ")).strip()[:_MAX_TEXT]
    return title, text


def fetch(args: dict) -> dict:
    """Live fetch: download `url`, extract readable text. Returns {url, title, text}.

    On failure returns the url with empty text rather than raising, so one bad
    URL doesn't abort the research loop. Successful bodies are cached by URL.
    """
    url = str(args.get("url", "")).strip()
    if not url:
        return {"url": url, "title": "", "text": ""}
    try:
        resp = httpx.get(
            url,
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        title, text = _extract(resp.text)
    except Exception as exc:  # noqa: BLE001 — surface a usable result, not a crash
        log.warning("live fetch failed", url=url, error=str(exc))
        return {"url": url, "title": "", "text": ""}
    result = {"url": url, "title": title or url, "text": text}
    BODY_CACHE[url] = {"title": result["title"], "text": text}
    return result


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
}


def build_live_gateway() -> ToolGateway:
    """A gateway whose web_search/fetch hit the real internet (corpus shape kept)."""
    gw = ToolGateway()
    for name, (handler, desc, schema) in _SPECS.items():
        gw.register(ToolSpec(name=name, description=desc, input_schema=schema), handler)
    return gw
