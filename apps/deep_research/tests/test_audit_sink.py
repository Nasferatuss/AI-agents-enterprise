"""The governance audit sink: a DENIED tool call through a gateway with the sink
attached schedules a durable ``record_tool_audit`` write — best-effort, async,
network-free (the persistence helper itself is mocked, no real trace store)."""

import asyncio

from workbench_app_research.audit import attach_audit_sink
from workbench_toolgateway import ToolGateway, ToolSpec


def _gateway_with_one_tool() -> ToolGateway:
    gw = attach_audit_sink(ToolGateway())
    gw.register(
        ToolSpec(name="web_search", description="search", input_schema={}),
        lambda args: [],
    )
    return gw


async def test_denied_call_schedules_audit_record(monkeypatch):
    """A tool blocked by the allowlist persists an audit entry with allowed=False."""
    recorded: list[dict] = []

    async def fake_record_tool_audit(entry: dict) -> str | None:
        recorded.append(entry)
        return "trace-id"

    # Patch where the sink looks it up (imported into the audit module's namespace).
    monkeypatch.setattr(
        "workbench_app_research.audit.record_tool_audit", fake_record_tool_audit
    )

    gw = _gateway_with_one_tool()
    # `secret_tool` is registered but NOT on the allowlist → denied by policy,
    # never executed (distinct from an unknown-tool denial).
    gw.register(
        ToolSpec(name="secret_tool", description="danger", input_schema={}),
        lambda args: "should not run",
    )
    result = await gw.call("secret_tool", {"q": "x"}, allowlist={"web_search"})
    assert result.allowed is False

    # The sink schedules the write fire-and-forget; let the pending task run.
    await asyncio.sleep(0)

    assert len(recorded) == 1
    entry = recorded[0]
    assert entry["tool"] == "secret_tool"
    assert entry["allowed"] is False
    assert entry["error"] == "tool not permitted"
    assert entry["args"] == {"q": "x"}


async def test_allowed_call_also_audited(monkeypatch):
    """Allowed calls are persisted too (the full governance trace, not only denials)."""
    recorded: list[dict] = []

    async def fake_record_tool_audit(entry: dict) -> str | None:
        recorded.append(entry)
        return None

    monkeypatch.setattr(
        "workbench_app_research.audit.record_tool_audit", fake_record_tool_audit
    )

    gw = _gateway_with_one_tool()
    result = await gw.call("web_search", {"query": "ai"}, allowlist={"web_search"})
    assert result.allowed is True

    await asyncio.sleep(0)

    assert len(recorded) == 1
    assert recorded[0]["tool"] == "web_search"
    assert recorded[0]["allowed"] is True


def test_sink_no_running_loop_is_silent(monkeypatch):
    """Called synchronously (no event loop), the sink drops the entry, never raises."""
    called = False

    async def fake_record_tool_audit(entry: dict) -> str | None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(
        "workbench_app_research.audit.record_tool_audit", fake_record_tool_audit
    )

    from workbench_app_research.audit import _audit_sink
    from workbench_toolgateway import AuditEntry

    # No running loop here → silently skipped, no exception, no scheduling.
    _audit_sink(
        AuditEntry(tool="t", args={}, allowed=False, error="denied", at="2026-01-01T00:00:00")
    )
    assert called is False
