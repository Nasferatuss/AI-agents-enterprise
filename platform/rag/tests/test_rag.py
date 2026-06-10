import pytest
from qdrant_client import AsyncQdrantClient

from workbench_rag.chunking import chunk_document
from workbench_rag.embeddings import HashEmbedder
from workbench_rag.loaders import from_text
from workbench_rag.pipeline import RagPipeline, rrf_fuse
from workbench_rag.store import QdrantStore
from workbench_rag.types import Chunk, Document


def _chunk(cid: str, text: str = "t") -> Chunk:
    return Chunk(id=cid, doc_id="d", source="s", ordinal=0, text=text)


def test_chunker_splits_on_headings():
    doc = Document(
        id="d1",
        source="test.md",
        text="# Intro\n\nFirst section text.\n\n# Details\n\nSecond section text.",
    )
    chunks = chunk_document(doc)
    assert len(chunks) == 2
    assert chunks[0].text.startswith("# Intro")
    assert chunks[1].text.startswith("# Details")
    assert [c.ordinal for c in chunks] == [0, 1]


def test_chunker_packs_long_sections_with_overlap():
    paragraphs = "\n\n".join(f"Paragraph {i} " + "word " * 80 for i in range(10))
    doc = Document(id="d2", source="long.md", text=paragraphs)
    chunks = chunk_document(doc, target_tokens=200, overlap_tokens=30)
    assert len(chunks) > 1
    # overlap: the tail of chunk N appears at the head of chunk N+1
    assert chunks[0].text[-50:].strip()[:20] in chunks[1].text[:400]


def test_chunker_empty_doc():
    assert chunk_document(Document(id="e", source="e.md", text="")) == []


def test_rrf_prefers_items_ranked_high_in_both():
    both = _chunk("both")
    dense_only = _chunk("dense")
    lex_only = _chunk("lex")
    fused = rrf_fuse([[both, dense_only], [both, lex_only]], top_k=3)
    assert fused[0].chunk.id == "both"
    assert {s.chunk.id for s in fused} == {"both", "dense", "lex"}


@pytest.fixture
async def pipeline():
    store = QdrantStore(AsyncQdrantClient(location=":memory:"), "rag_test")
    return RagPipeline(HashEmbedder(), store)


_DOCS = [
    ("kb/postgres.md", "# Postgres\n\nPostgres handles relational storage, traces and audit logs."),
    ("kb/qdrant.md", "# Qdrant\n\nQdrant is the vector database used for dense retrieval."),
    ("kb/redis.md", "# Redis\n\nRedis covers queues, rate limits and temporary state."),
]


async def test_ingest_and_dense_search(pipeline):
    stats = await pipeline.ingest([from_text(s, t) for s, t in _DOCS])
    assert stats.documents == 3
    assert stats.chunks == 3
    assert await pipeline.store.count() == 3

    results = await pipeline.search("vector database dense retrieval", top_k=2, hybrid=False)
    assert results[0].chunk.source == "kb/qdrant.md"
    assert results[0].retrieval == "dense"


async def test_hybrid_search_finds_keyword_match(pipeline):
    await pipeline.ingest([from_text(s, t) for s, t in _DOCS])
    results = await pipeline.search("rate limits", top_k=2, hybrid=True)
    assert results[0].chunk.source == "kb/redis.md"
    assert results[0].retrieval == "hybrid"


async def test_reingest_is_idempotent(pipeline):
    docs = [from_text(s, t) for s, t in _DOCS]
    await pipeline.ingest(docs)
    await pipeline.ingest(docs)  # same ids → upsert, not duplicates
    assert await pipeline.store.count() == 3


async def test_search_empty_index(pipeline):
    await pipeline.store.ensure_collection(dim=256)
    assert await pipeline.search("anything", hybrid=True) == []
