import json

import httpx
import pytest
from sqlalchemy import create_engine

from workbench_app_text2sql.agent import build_agent
from workbench_capabilities import create_sample_db, schema_description
from workbench_runtime.agent import run_agent
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter


@pytest.fixture
def engine(tmp_path):
    db = create_sample_db(tmp_path / "retail.db")
    return create_engine(f"sqlite:///file:{db}?mode=ro&uri=true")


def test_schema_description_lists_tables_and_fks(engine):
    schema = schema_description(engine)
    for table in ("customers", "products", "orders", "order_items"):
        assert f"TABLE {table}" in schema
    assert "-> customers.id" in schema
    assert schema == schema_description(engine)  # deterministic (prompt caching)


def _tool_call_response(name: str, arguments: dict) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def _text_response(text: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 7},
    }


def _router(responses: list[dict]) -> ModelRouter:
    calls = iter(responses)
    handler = lambda request: httpx.Response(200, json=next(calls))  # noqa: E731
    provider = Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )
    router = ModelRouter(
        registry={"fake": provider},
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    router.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]
    return router


async def test_agent_answers_with_sql_tool(engine):
    agent = build_agent(engine)
    router = _router(
        [
            _tool_call_response("run_sql", {"sql": "SELECT COUNT(*) AS n FROM customers"}),
            _text_response("There are 10 customers."),
        ]
    )
    run = await run_agent(agent, "How many customers do we have?", router=router)

    assert run.status == "completed"
    assert run.final_text == "There are 10 customers."
    execution = run.steps[0].tool_executions[0]
    assert execution.is_error is False
    payload = json.loads(execution.result)
    assert payload["rows"] == [[10]]
    assert "LIMIT" in payload["sql"]


async def test_agent_survives_rejected_sql(engine):
    agent = build_agent(engine)
    router = _router(
        [
            _tool_call_response("run_sql", {"sql": "DELETE FROM customers"}),
            _text_response("I cannot modify data; the database is read-only."),
        ]
    )
    run = await run_agent(agent, "delete everything", router=router)

    assert run.status == "completed"
    execution = run.steps[0].tool_executions[0]
    assert execution.is_error is True
    assert "forbidden" in execution.result.lower() or "read-only" in execution.result.lower()
