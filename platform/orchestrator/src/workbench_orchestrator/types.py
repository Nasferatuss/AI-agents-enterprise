"""Workflow Orchestrator types."""

from typing import Literal

from pydantic import BaseModel, Field

StepStatus = Literal["succeeded", "failed", "retried"]
# awaiting_approval / rejected are the human-in-the-loop states (Sprint 4.1).
RunStatus = Literal["running", "completed", "failed", "awaiting_approval", "rejected"]
ApprovalDecision = Literal["approved", "rejected"]


class StepAttempt(BaseModel):
    step: str
    attempt: int  # 1-based
    status: StepStatus
    latency_ms: int
    error: str | None = None
    updates: dict = Field(default_factory=dict)  # what the step merged into state


class ApprovalRecord(BaseModel):
    """Audit entry for one human decision at an approval gate (ADR-007 → governance)."""

    step: str
    decision: ApprovalDecision
    actor: str
    reason: str | None = None
    decided_at: str


class WorkflowRun(BaseModel):
    id: str
    workflow: str
    status: RunStatus
    created_at: str
    state: dict = Field(default_factory=dict)
    attempts: list[StepAttempt] = []
    approvals: list[ApprovalRecord] = []  # audit log of human decisions
    pending_step: str | None = None  # the gated step awaiting approval (when paused)
    approval_prompt: str | None = None  # what the human is being asked to approve
    error: str | None = None
    steps_executed: int = 0


class WorkflowInfo(BaseModel):
    name: str
    description: str
    steps: list[str]
    approval_gates: list[str]  # steps that require human approval
