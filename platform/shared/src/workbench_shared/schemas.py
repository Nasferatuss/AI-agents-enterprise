"""Base cross-service schemas."""

from typing import Literal

from pydantic import BaseModel

DependencyState = Literal["ok", "unreachable", "skipped"]


class DependencyStatus(BaseModel):
    name: str
    state: DependencyState
    detail: str | None = None


class HealthReport(BaseModel):
    service: str
    version: str
    env: str
    status: Literal["ok", "degraded"]
    dependencies: list[DependencyStatus] = []
