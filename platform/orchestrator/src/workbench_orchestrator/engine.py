"""Predictable workflow state machine (ADR-007).

A workflow is an ordered set of named steps. Each step is an async function
over the shared state dict; it returns updates to merge. Transitions are
explicit: `next` is a step name, a branch function over the state, or None
(end). Retries are per-step with optional delay. A global step budget guards
against branch cycles. No LLM decides the control flow — steps may call models
(via the router), but the graph itself is deterministic and auditable.

v0 keeps runs in memory; Postgres persistence arrives with the trace layer
(Sprint 5).
"""

import asyncio
import datetime
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from workbench_orchestrator.types import StepAttempt, WorkflowRun
from workbench_shared.logging import get_logger

log = get_logger(__name__)

MAX_STEPS_PER_RUN = 25  # guards against branch cycles

StepFn = Callable[[dict], Awaitable[dict]]
NextFn = Callable[[dict], str | None]


@dataclass(frozen=True)
class Step:
    name: str
    run: StepFn
    next: str | NextFn | None = None  # None → workflow ends after this step
    max_attempts: int = 1
    retry_delay_s: float = 0.0


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


async def execute(workflow: WorkflowDef, input_state: dict) -> WorkflowRun:
    run = WorkflowRun(
        id=uuid.uuid4().hex[:12],
        workflow=workflow.name,
        status="running",
        created_at=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        state=dict(input_state),
    )
    current: str | None = workflow.entry

    while current is not None:
        if run.steps_executed >= MAX_STEPS_PER_RUN:
            run.status = "failed"
            run.error = f"step budget exceeded ({MAX_STEPS_PER_RUN}) — branch cycle?"
            break
        step = workflow.step(current)
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
