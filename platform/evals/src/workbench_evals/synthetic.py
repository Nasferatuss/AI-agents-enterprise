"""Synthetic QA dataset generation from an indexed corpus.

For each sampled chunk the model writes one question answerable from that chunk
alone — the chunk's source becomes the ground-truth relevant source. Generation
routes at `standard` complexity. Seed of the synthetic-eval-generator module
(Sprint 9).
"""

import json

from workbench_evals.types import EvalDataset, QAExample
from workbench_rag.pipeline import RagPipeline
from workbench_runtime.router import ModelRouter
from workbench_runtime.types import UserMessage
from workbench_shared.logging import get_logger

log = get_logger(__name__)

_SYSTEM = (
    "Write ONE question that can be answered using ONLY the given text, plus "
    "the short answer. The question must be self-contained (no 'this text' "
    "references). Respond with ONLY a JSON object: "
    '{"question": "...", "answer": "..."}'
)


class SyntheticGenerationError(Exception):
    pass


async def generate_dataset(
    pipeline: RagPipeline,
    router: ModelRouter,
    name: str,
    n: int = 10,
) -> EvalDataset:
    corpus = await pipeline.store.all_chunks()
    if not corpus:
        raise SyntheticGenerationError(f"index {pipeline.store.collection} is empty")

    stride = max(len(corpus) // n, 1)
    sampled = corpus[::stride][:n]

    examples: list[QAExample] = []
    for i, chunk in enumerate(sampled):
        out = await router.step(
            [UserMessage(content=chunk.text)],
            complexity="standard",
            system=_SYSTEM,
            max_tokens=512,
        )
        start, end = out.text.find("{"), out.text.rfind("}")
        if start == -1 or end <= start:
            log.warning("synthetic example unparseable, skipping", chunk=chunk.id)
            continue
        try:
            data = json.loads(out.text[start : end + 1])
            examples.append(
                QAExample(
                    id=f"syn-{i}",
                    question=str(data["question"]),
                    expected_answer=str(data.get("answer") or "") or None,
                    relevant_sources=[chunk.source],
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            log.warning("synthetic example unparseable, skipping", chunk=chunk.id)

    if not examples:
        raise SyntheticGenerationError("no synthetic examples could be generated")
    return EvalDataset(name=name, examples=examples)
