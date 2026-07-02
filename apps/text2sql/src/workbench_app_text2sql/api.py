"""Text-to-SQL app endpoints (mounted by the gateway)."""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from workbench_app_text2sql.agent import build_agent
from workbench_capabilities import get_engine, schema_description
from workbench_runtime.agent import run_agent
from workbench_runtime.router import NoProviderAvailableError
from workbench_runtime.tracing import record_agent_run
from workbench_runtime.types import AgentRun

router = APIRouter(prefix="/v1/apps/text2sql", tags=["text2sql"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)  # bound LLM token cost


class SqlCall(BaseModel):
    sql: str
    columns: list[str] = []
    rows: list[list] = []
    row_count: int = 0
    is_error: bool = False
    error: str | None = None


class AskResponse(BaseModel):
    answer: str
    sql_calls: list[SqlCall]  # full question → SQL → result path for the UI
    run: AgentRun


def _extract_sql_calls(run: AgentRun) -> list[SqlCall]:
    calls: list[SqlCall] = []
    for step in run.steps:
        for ex in step.tool_executions:
            if ex.name != "run_sql":
                continue
            if ex.is_error:
                calls.append(
                    SqlCall(sql=str(ex.arguments.get("sql", "")), is_error=True, error=ex.result)
                )
                continue
            try:
                data = json.loads(ex.result)
                calls.append(
                    SqlCall(
                        sql=data["sql"],
                        columns=data["columns"],
                        rows=data["rows"],
                        row_count=data["row_count"],
                    )
                )
            except (json.JSONDecodeError, KeyError):
                calls.append(
                    SqlCall(
                        sql=str(ex.arguments.get("sql", "")),
                        is_error=True,
                        error="unparseable tool result",
                    )
                )
    return calls


@router.get("/schema")
async def get_schema() -> dict:
    return {"schema": schema_description(get_engine())}


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    agent = build_agent(get_engine())
    try:
        run = await run_agent(agent, req.question)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await record_agent_run(run, name="text2sql")  # trace under the app name
    return AskResponse(answer=run.final_text, sql_calls=_extract_sql_calls(run), run=run)
