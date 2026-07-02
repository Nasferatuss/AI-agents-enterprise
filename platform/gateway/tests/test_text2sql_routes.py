import httpx
import pytest

from workbench_app_text2sql import api as t2s_api
from workbench_gateway.app import create_app
from workbench_runtime.types import AgentRun, RunContext, Usage


@pytest.fixture
async def client(tmp_path, monkeypatch):
    from sqlalchemy import create_engine

    from workbench_capabilities import create_sample_db

    db = create_sample_db(tmp_path / "retail.db")
    engine = create_engine(f"sqlite:///file:{db}?mode=ro&uri=true")
    monkeypatch.setattr(t2s_api, "get_engine", lambda: engine)

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_schema_endpoint(client):
    resp = await client.get("/v1/apps/text2sql/schema")
    assert resp.status_code == 200
    assert "TABLE customers" in resp.json()["schema"]


async def test_ask_returns_answer_and_sql_path(client, monkeypatch):
    async def stub_run(agent, question):
        return AgentRun(
            agent="text2sql",
            status="completed",
            final_text="There are 10 customers.",
            steps=[],
            usage=Usage(input_tokens=1, output_tokens=1),
            cost_usd=0.0,
            context=RunContext(),
        )

    monkeypatch.setattr(t2s_api, "run_agent", stub_run)
    resp = await client.post("/v1/apps/text2sql/ask", json={"question": "how many customers?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "There are 10 customers."
    assert body["sql_calls"] == []
