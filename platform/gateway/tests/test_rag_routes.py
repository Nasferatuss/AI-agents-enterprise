import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from workbench_gateway.app import create_app
from workbench_gateway.routes import rag as rag_route
from workbench_rag import HashEmbedder, QdrantStore, RagPipeline


@pytest.fixture
async def client(monkeypatch):
    qdrant = AsyncQdrantClient(location=":memory:")

    def fake_pipeline(index: str) -> RagPipeline:
        return RagPipeline(HashEmbedder(), QdrantStore(qdrant, f"rag_{index}"))

    monkeypatch.setattr(rag_route, "get_pipeline", fake_pipeline)
    monkeypatch.setattr(rag_route, "_qdrant", lambda: qdrant)

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_ingest_then_search_roundtrip(client):
    resp = await client.post(
        "/v1/rag/indexes/kb/documents",
        json={
            "documents": [
                {"source": "a.md", "text": "# Qdrant\n\nVector search engine."},
                {"source": "b.md", "text": "# Redis\n\nQueues and rate limits."},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"documents": 2, "chunks": 2, "index": "rag_kb"}

    resp = await client.post("/v1/rag/indexes/kb/search", json={"query": "rate limits", "top_k": 1})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["chunk"]["source"] == "b.md"

    resp = await client.get("/v1/rag/indexes")
    assert resp.json() == [{"name": "kb", "chunks": 2}]


async def test_search_unknown_index_404(client):
    resp = await client.post("/v1/rag/indexes/ghost/search", json={"query": "x"})
    assert resp.status_code == 404


async def test_invalid_index_name_rejected(client):
    # Probing attempts on the {index} path segment → 422, before any Qdrant
    # collection name is built from it. (An encoded slash like ..%2F is normalized
    # away at routing and 404s before the handler — also safe, just a different code.)
    for bad in ("UPPER", "has space", "dot.ted", "sym!bol", "x" * 100):
        resp = await client.post(f"/v1/rag/indexes/{bad}/search", json={"query": "x"})
        assert resp.status_code == 422, bad


async def test_ingest_rejects_oversize_document(client):
    resp = await client.post(
        "/v1/rag/indexes/kb/documents",
        json={"documents": [{"source": "big.md", "text": "x" * 200_001}]},
    )
    assert resp.status_code == 422  # per-document char cap


async def test_search_rejects_oversize_query(client):
    resp = await client.post("/v1/rag/indexes/kb/search", json={"query": "x" * 4_001})
    assert resp.status_code == 422  # query char cap before it hits the embedder
