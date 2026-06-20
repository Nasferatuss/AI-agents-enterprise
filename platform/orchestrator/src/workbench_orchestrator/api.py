"""Workflow Orchestrator endpoints (mounted by the gateway)."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from workbench_orchestrator import registry
from workbench_orchestrator.engine import ApprovalError
from workbench_orchestrator.tracing import record_workflow_run
from workbench_orchestrator.types import WorkflowInfo, WorkflowRun
from workbench_runtime.router import NoProviderAvailableError
from workbench_shared.config import get_settings

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])


class RunRequest(BaseModel):
    input: dict = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=128)  # who is approving/rejecting (audit)
    reason: str | None = Field(default=None, max_length=2000)


def _check_approval_token(provided: str | None) -> None:
    """Optional shared-secret gate (Finding 2). Open when WB_APPROVAL_TOKEN unset
    (local demo); enforced when configured so the governance control isn't a
    purely self-attested actor string."""
    required = get_settings().approval_token
    if required and provided != required:
        raise HTTPException(status_code=401, detail="invalid or missing approval token")


@router.get("", response_model=list[WorkflowInfo])
async def list_workflows() -> list[WorkflowInfo]:
    return [
        WorkflowInfo(
            name=wf.name,
            description=wf.description,
            steps=[s.name for s in wf.steps],
            approval_gates=wf.approval_gates,
        )
        for wf in registry.WORKFLOWS.values()
    ]


@router.get("/runs", response_model=list[WorkflowRun])
async def list_runs() -> list[WorkflowRun]:
    return await registry.list_runs()


@router.get("/runs/{run_id}", response_model=WorkflowRun)
async def get_run(run_id: str) -> WorkflowRun:
    run = await registry.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    return run


@router.post("/{name}/run", response_model=WorkflowRun)
async def run(
    name: str,
    req: RunRequest,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> WorkflowRun:
    if name not in registry.WORKFLOWS:
        raise HTTPException(status_code=404, detail=f"unknown workflow: {name}")
    try:
        wf_run = await registry.run_workflow(name, req.input, idempotency_key=idempotency_key)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await record_workflow_run(wf_run)  # skipped automatically if awaiting_approval
    return wf_run


async def _decide(run_id: str, decision, req: ApprovalRequest, token: str | None) -> WorkflowRun:
    _check_approval_token(token)
    try:
        resumed = await registry.resume_run(
            run_id, decision=decision, actor=req.actor, reason=req.reason
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}") from exc
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await record_workflow_run(resumed)  # now terminal → recorded
    return resumed


@router.post("/runs/{run_id}/approve", response_model=WorkflowRun)
async def approve(
    run_id: str,
    req: ApprovalRequest,
    x_approval_token: Annotated[str | None, Header()] = None,
) -> WorkflowRun:
    return await _decide(run_id, "approved", req, x_approval_token)


@router.post("/runs/{run_id}/reject", response_model=WorkflowRun)
async def reject(
    run_id: str,
    req: ApprovalRequest,
    x_approval_token: Annotated[str | None, Header()] = None,
) -> WorkflowRun:
    return await _decide(run_id, "rejected", req, x_approval_token)
