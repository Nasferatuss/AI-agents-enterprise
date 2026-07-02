"""Deep Research Agent endpoints (mounted by the gateway)."""

import shlex
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from workbench_app_research.audit import attach_audit_sink
from workbench_app_research.research import ResearchReport, run_research
from workbench_capabilities.web import build_live_gateway
from workbench_observability import safe_record
from workbench_runtime import get_router
from workbench_runtime.router import NoProviderAvailableError
from workbench_shared.config import get_settings
from workbench_toolgateway import ToolGateway, ToolSpec, build_default_gateway
from workbench_toolgateway.mcp_client import mcp_session, register_mcp_tools

router = APIRouter(prefix="/v1/apps/research", tags=["deep-research"])


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.get("/tools", response_model=list[ToolSpec])
async def tools() -> list[ToolSpec]:
    """The tools the gateway exposes (registry view)."""
    return build_default_gateway().list_tools()


@router.get("/mcp/tools", response_model=list[ToolSpec])
async def mcp_tools() -> list[ToolSpec]:
    """Live tool list sourced from the configured MCP server.

    When ``WB_MCP_SERVER_COMMAND`` is set, connect over stdio and return the
    server's advertised tools. When unset, returns ``[]`` (no MCP server wired).
    """
    command = get_settings().mcp_server_command.strip()
    if not command:
        return []
    cmd, *args = shlex.split(command)
    gateway = ToolGateway()
    async with mcp_session(cmd, args) as session:
        await register_mcp_tools(gateway, session)
        return gateway.list_tools()


@router.post("", response_model=ResearchReport)
async def research(req: ResearchRequest) -> ResearchReport:
    started = time.monotonic()
    command = get_settings().mcp_server_command.strip()
    try:
        if command:
            # Source tools from a real MCP server over stdio (opt-in).
            cmd, *args = shlex.split(command)
            # Fresh per request → clean in-memory audit; sink persists it durably.
            gateway = attach_audit_sink(ToolGateway())
            async with mcp_session(cmd, args) as session:
                names = await register_mcp_tools(gateway, session)
                report = await run_research(
                    get_router(), gateway, req.question, allowlist=set(names)
                )
        elif get_settings().research_live_web:
            # Real web research: web_search via DuckDuckGo, fetch downloads URLs.
            # Same ToolSpec names as the corpus, so run_research is unchanged; a
            # network failure degrades to empty results (see web.py). The report
            # stage gets each body straight from its fetch result (no side channel).
            # Fresh per request → clean in-memory audit; sink persists it durably.
            gateway = attach_audit_sink(build_live_gateway())
            report = await run_research(get_router(), gateway, req.question)
        else:
            # Fresh per request → clean in-memory audit; sink persists it durably.
            gateway = attach_audit_sink(build_default_gateway())
            report = await run_research(get_router(), gateway, req.question)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await safe_record(
        kind="agent",
        name="deep_research",
        status="completed",
        latency_ms=int((time.monotonic() - started) * 1000),
        cost_usd=report.cost_usd,
        num_steps=len(report.tool_calls),
        payload=report.model_dump(),
    )
    return report
