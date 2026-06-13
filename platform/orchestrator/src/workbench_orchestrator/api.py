"""Workflow Orchestrator endpoints (mounted by the gateway)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from workbench_orchestrator import registry
from workbench_orchestrator.engine import ApprovalError
from workbench_orchestrator.tracing import record_workflow_run
from workbench_orchestrator.types import WorkflowInfo, WorkflowRun
from workbench_runtime.router import NoProviderAvailableError

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])


class RunRequest(BaseModel):
    input: dict = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    actor: str = Field(min_length=1)  # who is approving/rejecting (audit)
    reason: str | None = None


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
    return registry.list_runs()


@router.get("/runs/{run_id}", response_model=WorkflowRun)
async def get_run(run_id: str) -> WorkflowRun:
    run = registry.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    return run


@router.post("/{name}/run", response_model=WorkflowRun)
async def run(name: str, req: RunRequest) -> WorkflowRun:
    if name not in registry.WORKFLOWS:
        raise HTTPException(status_code=404, detail=f"unknown workflow: {name}")
    try:
        wf_run = await registry.run_workflow(name, req.input)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await record_workflow_run(wf_run)  # skipped automatically if awaiting_approval
    return wf_run


async def _decide(run_id: str, decision, req: ApprovalRequest) -> WorkflowRun:
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
async def approve(run_id: str, req: ApprovalRequest) -> WorkflowRun:
    return await _decide(run_id, "approved", req)


@router.post("/runs/{run_id}/reject", response_model=WorkflowRun)
async def reject(run_id: str, req: ApprovalRequest) -> WorkflowRun:
    return await _decide(run_id, "rejected", req)
