"""Workflow Orchestrator types."""

from typing import Literal

from pydantic import BaseModel, Field

StepStatus = Literal["succeeded", "failed", "retried"]
RunStatus = Literal["running", "completed", "failed"]


class StepAttempt(BaseModel):
    step: str
    attempt: int  # 1-based
    status: StepStatus
    latency_ms: int
    error: str | None = None
    updates: dict = Field(default_factory=dict)  # what the step merged into state


class WorkflowRun(BaseModel):
    id: str
    workflow: str
    status: RunStatus
    created_at: str
    state: dict = Field(default_factory=dict)
    attempts: list[StepAttempt] = []
    error: str | None = None
    steps_executed: int = 0


class WorkflowInfo(BaseModel):
    name: str
    description: str
    steps: list[str]
