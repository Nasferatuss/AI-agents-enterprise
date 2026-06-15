"""Synthetic eval dataset generator (module #9).

Extends the basic per-chunk generator with the case types that make an eval set
trustworthy: standard (answerable), negative (off-corpus → must refuse),
multi-hop (needs two sources). Ships a benchmark card — the calibration artifact
that mitigates the "synthetic dataset недостоверен" risk by making composition,
coverage, and the generating model explicit.
"""

import json
from typing import Literal

from pydantic import BaseModel

from workbench_rag.pipeline import RagPipeline
from workbench_runtime.router import ModelRouter
from workbench_runtime.types import UserMessage
from workbench_shared.logging import get_logger

log = get_logger(__name__)

CaseType = Literal["standard", "negative", "multihop"]


class EvalCase(BaseModel):
    id: str
    question: str
    expected_answer: str | None = None
    relevant_sources: list[str] = []  # empty for negative cases (nothing should match)
    case_type: CaseType


class BenchmarkCard(BaseModel):
    dataset: str
    total: int
    by_type: dict[str, int]
    source_coverage: int  # distinct corpus sources referenced
    generator_model: str
    note: str = (
        "Synthetic — calibrate against a human-reviewed subset before trusting "
        "absolute scores. Negative cases score refusal accuracy, not retrieval."
    )


class SyntheticDataset(BaseModel):
    name: str
    cases: list[EvalCase]
    card: BenchmarkCard


class GenerationError(Exception):
    pass


def _parse_obj(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


_STANDARD_SYSTEM = (
    "Write ONE self-contained question answerable from ONLY the given text, plus "
    'a short reference answer. Respond with ONLY JSON: {"question": "...", "answer": "..."}'
)
_MULTIHOP_SYSTEM = (
    "Write ONE question that requires combining BOTH given passages to answer "
    '(multi-hop). Respond with ONLY JSON: {"question": "...", "answer": "..."}'
)
_NEGATIVE_SYSTEM = (
    "Given the TOPICS a knowledge base covers, write ONE plausible question about "
    "a DIFFERENT, related topic that is NOT covered, so a grounded system must "
    'refuse. Respond with ONLY JSON: {"question": "..."}'
)


async def generate_eval_dataset(
    pipeline: RagPipeline,
    router: ModelRouter,
    name: str,
    n_standard: int = 4,
    n_negative: int = 2,
    n_multihop: int = 2,
) -> SyntheticDataset:
    corpus = await pipeline.store.all_chunks()
    if not corpus:
        raise GenerationError(f"index {pipeline.store.collection} is empty")

    cases: list[EvalCase] = []

    # standard — sample distinct chunks
    stride = max(len(corpus) // max(n_standard, 1), 1)
    for i, chunk in enumerate(corpus[::stride][:n_standard]):
        out = await router.step(
            [UserMessage(content=chunk.text)],
            complexity="standard",
            system=_STANDARD_SYSTEM,
            max_tokens=512,
        )
        data = _parse_obj(out.text)
        if data and data.get("question"):
            cases.append(
                EvalCase(
                    id=f"std-{i}",
                    question=str(data["question"]),
                    expected_answer=str(data.get("answer") or "") or None,
                    relevant_sources=[chunk.source],
                    case_type="standard",
                )
            )

    # multi-hop — pair adjacent distinct-source chunks
    pairs = _distinct_source_pairs(corpus, n_multihop)
    for i, (a, b) in enumerate(pairs):
        out = await router.step(
            [UserMessage(content=f"Passage A:\n{a.text}\n\nPassage B:\n{b.text}")],
            complexity="complex",
            system=_MULTIHOP_SYSTEM,
            max_tokens=512,
        )
        data = _parse_obj(out.text)
        if data and data.get("question"):
            cases.append(
                EvalCase(
                    id=f"multi-{i}",
                    question=str(data["question"]),
                    expected_answer=str(data.get("answer") or "") or None,
                    relevant_sources=[a.source, b.source],
                    case_type="multihop",
                )
            )

    # negative — off-corpus questions that must be refused
    topics = ", ".join(sorted({c.source for c in corpus}))
    for i in range(n_negative):
        out = await router.step(
            [UserMessage(content=f"Topics covered: {topics}")],
            complexity="standard",
            system=_NEGATIVE_SYSTEM,
            max_tokens=256,
        )
        data = _parse_obj(out.text)
        if data and data.get("question"):
            cases.append(
                EvalCase(
                    id=f"neg-{i}",
                    question=str(data["question"]),
                    expected_answer="The provided context does not contain the answer.",
                    relevant_sources=[],
                    case_type="negative",
                )
            )

    if not cases:
        raise GenerationError("no synthetic cases could be generated")

    by_type: dict[str, int] = {}
    for c in cases:
        by_type[c.case_type] = by_type.get(c.case_type, 0) + 1
    coverage = len({s for c in cases for s in c.relevant_sources})
    model = next((c for c in [out.model] if c), "") if cases else ""

    log.info("synthetic dataset generated", dataset=name, total=len(cases), by_type=by_type)
    return SyntheticDataset(
        name=name,
        cases=cases,
        card=BenchmarkCard(
            dataset=name,
            total=len(cases),
            by_type=by_type,
            source_coverage=coverage,
            generator_model=model,
        ),
    )


def _distinct_source_pairs(corpus, n):
    pairs = []
    for i in range(0, len(corpus) - 1):
        a, b = corpus[i], corpus[i + 1]
        if a.source != b.source:
            pairs.append((a, b))
        if len(pairs) >= n:
            break
    return pairs
