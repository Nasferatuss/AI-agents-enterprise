import json

import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from workbench_evals.judge import parse_verdict
from workbench_evals.metrics import citation_metrics, retrieval_metrics
from workbench_evals.runner import run_rag_eval
from workbench_evals.synthetic import SyntheticGenerationError, generate_dataset
from workbench_evals.types import EvalDataset, QAExample
from workbench_rag.embeddings import HashEmbedder
from workbench_rag.loaders import from_text
from workbench_rag.pipeline import RagPipeline
from workbench_rag.store import QdrantStore
from workbench_rag.types import Chunk, ScoredChunk
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter


def _scored(source: str) -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(id=f"{source}:0", doc_id=source, source=source, ordinal=0, text="t"),
        score=1.0,
        retrieval="hybrid",
    )


def test_retrieval_metrics():
    retrieved = [_scored("a.md"), _scored("b.md"), _scored("c.md")]
    m = retrieval_metrics(retrieved, relevant_sources=["b.md"])
    assert m.hit is True
    assert m.reciprocal_rank == 0.5
    assert m.context_precision == pytest.approx(1 / 3)

    miss = retrieval_metrics(retrieved, relevant_sources=["zzz.md"])
    assert miss.hit is False
    assert miss.reciprocal_rank == 0.0


def test_citation_metrics():
    m = citation_metrics("Per [1] and [3], yes. [9] is bogus.", n_retrieved=3)
    assert m.cited == 3
    assert m.valid == 2
    assert m.accuracy == pytest.approx(2 / 3)
    assert citation_metrics("no citations here", 3).accuracy == 0.0


def test_parse_verdict_handles_fenced_json_and_garbage():
    ok = parse_verdict('Sure!\n```json\n{"score": 0.9, "passed": true, "reasoning": "good"}\n```')
    assert ok.score == 0.9 and ok.passed and not ok.parse_error

    bad = parse_verdict("I think it is fine.")
    assert bad.parse_error is True and bad.score == 0.0

    clamped = parse_verdict('{"score": 7, "passed": true, "reasoning": "x"}')
    assert clamped.score == 1.0


def _text_response(text: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def _fake_router(handler) -> ModelRouter:
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


_DOCS = [
    ("kb/qdrant.md", "# Qdrant\n\nQdrant is the vector database used for dense retrieval."),
    ("kb/redis.md", "# Redis\n\nRedis covers queues, rate limits and temporary state."),
]


@pytest.fixture
async def pipeline():
    store = QdrantStore(AsyncQdrantClient(location=":memory:"), "rag_test")
    p = RagPipeline(HashEmbedder(), store)
    await p.ingest([from_text(s, t) for s, t in _DOCS])
    return p


async def test_run_rag_eval_end_to_end(pipeline, tmp_path, monkeypatch):
    monkeypatch.setenv("WB_EVAL_RESULTS_DIR", str(tmp_path))
    from workbench_shared.config import get_settings

    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = next(m["content"] for m in body["messages"] if m["role"] == "system")
        if "evaluation judge" in system:
            return httpx.Response(
                200,
                json=_text_response('{"score": 0.8, "passed": true, "reasoning": "grounded"}'),
            )
        return httpx.Response(200, json=_text_response("Qdrant stores vectors [1]."))

    dataset = EvalDataset(
        name="smoke",
        examples=[
            QAExample(
                id="q1",
                question="What is the vector database?",
                relevant_sources=["kb/qdrant.md"],
            ),
            QAExample(
                id="q2", question="What handles rate limits?", relevant_sources=["kb/redis.md"]
            ),
        ],
    )
    report = await run_rag_eval(pipeline, _fake_router(handler), dataset, top_k=2, judge=True)

    assert report.aggregates.n == 2
    assert report.aggregates.hit_rate == 1.0  # hash embedder: exact keywords retrieve their doc
    assert report.aggregates.faithfulness == pytest.approx(0.8)
    assert report.aggregates.citation_accuracy == 1.0
    assert report.examples[0].answer == "Qdrant stores vectors [1]."
    assert report.report_path is not None and report.report_path.startswith(str(tmp_path))

    get_settings.cache_clear()


async def test_run_rag_eval_without_judge(pipeline, monkeypatch, tmp_path):
    monkeypatch.setenv("WB_EVAL_RESULTS_DIR", str(tmp_path))
    from workbench_shared.config import get_settings

    get_settings.cache_clear()

    handler = lambda request: httpx.Response(200, json=_text_response("answer [1]"))  # noqa: E731
    dataset = EvalDataset(
        name="nojudge",
        examples=[QAExample(id="q", question="q?", relevant_sources=["kb/qdrant.md"])],
    )
    report = await run_rag_eval(pipeline, _fake_router(handler), dataset, judge=False)
    assert report.judged is False
    assert report.aggregates.faithfulness is None
    assert report.examples[0].faithfulness is None

    get_settings.cache_clear()


async def test_generate_synthetic_dataset(pipeline):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_text_response('{"question": "What does Qdrant do?", "answer": "Vector search."}'),
        )

    dataset = await generate_dataset(pipeline, _fake_router(handler), name="syn", n=2)
    assert len(dataset.examples) == 2
    assert dataset.examples[0].question == "What does Qdrant do?"
    assert dataset.examples[0].relevant_sources[0] in {"kb/qdrant.md", "kb/redis.md"}


async def test_generate_synthetic_empty_index_raises():
    store = QdrantStore(AsyncQdrantClient(location=":memory:"), "rag_empty")
    await store.ensure_collection(dim=256)
    pipeline = RagPipeline(HashEmbedder(), store)
    with pytest.raises(SyntheticGenerationError):
        await generate_dataset(pipeline, _fake_router(lambda r: None), name="x", n=2)
