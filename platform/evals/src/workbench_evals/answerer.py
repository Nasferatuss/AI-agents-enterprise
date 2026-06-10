"""RAG answerer: retrieve → answer strictly from context with [n] citations."""

from workbench_rag.pipeline import RagPipeline
from workbench_rag.types import ScoredChunk
from workbench_runtime.router import ModelRouter
from workbench_runtime.types import UserMessage

_SYSTEM = (
    "Answer the question using ONLY the numbered context chunks. Cite every "
    "claim with inline markers like [1] or [2] referring to chunk numbers. "
    "If the context does not contain the answer, say exactly: "
    '"The provided context does not contain the answer."'
)


def _render_context(chunks: list[ScoredChunk]) -> str:
    return "\n\n".join(
        f"[{i + 1}] ({s.chunk.source})\n{s.chunk.text}" for i, s in enumerate(chunks)
    )


async def rag_answer(
    pipeline: RagPipeline,
    router: ModelRouter,
    question: str,
    top_k: int = 5,
) -> tuple[str, list[ScoredChunk], float | None]:
    """Returns (answer, retrieved chunks, llm cost)."""
    retrieved = await pipeline.search(question, top_k=top_k)
    prompt = f"Context:\n{_render_context(retrieved)}\n\nQuestion: {question}"
    out = await router.step(
        [UserMessage(content=prompt)],
        complexity="standard",
        system=_SYSTEM,
        max_tokens=1024,
    )
    return out.text, retrieved, out.cost_usd
