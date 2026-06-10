"""Pure (LLM-free) retrieval and citation metrics."""

import re

from workbench_evals.types import CitationMetrics, RetrievalMetrics
from workbench_rag.types import ScoredChunk

_CITATION_RE = re.compile(r"\[(\d+)\]")


def retrieval_metrics(
    retrieved: list[ScoredChunk], relevant_sources: list[str]
) -> RetrievalMetrics:
    relevant = set(relevant_sources)
    hits = [s.chunk.source in relevant for s in retrieved]
    first_rank = next((i + 1 for i, h in enumerate(hits) if h), None)
    return RetrievalMetrics(
        hit=first_rank is not None,
        reciprocal_rank=1.0 / first_rank if first_rank else 0.0,
        context_precision=sum(hits) / len(hits) if hits else 0.0,
    )


def citation_metrics(answer: str, n_retrieved: int) -> CitationMetrics:
    """Citations are inline [n] markers, 1-based against the retrieved list."""
    cited = {int(m) for m in _CITATION_RE.findall(answer)}
    valid = {c for c in cited if 1 <= c <= n_retrieved}
    return CitationMetrics(
        cited=len(cited),
        valid=len(valid),
        accuracy=len(valid) / len(cited) if cited else 0.0,
    )
