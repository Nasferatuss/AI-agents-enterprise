"""A real Model Context Protocol (MCP) stdio client for the Tool Gateway.

This lets the gateway source its tools from a live MCP server over stdio instead
of only the in-process corpus connectors. Tools advertised by the server are
registered onto a `ToolGateway` as async handlers that proxy `call_tool` over the
session, so the same governance boundary (allowlist + audit log) still applies.

Uses the official Python SDK (`mcp`). The bundled `mcp_server` module re-exposes
the corpus connectors over MCP, so the deep-research pipeline runs unchanged.
"""

import asyncio
import gc
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from workbench_shared.logging import get_logger
from workbench_toolgateway.gateway import ToolGateway
from workbench_toolgateway.types import ToolSpec

log = get_logger(__name__)


@asynccontextmanager
async def mcp_session(command: str, args: list[str]) -> AsyncIterator[ClientSession]:
    """Open an MCP stdio session against `command args`, yield an initialized session."""
    params = StdioServerParameters(command=command, args=args)
    try:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            log.info("mcp session initialized", command=command, args=args)
            yield session
    finally:
        # The stdio server runs as a subprocess. Once the context managers above
        # exit the process is terminated, but its asyncio transport is otherwise
        # finalized by GC — which, if that happens after the event loop closes,
        # prints a spurious "Event loop is closed" from the transport's __del__
        # (seen on Linux/CI). Yield a tick so anyio's pending close callbacks run,
        # then finalize the now-unreachable transport while the loop is still live.
        await asyncio.sleep(0)
        gc.collect()


def _extract_result(result: object) -> object:
    """Extract a plain Python value from a `CallToolResult`.

    Prefers `structuredContent` (FastMCP wraps a non-dict return as
    ``{"result": ...}``, so a lone ``result`` key is unwrapped). Falls back to
    parsing the concatenated text content as JSON, otherwise returns the raw text.
    """
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured

    content = getattr(result, "content", None) or []
    texts = [c.text for c in content if getattr(c, "type", None) == "text"]
    if texts:
        joined = "".join(texts)
        try:
            return json.loads(joined)
        except (json.JSONDecodeError, ValueError):
            return joined
    return None


async def register_mcp_tools(gateway: ToolGateway, session: ClientSession) -> list[str]:
    """Register every tool advertised by the MCP server onto the gateway.

    Returns the list of registered tool names (use it as the gateway allowlist).
    """
    listed = await session.list_tools()
    names: list[str] = []
    for tool in listed.tools:

        def make_handler(tool_name: str):
            async def handler(args: dict) -> object:
                result = await session.call_tool(tool_name, args)
                return _extract_result(result)

            return handler

        gateway.register(
            ToolSpec(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
            ),
            make_handler(tool.name),
        )
        names.append(tool.name)

    log.info("registered mcp tools", tools=names)
    return names
