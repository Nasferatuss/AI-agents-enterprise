"""The Tool Gateway — a single, governed entry point for all tool calls (ADR-005).

Security boundary is built into the gateway, not bolted on:
- **registry**: tools are registered typed handlers (no arbitrary shell — there is
  no generic "run command" tool to register against);
- **permission allowlist**: each call is checked against a per-caller allowlist;
  a denied tool is never executed;
- **audit log**: every call (allowed or denied, with args, latency, error) is
  recorded — the governance artifact and the deep-research "trace".

The in-memory `audit` list lives only as long as the gateway instance, which apps
recreate per request — so by itself it is ephemeral. To make audit durable, pass an
`audit_sink` callback: it is invoked for *every* allowed and denied call and can
forward the entry into a persistent store (e.g. the observability trace store via a
small helper there). The gateway never imports observability directly — that would
create a toolgateway→observability dependency cycle — the sink is wired by the outer
app/gateway layer instead.
"""

import datetime
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from workbench_shared.logging import get_logger
from workbench_toolgateway.types import AuditEntry, ToolResult, ToolSpec

log = get_logger(__name__)

# A connector is a typed function over JSON-able args returning a JSON-able result.
Connector = Callable[[dict], object | Awaitable[object]]


@dataclass
class _Registered:
    spec: ToolSpec
    handler: Connector


@dataclass
class ToolGateway:
    _tools: dict[str, _Registered] = field(default_factory=dict)
    audit: list[AuditEntry] = field(default_factory=list)
    # Optional durable sink: called with every audit entry (allowed and denied) so an
    # outer layer can persist governance audit beyond this short-lived instance. Kept
    # separate from the in-memory `audit` list, which stays for tests / back-compat.
    audit_sink: Callable[[AuditEntry], None] | None = None

    def register(self, spec: ToolSpec, handler: Connector) -> None:
        self._tools[spec.name] = _Registered(spec=spec, handler=handler)

    def list_tools(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def _record(self, tool: str, args: dict, allowed: bool, error: str | None, ms: int) -> None:
        entry = AuditEntry(
            tool=tool,
            args=args,
            allowed=allowed,
            error=error,
            latency_ms=ms,
            at=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        )
        self.audit.append(entry)
        if self.audit_sink is not None:
            # The sink persists audit durably; a sink failure must never break the tool
            # call (audit is telemetry / governance, not the critical path).
            try:
                self.audit_sink(entry)
            except Exception as exc:  # noqa: BLE001 — audit persistence is best-effort
                log.warning("audit_sink failed", tool=tool, error=str(exc))

    async def call(self, tool: str, args: dict, *, allowlist: set[str] | None = None) -> ToolResult:
        started = time.monotonic()

        if tool not in self._tools:
            self._record(tool, args, allowed=False, error="unknown tool", ms=0)
            return ToolResult(tool=tool, allowed=False, error="unknown tool")

        if allowlist is not None and tool not in allowlist:
            self._record(tool, args, allowed=False, error="tool not permitted", ms=0)
            log.warning("tool call denied by allowlist", tool=tool)
            return ToolResult(tool=tool, allowed=False, error="tool not permitted")

        try:
            result = self._tools[tool].handler(args)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # noqa: BLE001 — tool failures are returned, not raised
            ms = int((time.monotonic() - started) * 1000)
            self._record(tool, args, allowed=True, error=str(exc), ms=ms)
            return ToolResult(tool=tool, allowed=True, error=str(exc), latency_ms=ms)

        ms = int((time.monotonic() - started) * 1000)
        self._record(tool, args, allowed=True, error=None, ms=ms)
        return ToolResult(tool=tool, allowed=True, output=result, latency_ms=ms)
