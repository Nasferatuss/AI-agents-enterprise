"""A real, runnable MCP server that re-exposes the corpus connectors over MCP.

The project ships BOTH sides of the protocol: this FastMCP server advertises the
same three tools the in-process connectors provide (`web_search`, `fetch`,
`kb_search`), delegating to them directly. Launch it over stdio with:

    python -m workbench_toolgateway.mcp_server

so the deep-research agent (via `mcp_client`) can drive the exact same pipeline
over a real MCP transport.
"""

from mcp.server.fastmcp import FastMCP

from workbench_toolgateway import connectors

mcp = FastMCP("workbench-corpus")


@mcp.tool()
def web_search(query: str) -> list[dict]:
    """Search the corpus for sources. Returns [{title, url, snippet}]."""
    return connectors.web_search({"query": query})


@mcp.tool()
def fetch(url: str) -> dict:
    """Fetch the full text of a source by its url. Returns {url, title, text}."""
    return connectors.fetch({"url": url})


@mcp.tool()
def kb_search(query: str) -> list[dict]:
    """Search the internal knowledge base for passages. Returns [{source, text}]."""
    return connectors.kb_search({"query": query})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
