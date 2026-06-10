"""Agent execution endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from workbench_runtime.agent import run_agent
from workbench_runtime.demo import AGENTS
from workbench_runtime.router import NoProviderAvailableError
from workbench_runtime.types import AgentRun

router = APIRouter(prefix="/v1/agents", tags=["agents"])


class AgentInfo(BaseModel):
    name: str
    complexity: str
    tools: list[str]


class RunRequest(BaseModel):
    input: str = Field(min_length=1)


@router.get("", response_model=list[AgentInfo])
async def list_agents() -> list[AgentInfo]:
    return [
        AgentInfo(name=a.name, complexity=a.complexity, tools=[t.name for t in a.tools])
        for a in AGENTS.values()
    ]


@router.post("/{name}/run", response_model=AgentRun)
async def run(name: str, req: RunRequest) -> AgentRun:
    agent = AGENTS.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {name}")
    try:
        return await run_agent(agent, req.input)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
