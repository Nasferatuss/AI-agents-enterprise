"""MCP / Tool Gateway: registry, permission allowlist, audit log (ADR-005)."""

from workbench_toolgateway.connectors import build_default_gateway
from workbench_toolgateway.gateway import ToolGateway
from workbench_toolgateway.types import AuditEntry, ToolResult, ToolSpec

__all__ = ["AuditEntry", "ToolGateway", "ToolResult", "ToolSpec", "build_default_gateway"]
