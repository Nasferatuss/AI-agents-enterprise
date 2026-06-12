"""Text-to-SQL agent: schema-aware instructions + guarded run_sql tool."""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import Engine, create_engine, make_url

from workbench_app_text2sql.safe_sql import MAX_ROWS, SqlGuardError, execute_sql
from workbench_app_text2sql.sampledb import create_sample_db
from workbench_app_text2sql.schema import reflect_tables, schema_description
from workbench_runtime.agent import Agent
from workbench_runtime.tools import Tool
from workbench_shared.config import get_settings

_TOOL_ROWS_SHOWN = 50  # keep tool results small in the context window

_INSTRUCTIONS_TEMPLATE = """You are a BI analyst agent answering business questions \
over a SQL database.

Rules:
- Use the run_sql tool for every fact; never invent numbers.
- Read-only: a single SELECT per call (CTEs allowed). Writes are rejected.
- Results are capped at {max_rows} rows — aggregate in SQL instead of paging raw rows.
- Finish with a concise business answer; show the key numbers and mention the SQL used.

Database schema:
{schema}"""


class RunSqlInput(BaseModel):
    sql: str = Field(description="One read-only SELECT statement (CTEs allowed)")


def _dialect(engine: Engine) -> str:
    return "sqlite" if engine.dialect.name == "sqlite" else engine.dialect.name


def make_run_sql_tool(engine: Engine, allowed_tables: set[str]) -> Tool:
    async def run_sql(inp: RunSqlInput) -> str:
        try:
            sql, columns, rows = await execute_sql(
                engine, inp.sql, allowed_tables, dialect=_dialect(engine)
            )
        except SqlGuardError as exc:
            raise SqlGuardError(str(exc)) from exc  # surfaces as is_error tool result
        return json.dumps(
            {
                "sql": sql,
                "columns": columns,
                "rows": rows[:_TOOL_ROWS_SHOWN],
                "row_count": len(rows),
                "truncated": len(rows) > _TOOL_ROWS_SHOWN,
            },
            ensure_ascii=False,
            default=str,
        )

    return Tool(
        name="run_sql",
        description=(
            "Execute ONE read-only SELECT against the BI database and get columns/rows "
            f"as JSON (max {MAX_ROWS} rows). Call it whenever the answer needs data."
        ),
        input_model=RunSqlInput,
        handler=run_sql,
    )


def build_agent(engine: Engine) -> Agent:
    allowed = reflect_tables(engine)
    return Agent(
        name="text2sql",
        instructions=_INSTRUCTIONS_TEMPLATE.format(
            max_rows=MAX_ROWS, schema=schema_description(engine)
        ),
        tools=[make_run_sql_tool(engine, allowed)],
        complexity="standard",
        max_steps=6,
    )


@lru_cache
def get_engine() -> Engine:
    """BI engine from settings; sqlite opens read-only, sample DB auto-created."""
    url = make_url(get_settings().bi_database_url)
    if url.get_backend_name() == "sqlite" and url.database:
        db_path = Path(url.database)
        if not db_path.exists():
            create_sample_db(db_path)
        ro_uri = f"file:{db_path}?mode=ro&uri=true"
        return create_engine(f"sqlite:///{ro_uri}")
    return create_engine(url)  # non-sqlite: use a read-only DB user (ADR-004)
