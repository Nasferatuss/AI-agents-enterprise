"""Evaluation Engine types: datasets, per-example results, reports."""

from pydantic import BaseModel, Field

from workbench_rag.types import ScoredChunk


class QAExample(BaseModel):
    id: str
    question: str
    expected_answer: str | None = None
    relevant_sources: list[str] = Field(min_length=1)  # doc sources that contain the answer


class EvalDataset(BaseModel):
    name: str
    examples: list[QAExample] = Field(min_length=1)


class RetrievalMetrics(BaseModel):
    hit: bool  # any relevant source retrieved in top_k
    reciprocal_rank: float  # 1/rank of first relevant source, 0 if none
    context_precision: float  # fraction of retrieved chunks from relevant sources


class JudgeVerdict(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    reasoning: str
    parse_error: bool = False


class CitationMetrics(BaseModel):
    cited: int  # distinct [n] markers in the answer
    valid: int  # markers pointing at an actually retrieved chunk
    accuracy: float  # valid/cited; 0.0 when nothing is cited


class ExampleReport(BaseModel):
    example_id: str
    question: str
    retrieval: RetrievalMetrics
    retrieved: list[ScoredChunk]
    answer: str | None = None
    citations: CitationMetrics | None = None
    faithfulness: JudgeVerdict | None = None
    answer_relevance: JudgeVerdict | None = None


class EvalAggregates(BaseModel):
    n: int
    hit_rate: float
    mrr: float
    context_precision: float
    citation_accuracy: float | None = None
    faithfulness: float | None = None
    answer_relevance: float | None = None


class EvalReport(BaseModel):
    dataset: str
    index: str
    top_k: int
    judged: bool
    created_at: str
    aggregates: EvalAggregates
    examples: list[ExampleReport]
    llm_cost_usd: float | None = None  # answers + judges combined
    report_path: str | None = None
