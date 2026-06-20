"""Predictable workflow state machine with human-in-the-loop gates (ADR-007).

A workflow is an ordered set of named steps. Each step is an async function
over the shared state dict; it returns updates to merge. Transitions are
explicit: `next` is a step name, a branch function over the state, or None
(end). Retries are per-step with optional delay. A global step budget guards
against branch cycles. No LLM decides the control flow — steps may call models
(via the router), but the graph itself is deterministic and auditable.

**Human-in-the-loop (Sprint 4.1).** A step marked `requires_approval` is a gate:
the engine suspends *before* executing it, the run goes `awaiting_approval`, and
nothing risky has happened yet. A human resumes with approve (run continues and
executes the gate) or reject (run ends `rejected`, the gate never runs). Every
decision is appended to `run.approvals` as an audit trail.

Runs are persisted by the registry to the durable run store
(`workbench_observability.runs`), so a run paused at an approval gate survives a
gateway restart and can be resumed from any replica — see `registry.py`.
"""

import asyncio
import datetime
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from workbench_orchestrator.types import ApprovalDecision, ApprovalRecord, StepAttempt, WorkflowRun
from workbench_shared.logging import get_logger

log = get_logger(__name__)

MAX_STEPS_PER_RUN = 25  # guards against branch cycles

StepFn = Callable[[dict], Awaitable[dict]]
NextFn = Callable[[dict], str | None]


class ApprovalError(Exception):
    """Resume attempted on a run that is not awaiting approval."""


@dataclass(frozen=True)
class Step:
    name: str
    run: StepFn
    next: str | NextFn | None = None  # None → workflow ends after this step
    max_attempts: int = 1
    retry_delay_s: float = 0.0
    requires_approval: bool = False  # gate: suspend for human approval before running
    approval_prompt: str | None = None  # shown to the human at the gate


@dataclass(frozen=True)
class WorkflowDef:
    name: str
    description: str
    steps: list[Step] = field(default_factory=list)

    def __post_init__(self) -> None:
        names = [s.name for s in self.steps]
        if not names:
            raise ValueError(f"workflow {self.name} has no steps")
        if len(names) != len(set(names)):
            raise ValueError(f"workflow {self.name} has duplicate step names")
        for step in self.steps:
            if isinstance(step.next, str) and step.next not in names:
                raise ValueError(f"workflow {self.name}: step {step.name} → unknown {step.next}")

    def step(self, name: str) -> Step:
        return next(s for s in self.steps if s.name == name)

    @property
    def entry(self) -> str:
        return self.steps[0].name

    @property
    def approval_gates(self) -> list[str]:
        return [s.name for s in self.steps if s.requires_approval]


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


async def execute(workflow: WorkflowDef, input_state: dict) -> WorkflowRun:
    run = WorkflowRun(
        id=uuid.uuid4().hex[:12],
        workflow=workflow.name,
        status="running",
        created_at=_utc_now(),
        state=dict(input_state),
    )
    return await _drive(workflow, run, workflow.entry)


async def resume(
    workflow: WorkflowDef,
    run: WorkflowRun,
    *,
    decision: ApprovalDecision,
    actor: str,
    reason: str | None = None,
) -> WorkflowRun:
    """Apply a human decision at the pending approval gate and continue (or end)."""
    if run.status != "awaiting_approval" or run.pending_step is None:
        raise ApprovalError(f"run {run.id} is not awaiting approval (status={run.status})")

    gate = run.pending_step
    run.approvals.append(
        ApprovalRecord(
            step=gate, decision=decision, actor=actor, reason=reason, decided_at=_utc_now()
        )
    )
    run.pending_step = None
    run.approval_prompt = None
    log.info("workflow approval decision", run=run.id, step=gate, decision=decision, actor=actor)

    if decision == "rejected":
        run.status = "rejected"
        run.error = f"step '{gate}' rejected by {actor}"
        return run

    run.status = "running"
    return await _drive(workflow, run, gate)  # gate is now approved → it will execute


async def _drive(workflow: WorkflowDef, run: WorkflowRun, current: str | None) -> WorkflowRun:
    approved = {a.step for a in run.approvals if a.decision == "approved"}

    while current is not None:
        if run.steps_executed >= MAX_STEPS_PER_RUN:
            run.status = "failed"
            run.error = f"step budget exceeded ({MAX_STEPS_PER_RUN}) — branch cycle?"
            break
        step = workflow.step(current)

        # Approval gate: suspend before executing the gated step (nothing risky yet).
        if step.requires_approval and step.name not in approved:
            run.status = "awaiting_approval"
            run.pending_step = step.name
            run.approval_prompt = step.approval_prompt or f"Approve step '{step.name}'?"
            log.info(
                "workflow awaiting approval", workflow=workflow.name, run=run.id, step=step.name
            )
            return run

        run.steps_executed += 1
        succeeded = False
        for attempt in range(1, step.max_attempts + 1):
            started = time.monotonic()
            try:
                updates = await step.run(run.state)
            except Exception as exc:  # noqa: BLE001 — failures become run state
                latency = int((time.monotonic() - started) * 1000)
                last = attempt == step.max_attempts
                run.attempts.append(
                    StepAttempt(
                        step=step.name,
                        attempt=attempt,
                        status="failed" if last else "retried",
                        latency_ms=latency,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                log.warning(
                    "workflow step failed",
                    workflow=workflow.name,
                    run=run.id,
                    step=step.name,
                    attempt=attempt,
                    error=str(exc),
                )
                if not last and step.retry_delay_s:
                    await asyncio.sleep(step.retry_delay_s)
                continue

            latency = int((time.monotonic() - started) * 1000)
            run.state.update(updates or {})
            run.attempts.append(
                StepAttempt(
                    step=step.name,
                    attempt=attempt,
                    status="succeeded",
                    latency_ms=latency,
                    updates=updates or {},
                )
            )
            succeeded = True
            break

        if not succeeded:
            run.status = "failed"
            run.error = f"step '{step.name}' failed after {step.max_attempts} attempt(s)"
            break

        current = step.next(run.state) if callable(step.next) else step.next

    if run.status == "running":
        run.status = "completed"
    log.info(
        "workflow finished",
        workflow=workflow.name,
        run=run.id,
        status=run.status,
        steps=run.steps_executed,
        attempts=len(run.attempts),
    )
    return run
