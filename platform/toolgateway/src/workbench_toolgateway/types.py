"""Tool Gateway types (MCP-style: named tools with JSON schemas)."""

from typing import Any

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool: str
    allowed: bool  # False when denied by the permission allowlist or unknown
    latency_ms: int = 0
    output: Any = None  # JSON-serializable connector output
    error: str | None = None


class AuditEntry(BaseModel):
    """One row of the tool-call audit log (governance artifact, ADR-005)."""

    tool: str
    args: dict
    allowed: bool
    error: str | None = None
    latency_ms: int = 0
    at: str  # ISO timestamp
