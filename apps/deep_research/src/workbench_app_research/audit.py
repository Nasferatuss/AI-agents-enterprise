"""Bridge the Tool Gateway's synchronous ``audit_sink`` to the observability
trace store's asynchronous ``record_tool_audit`` (durable governance log, ADR-005).

The gateway calls ``audit_sink(entry)`` synchronously for *every* allowed and denied
tool call, but the persistence helper (`record_tool_audit`) is a coroutine. Tool
calls happen inside an async request handler, so there is already a running event
loop: we schedule the write fire-and-forget via ``asyncio.ensure_future`` and return
immediately — the sink never blocks the tool call and never raises (audit is
telemetry / governance, not the critical path, same principle as ``safe_record``).

If there is no running loop (e.g. a unit test calling the gateway synchronously
outside ``asyncio.run``), we silently skip — we never call ``asyncio.run`` from a
sink, which could deadlock or run a second loop. The whole thing is wrapped in a
broad ``try/except`` so a telemetry failure can never surface into the request.

The adapter lives in the app layer (not in toolgateway) so toolgateway keeps no
dependency on observability — the gateway only knows about the opaque sink callback.
"""

import asyncio

from workbench_observability import record_tool_audit
from workbench_shared.logging import get_logger
from workbench_toolgateway import AuditEntry, ToolGateway

log = get_logger(__name__)


def _audit_sink(entry: AuditEntry) -> None:
    """Synchronous sink: schedule the async durable write, best-effort.

    Never blocks, never raises — a failure here must not break the tool call.
    """
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop (e.g. a synchronous unit test). We cannot safely
            # start one from inside a sink, so drop the entry — the in-memory audit
            # list on the gateway still holds it for the request's lifetime.
            return
        # Fire-and-forget: the coroutine itself is best-effort (safe_record swallows
        # store outages), so a pending task that never settles is harmless.
        loop.create_task(record_tool_audit(entry.model_dump()))
    except Exception as exc:  # noqa: BLE001 — audit persistence must never break a call
        log.warning(
            "audit sink scheduling failed", tool=getattr(entry, "tool", "?"), error=str(exc)
        )


def attach_audit_sink(gateway: ToolGateway) -> ToolGateway:
    """Wire the durable audit sink onto a gateway and return it (for chaining).

    Idempotent and safe to call on any gateway, including ones built elsewhere
    (e.g. ``build_live_gateway``). Behaviour degrades silently when no trace store
    is configured: ``record_tool_audit`` -> ``safe_record`` swallows DB outages.
    """
    gateway.audit_sink = _audit_sink
    return gateway
