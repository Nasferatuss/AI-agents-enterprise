import json

import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from workbench_evals.generator import GenerationError, generate_eval_dataset
from workbench_rag import HashEmbedder, QdrantStore, RagPipeline, from_text
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter

_DOCS = [
    ("kb/a.md", "# Alpha\n\nAlpha is the first module covering ingestion of documents."),
    ("kb/b.md", "# Beta\n\nBeta is the second module covering vector retrieval and search."),
    ("kb/c.md", "# Gamma\n\nGamma is the third module covering evaluation and metrics."),
]


def _router() -> ModelRouter:
    def handler(request: httpx.Request) -> httpx.Response:
        system = next(
            m["content"] for m in json.loads(request.content)["messages"] if m["role"] == "system"
        )
        if "NOT covered" in system:  # negative
            text = json.dumps({"question": "What is the pricing of the SaaS plan?"})
        elif "multi-hop" in system:
            text = json.dumps(
                {"question": "How do Alpha and Beta combine?", "answer": "via the pipeline"}
            )
        else:  # standard
            text = json.dumps({"question": "What does this module cover?", "answer": "a topic"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 15},
            },
        )

    provider = Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )
    r = ModelRouter(
        registry={"fake": provider}, http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    r.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]
    return r


@pytest.fixture
async def pipeline():
    store = QdrantStore(AsyncQdrantClient(location=":memory:"), "rag_gen")
    p = RagPipeline(HashEmbedder(), store)
    await p.ingest([from_text(s, t) for s, t in _DOCS])
    return p


async def test_generates_three_case_types_with_card(pipeline):
    ds = await generate_eval_dataset(
        pipeline, _router(), "gen", n_standard=2, n_negative=1, n_multihop=1
    )
    types = {c.case_type for c in ds.cases}
    assert types == {"standard", "negative", "multihop"}

    negative = next(c for c in ds.cases if c.case_type == "negative")
    assert negative.relevant_sources == []  # nothing should match → refusal expected
    assert "does not contain" in negative.expected_answer

    multihop = next(c for c in ds.cases if c.case_type == "multihop")
    assert len(multihop.relevant_sources) == 2  # needs two sources

    # benchmark card describes the composition (trust/calibration artifact)
    assert ds.card.total == len(ds.cases)
    assert ds.card.by_type["standard"] == 2
    assert ds.card.source_coverage >= 1
    assert "calibrate" in ds.card.note


async def test_empty_index_raises():
    store = QdrantStore(AsyncQdrantClient(location=":memory:"), "rag_empty")
    await store.ensure_collection(dim=256)
    p = RagPipeline(HashEmbedder(), store)
    with pytest.raises(GenerationError):
        await generate_eval_dataset(p, _router(), "x")
