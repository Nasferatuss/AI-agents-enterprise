"""Retrieval regression gate (Phase 4 QA).

Runs an eval dataset through the RAG pipeline and reports retrieval-only metrics
(no LLM needed → deterministic, CI-friendly with the HashEmbedder). A regression
test asserts these stay at or above a baseline, guarding chunking, embedding,
and hybrid-search changes from silently degrading retrieval quality.
"""

from pydantic import BaseModel

from workbench_evals.metrics import retrieval_metrics
from workbench_evals.types import EvalDataset
from workbench_rag.pipeline import RagPipeline


class RetrievalRegression(BaseModel):
    n: int
    hit_rate: float  # any relevant source in top_k
    mrr: float  # mean reciprocal rank of first relevant source
    context_precision: float  # fraction of retrieved chunks from relevant sources


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


async def run_retrieval_regression(
    pipeline: RagPipeline, dataset: EvalDataset, top_k: int = 5
) -> RetrievalRegression:
    hits: list[float] = []
    rr: list[float] = []
    cp: list[float] = []
    for ex in dataset.examples:
        retrieved = await pipeline.search(ex.question, top_k=top_k)
        m = retrieval_metrics(retrieved, ex.relevant_sources)
        hits.append(1.0 if m.hit else 0.0)
        rr.append(m.reciprocal_rank)
        cp.append(m.context_precision)
    return RetrievalRegression(
        n=len(dataset.examples),
        hit_rate=_mean(hits),
        mrr=_mean(rr),
        context_precision=_mean(cp),
    )
