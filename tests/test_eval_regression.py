"""Retrieval regression gate (Phase 4 QA).

Deterministic with the HashEmbedder — guards chunking, embedding, and hybrid
search from silently degrading. Thresholds are a baseline floor, not a target;
with real embeddings on the GPU box they would be set higher.
"""

import json
from pathlib import Path

import pytest
from qdrant_client import AsyncQdrantClient

from workbench_evals.regression import run_retrieval_regression
from workbench_evals.types import EvalDataset, QAExample
from workbench_rag import HashEmbedder, QdrantStore, RagPipeline, from_text

# Baseline floor for the golden knowledge base (HashEmbedder + hybrid RRF).
# Each question has exactly one relevant single-chunk doc, so context_precision
# at top_k=3 maxes at 1/3 — the floor below catches "relevant doc crowded out".
TOP_K = 3
MIN_HIT_RATE = 0.80
MIN_MRR = 0.70
MIN_CONTEXT_PRECISION = 0.30

_KB = Path(__file__).resolve().parents[1] / "examples" / "rag" / "knowledge_base.json"


@pytest.fixture
async def pipeline():
    data = json.loads(_KB.read_text())
    store = QdrantStore(AsyncQdrantClient(location=":memory:"), "rag_regression")
    pipe = RagPipeline(HashEmbedder(), store)
    await pipe.ingest([from_text(d["source"], d["text"]) for d in data["documents"]])
    return pipe, data["questions"]


async def test_retrieval_meets_baseline(pipeline):
    pipe, questions = pipeline
    dataset = EvalDataset(
        name="golden-kb",
        examples=[QAExample(**q) for q in questions],
    )
    result = await run_retrieval_regression(pipe, dataset, top_k=TOP_K)

    assert result.n == 6
    assert result.hit_rate >= MIN_HIT_RATE, f"hit_rate regressed: {result.hit_rate}"
    assert result.mrr >= MIN_MRR, f"mrr regressed: {result.mrr}"
    assert result.context_precision >= MIN_CONTEXT_PRECISION, (
        f"context_precision regressed: {result.context_precision}"
    )
