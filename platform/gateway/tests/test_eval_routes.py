import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from workbench_gateway.app import create_app
from workbench_gateway.routes import rag as rag_route
from workbench_rag import HashEmbedder, QdrantStore, RagPipeline


@pytest.fixture
async def client(monkeypatch):
    qdrant = AsyncQdrantClient(location=":memory:")
    monkeypatch.setattr(
        rag_route,
        "get_pipeline",
        lambda index: RagPipeline(HashEmbedder(), QdrantStore(qdrant, f"rag_{index}")),
    )
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_eval_requires_exactly_one_dataset_source(client):
    resp = await client.post(
        "/v1/evals/rag",
        json={"index": "kb"},  # neither dataset nor synthetic
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/v1/evals/rag",
        json={
            "index": "kb",
            "synthetic": {"n": 2},
            "dataset": {
                "name": "d",
                "examples": [{"id": "1", "question": "q", "relevant_sources": ["a.md"]}],
            },
        },
    )
    assert resp.status_code == 422


async def test_eval_unknown_index_404(client):
    resp = await client.post("/v1/evals/rag", json={"index": "ghost", "synthetic": {"n": 2}})
    assert resp.status_code == 404
