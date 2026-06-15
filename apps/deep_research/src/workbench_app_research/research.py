"""Deep Research pipeline: plan → research (via Tool Gateway) → cited report.

Control flow is code-driven and predictable (ADR-007): the planner produces
sub-questions, the research stage drives the gateway tools (web_search → fetch)
under an allowlist, and the report stage synthesizes a cited answer that only
uses the gathered sources (the verifier behaviour is folded into its prompt).
The gateway audit log is the tool trace returned with the report.
"""

import json

from pydantic import BaseModel

from workbench_runtime.router import ModelRouter
from workbench_runtime.types import UserMessage
from workbench_toolgateway import AuditEntry, ToolGateway

_ALLOWLIST = {"web_search", "fetch", "kb_search"}
_MAX_SUBQUESTIONS = 3

_PLAN_SYSTEM = (
    "You are a research planner. Break the question into up to 3 focused "
    'sub-questions. Respond with ONLY JSON: {"sub_questions": ["...", "..."]}'
)
_REPORT_SYSTEM = (
    "You are a research analyst. Write a concise report answering the question "
    "using ONLY the numbered sources provided. Cite claims with inline markers "
    "like [1], [2]. If the sources do not support an answer, say so explicitly "
    "rather than inventing facts."
)


class Source(BaseModel):
    n: int
    url: str
    title: str


class ResearchReport(BaseModel):
    question: str
    sub_questions: list[str]
    sources: list[Source]
    report: str
    tool_calls: list[AuditEntry]  # gateway audit = the tool trace (ADR-005)
    provider: str = ""
    model: str = ""
    cost_usd: float | None = None


def _parse_subquestions(text: str, fallback: str) -> list[str]:
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            subs = [str(s) for s in data.get("sub_questions", []) if str(s).strip()]
            if subs:
                return subs[:_MAX_SUBQUESTIONS]
        except json.JSONDecodeError:
            pass
    return [fallback]


def _add_cost(total: float | None, part: float | None) -> float | None:
    return None if (total is None or part is None) else total + part


async def run_research(
    router: ModelRouter,
    gateway: ToolGateway,
    question: str,
    *,
    allowlist: set[str] | None = None,
) -> ResearchReport:
    # `allowlist` lets callers override the tools this run may use (e.g. when the
    # gateway is backed by a live MCP server). Default keeps the built-in set.
    allowlist = allowlist if allowlist is not None else _ALLOWLIST
    cost: float | None = 0.0

    # 1. plan
    plan = await router.step(
        [UserMessage(content=question)],
        complexity="complex",
        system=_PLAN_SYSTEM,
        max_tokens=512,
    )
    cost = _add_cost(cost, plan.cost_usd)
    sub_questions = _parse_subquestions(plan.text, question)

    # 2. research — drive the gateway tools under the allowlist
    sources: list[Source] = []
    seen: set[str] = set()
    for sq in sub_questions:
        search = await gateway.call("web_search", {"query": sq}, allowlist=allowlist)
        for hit in (search.output or [])[:2]:
            url = hit.get("url")
            if not url or url in seen:
                continue
            fetched = await gateway.call("fetch", {"url": url}, allowlist=allowlist)
            if fetched.allowed and not fetched.error and fetched.output:
                seen.add(url)
                sources.append(Source(n=len(sources) + 1, url=url, title=fetched.output["title"]))

    # 3. report (with verification baked into the prompt)
    numbered = "\n\n".join(
        f"[{s.n}] {s.title} ({s.url})\n{_source_text(gateway, s.url)}" for s in sources
    )
    report_out = await router.step(
        [UserMessage(content=f"Question: {question}\n\nSources:\n{numbered}")],
        complexity="complex",
        system=_REPORT_SYSTEM,
        max_tokens=1024,
    )
    cost = _add_cost(cost, report_out.cost_usd)

    return ResearchReport(
        question=question,
        sub_questions=sub_questions,
        sources=sources,
        report=report_out.text,
        tool_calls=gateway.audit,
        provider=report_out.provider,
        model=report_out.model,
        cost_usd=cost,
    )


def _source_text(gateway: ToolGateway, url: str) -> str:
    """Recover the fetched body for `url` for the report stage.

    Live-web runs cache real bodies in ``web.BODY_CACHE`` during the research
    loop (the gateway keeps no payloads); corpus runs fall back to ``CORPUS``.
    """
    from workbench_app_research.web import BODY_CACHE

    if url in BODY_CACHE:
        return BODY_CACHE[url].get("text", "")

    from workbench_toolgateway.corpus import CORPUS

    return CORPUS.get(url, {}).get("text", "")
