"""End-to-end functional QA (Phase 4): a cross-layer journey through the gateway.

Exercises RAG → text2sql → orchestrator → observability over real HTTP, with the
deterministic (no-LLM) paths, and asserts the observability layer captured the
run. Crosses every platform layer the MVP ships.
"""

import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from workbench_gateway.app import create_app
from workbench_gateway.routes import rag as rag_route
from workbench_observability import init_db
from workbench_orchestrator import Step, WorkflowDef, register
from workbench_rag import HashEmbedder, QdrantStore, RagPipeline


@pytest.fixture
async def client(monkeypatch):
    await init_db()
    qdrant = AsyncQdrantClient(location=":memory:")
    monkeypatch.setattr(
        rag_route,
        "get_pipeline",
        lambda index: RagPipeline(HashEmbedder(), QdrantStore(qdrant, f"rag_{index}")),
    )

    async def noop(state):
        return {"ok": True}

    register(WorkflowDef(name="journey_wf", description="", steps=[Step(name="s", run=noop)]))

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_full_platform_journey(client):
    # 1. health: gateway is up
    assert (await client.get("/healthz")).json()["status"] == "ok"

    # 2. RAG: ingest then retrieve
    ingest = await client.post(
        "/v1/rag/indexes/kb/documents",
        json={
            "documents": [
                {"source": "a.md", "text": "# Qdrant\n\nVector database for dense retrieval."},
                {"source": "b.md", "text": "# Redis\n\nQueues and rate limiting."},
            ]
        },
    )
    assert ingest.json()["chunks"] == 2
    found = await client.post("/v1/rag/indexes/kb/search", json={"query": "rate limiting"})
    assert found.json()[0]["chunk"]["source"] == "b.md"

    # 3. text2sql: schema explorer works end to end
    schema = await client.get("/v1/apps/text2sql/schema")
    assert "TABLE customers" in schema.json()["schema"]

    # 4. orchestrator: run a workflow to completion
    run = await client.post("/v1/workflows/journey_wf/run", json={"input": {}})
    assert run.json()["status"] == "completed"

    # 5. observability: the workflow run was traced and shows in the dashboard
    traces = (await client.get("/v1/observability/traces")).json()
    assert any(t["name"] == "journey_wf" and t["status"] == "completed" for t in traces)
    summary = (await client.get("/v1/observability/summary")).json()
    assert summary["total"] >= 1
    assert summary["by_kind"].get("workflow", 0) >= 1


async def test_models_and_agents_surface_listable(client):
    # discovery endpoints respond even with no providers configured
    assert (await client.get("/v1/models")).status_code == 200
    agents = (await client.get("/v1/agents")).json()
    assert any(a["name"] == "demo" for a in agents)
    workflows = (await client.get("/v1/workflows")).json()
    assert any(w["name"] == "access_request" for w in workflows)
