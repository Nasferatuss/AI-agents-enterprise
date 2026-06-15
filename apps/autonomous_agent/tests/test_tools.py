"""Network-free tests for the real coworker toolset (web/SQL/file sandbox)."""

import json

import pytest
from workbench_app_autonomous import tools
from workbench_app_autonomous.tools import (
    FetchUrlInput,
    ListFilesInput,
    ReadFileInput,
    RunSqlInput,
    WebSearchInput,
    WriteFileInput,
    _list_files,
    _make_run_sql_tool,
    _read_file,
    _safe_path,
    _write_file,
)

from workbench_app_text2sql.agent import get_engine
from workbench_app_text2sql.schema import reflect_tables

# --- file sandbox ---


def test_file_sandbox_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_AGENT_WORKSPACE", str(tmp_path / "ws"))
    assert "wrote" in _write_file(WriteFileInput(filename="report.md", content="hello"))
    assert _read_file(ReadFileInput(filename="report.md")) == "hello"
    listed = json.loads(_list_files(ListFilesInput()))
    assert "report.md" in listed


def test_read_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_AGENT_WORKSPACE", str(tmp_path / "ws"))
    assert "not found" in _read_file(ReadFileInput(filename="nope.txt"))


def test_safe_path_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_AGENT_WORKSPACE", str(tmp_path / "ws"))
    with pytest.raises(ValueError):
        _safe_path("../escape.txt")
    with pytest.raises(ValueError):
        _safe_path("a/b/../../../escape.txt")


def test_safe_path_rejects_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_AGENT_WORKSPACE", str(tmp_path / "ws"))
    with pytest.raises(ValueError):
        _safe_path("/etc/passwd")


def test_write_file_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_AGENT_WORKSPACE", str(tmp_path / "ws"))
    out = _write_file(WriteFileInput(filename="../escape.txt", content="x"))
    assert out.startswith("rejected:")


# --- run_sql (text2sql engine, network-free) ---


def _sql_tool():
    engine = get_engine()
    return _make_run_sql_tool(engine, reflect_tables(engine))


async def test_run_sql_valid_select():
    tool = _sql_tool()
    out = await tool.handler(RunSqlInput(sql="SELECT * FROM customers"))
    data = json.loads(out)
    assert data["columns"]
    assert data["row_count"] >= 1


async def test_run_sql_rejects_write():
    tool = _sql_tool()
    out = await tool.handler(RunSqlInput(sql="DROP TABLE customers"))
    assert out.startswith("SQL rejected:")  # guard message, not a crash


# --- web tools (monkeypatched, no network) ---


def test_web_search_shape(monkeypatch):
    monkeypatch.setattr(
        tools.web,
        "web_search",
        lambda args: [
            {"title": "T", "url": "http://x", "snippet": "S"},
            {"title": "T2", "url": "http://y", "snippet": "S2"},
        ],
    )
    out = tools._web_search(WebSearchInput(query="anything"))
    data = json.loads(out)
    assert data[0] == {"title": "T", "url": "http://x", "snippet": "S"}


def test_fetch_url_returns_text(monkeypatch):
    monkeypatch.setattr(
        tools.web, "fetch", lambda args: {"url": args["url"], "title": "t", "text": "body text"}
    )
    assert tools._fetch_url(FetchUrlInput(url="http://x")) == "body text"


def test_fetch_url_empty(monkeypatch):
    monkeypatch.setattr(
        tools.web, "fetch", lambda args: {"url": args["url"], "title": "", "text": ""}
    )
    assert "no readable text" in tools._fetch_url(FetchUrlInput(url="http://x"))
