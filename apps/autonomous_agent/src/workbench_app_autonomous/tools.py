"""Real "coworker" toolset for the Autonomous Agent: live web, SQL, file workspace.

Three capability groups, all wrapped as runtime ``Tool``s (pydantic input model +
handler, async where the underlying call is async):

* web — ``web_search`` / ``fetch_url`` over the deep-research live web connectors.
* SQL — ``run_sql`` reuses text2sql's read-only guards (``execute_sql`` + the
  ``safe_sql`` allowlist/LIMIT enforcement) over the same sample BI database.
* file workspace — ``write_file`` / ``read_file`` / ``list_files`` into a single
  SANDBOXED directory.

Safety boundary: there is deliberately NO shell/exec/eval tool. The agent can only
touch the filesystem through the sandbox, whose root is fixed (``WB_AGENT_WORKSPACE``
or ``data/agent_workspace``) and whose ``_safe_path`` rejects absolute paths and any
``..`` traversal that would escape the root. SQL is read-only (SELECT only, writes
and DDL rejected by the guard). Web access degrades to empty results on failure.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import Engine
from workbench_capabilities import (
    MAX_ROWS,
    SqlGuardError,
    execute_sql,
    get_engine,
    reflect_tables,
    schema_description,
    web,
)

from workbench_runtime.tools import Tool
from workbench_shared.netguard import UnsafeUrlError, assert_public_url

_MAX_SEARCH_RESULTS = 5
_MAX_FILE_BYTES = 100_000
_TOOL_ROWS_SHOWN = 50


# --- web tools (deep-research live connectors) ---


class WebSearchInput(BaseModel):
    query: str = Field(description="Web search query.")


def _web_search(inp: WebSearchInput) -> str:
    hits = web.web_search({"query": inp.query, "max_results": _MAX_SEARCH_RESULTS})
    out = [
        {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("snippet", "")}
        for h in hits[:_MAX_SEARCH_RESULTS]
    ]
    return json.dumps(out, ensure_ascii=False)


class FetchUrlInput(BaseModel):
    url: str = Field(description="Absolute http(s) URL to fetch.")


def _fetch_url(inp: FetchUrlInput) -> str:
    try:
        assert_public_url(inp.url)
    except UnsafeUrlError as exc:
        # SSRF guard: refuse private/loopback/metadata targets and non-http(s)
        # schemes. Return the message so the agent self-corrects instead of crashing.
        return f"rejected: {exc}"
    result = web.fetch({"url": inp.url})
    text = result.get("text", "")
    if not text:
        return f"(no readable text fetched from {inp.url})"
    return text


# --- SQL tool (read-only, reuses text2sql guards) ---


def _dialect(engine: Engine) -> str:
    return "sqlite" if engine.dialect.name == "sqlite" else engine.dialect.name


class RunSqlInput(BaseModel):
    sql: str = Field(description="One read-only SELECT statement (CTEs allowed).")


def _make_run_sql_tool(engine: Engine, allowed_tables: set[str]) -> Tool:
    dialect = _dialect(engine)

    async def run_sql(inp: RunSqlInput) -> str:
        try:
            sql, columns, rows = await execute_sql(engine, inp.sql, allowed_tables, dialect=dialect)
        except SqlGuardError as exc:
            # Return the guard message as the tool result so the agent self-corrects.
            return f"SQL rejected: {exc}"
        return json.dumps(
            {
                "sql": sql,
                "columns": columns,
                "rows": rows[:_TOOL_ROWS_SHOWN],
                "row_count": len(rows),
                "truncated": len(rows) > _TOOL_ROWS_SHOWN,
            },
            ensure_ascii=False,
            default=str,
        )

    return Tool(
        name="run_sql",
        description=(
            "Execute ONE read-only SELECT against the sales/BI database and get "
            f"columns/rows as JSON (max {MAX_ROWS} rows; writes and DDL are rejected). "
            "Use it whenever the answer needs real data.\n\nSchema:\n" + schema_description(engine)
        ),
        input_model=RunSqlInput,
        handler=run_sql,
    )


# --- file workspace (sandbox) ---


def _workspace_root() -> Path:
    root = Path(os.getenv("WB_AGENT_WORKSPACE", "data/agent_workspace")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path(name: str) -> Path:
    """Resolve ``name`` inside the workspace, rejecting any escape.

    Raises ValueError on absolute paths or ``..`` traversal that resolves outside
    the workspace root.
    """
    if not name or not name.strip():
        raise ValueError("filename is required")
    candidate = Path(name)
    if candidate.is_absolute():
        raise ValueError(f"absolute paths are not allowed: {name}")
    root = _workspace_root()
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path escapes the workspace sandbox: {name}")
    # Defense in depth against symlink escape: even if a symlink was planted in
    # the workspace (by an operator, a bind-mount, or CI), the *real* path must
    # still live under the *real* root, and we refuse to follow a final symlink.
    real_root = os.path.realpath(root)
    real_target = os.path.realpath(resolved)
    if real_target != real_root and not real_target.startswith(real_root + os.sep):
        raise ValueError(f"path escapes the workspace sandbox (symlink): {name}")
    if resolved.is_symlink() or os.path.islink(resolved):
        raise ValueError(f"symlinks are not allowed in the workspace: {name}")
    return resolved


class WriteFileInput(BaseModel):
    filename: str = Field(description="Relative path inside the workspace, e.g. 'report.md'.")
    content: str = Field(description="Text content to write.")


def _write_file(inp: WriteFileInput) -> str:
    if len(inp.content.encode("utf-8")) > _MAX_FILE_BYTES:
        return f"content too large (max {_MAX_FILE_BYTES} bytes)"
    try:
        path = _safe_path(inp.filename)
    except ValueError as exc:
        return f"rejected: {exc}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(inp.content, encoding="utf-8")
    rel = path.relative_to(_workspace_root())
    return f"wrote {len(inp.content)} chars to {rel}"


class ReadFileInput(BaseModel):
    filename: str = Field(description="Relative path inside the workspace.")


def _read_file(inp: ReadFileInput) -> str:
    try:
        path = _safe_path(inp.filename)
    except ValueError as exc:
        return f"rejected: {exc}"
    if not path.is_file():
        return f"file not found: {inp.filename}"
    return path.read_text(encoding="utf-8")


class ListFilesInput(BaseModel):
    pass


def _list_files(_: ListFilesInput) -> str:
    root = _workspace_root()
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    return json.dumps(files, ensure_ascii=False) if files else "(workspace is empty)"


# --- public builder ---


@lru_cache
def _sql_tool() -> Tool:
    engine = get_engine()
    return _make_run_sql_tool(engine, reflect_tables(engine))


def build_tools() -> list[Tool]:
    """The real coworker toolset: web research, read-only SQL, file workspace."""
    return [
        Tool(
            name="web_search",
            description="Search the live web. Returns a JSON list of "
            f"[{{title, url, snippet}}] (up to {_MAX_SEARCH_RESULTS}). "
            "Call this first to find sources.",
            input_model=WebSearchInput,
            handler=_web_search,
        ),
        Tool(
            name="fetch_url",
            description="Fetch the readable text of a web page by URL (capped). "
            "Use after web_search to read a source.",
            input_model=FetchUrlInput,
            handler=_fetch_url,
        ),
        _sql_tool(),
        Tool(
            name="write_file",
            description="Save text into the sandboxed file workspace. Use it to "
            "persist substantial deliverables (reports, CSVs, notes).",
            input_model=WriteFileInput,
            handler=_write_file,
        ),
        Tool(
            name="read_file",
            description="Read a text file back from the sandboxed workspace.",
            input_model=ReadFileInput,
            handler=_read_file,
        ),
        Tool(
            name="list_files",
            description="List the files currently in the sandboxed workspace.",
            input_model=ListFilesInput,
            handler=_list_files,
        ),
    ]
