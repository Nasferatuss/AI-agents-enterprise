"""The Tool Gateway — a single, governed entry point for all tool calls (ADR-005).

Security boundary is built into the gateway, not bolted on:
- **registry**: tools are registered typed handlers (no arbitrary shell — there is
  no generic "run command" tool to register against);
- **permission allowlist**: each call is checked against a per-caller allowlist;
  a denied tool is never executed;
- **audit log**: every call (allowed or denied, with args, latency, error) is
  recorded — the governance artifact and the deep-research "trace".
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

    def register(self, spec: ToolSpec, handler: Connector) -> None:
        self._tools[spec.name] = _Registered(spec=spec, handler=handler)

    def list_tools(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def _record(self, tool: str, args: dict, allowed: bool, error: str | None, ms: int) -> None:
        self.audit.append(
            AuditEntry(
                tool=tool,
                args=args,
                allowed=allowed,
                error=error,
                latency_ms=ms,
                at=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            )
        )

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
