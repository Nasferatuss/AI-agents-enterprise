"""Workflow Orchestrator endpoints (mounted by the gateway)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from workbench_orchestrator import registry
from workbench_orchestrator.types import WorkflowInfo, WorkflowRun
from workbench_runtime.router import NoProviderAvailableError

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])


class RunRequest(BaseModel):
    input: dict = Field(default_factory=dict)


@router.get("", response_model=list[WorkflowInfo])
async def list_workflows() -> list[WorkflowInfo]:
    return [
        WorkflowInfo(name=wf.name, description=wf.description, steps=[s.name for s in wf.steps])
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
        return await registry.run_workflow(name, req.input)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
