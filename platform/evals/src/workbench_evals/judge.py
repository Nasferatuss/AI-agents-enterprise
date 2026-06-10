"""LLM-as-judge scorers (faithfulness, answer relevance).

Judges route at complexity="judge" — per ADR-008 the judge must be a stronger
model than the one being judged, so this lands on the frontier tier. Verdicts
are requested as JSON and parsed defensively: an unparseable verdict scores 0
with parse_error=True rather than crashing the eval run.
"""

import json

from workbench_evals.types import JudgeVerdict
from workbench_runtime.router import ModelRouter
from workbench_runtime.types import UserMessage

_FAITHFULNESS_SYSTEM = (
    "You are a strict evaluation judge. Given context, question and answer, "
    "judge whether the answer is fully grounded in the context (no invented "
    "facts). Respond with ONLY a JSON object: "
    '{"score": <0.0-1.0>, "passed": <true|false>, "reasoning": "<one sentence>"}'
)

_RELEVANCE_SYSTEM = (
    "You are a strict evaluation judge. Judge whether the answer actually "
    "addresses the question (regardless of factual grounding). Respond with "
    "ONLY a JSON object: "
    '{"score": <0.0-1.0>, "passed": <true|false>, "reasoning": "<one sentence>"}'
)


def parse_verdict(text: str) -> JudgeVerdict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return JudgeVerdict(
            score=0.0, passed=False, reasoning="unparseable verdict", parse_error=True
        )
    try:
        data = json.loads(text[start : end + 1])
        return JudgeVerdict(
            score=max(0.0, min(1.0, float(data["score"]))),
            passed=bool(data["passed"]),
            reasoning=str(data.get("reasoning", "")),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return JudgeVerdict(
            score=0.0, passed=False, reasoning="unparseable verdict", parse_error=True
        )


async def _judge(
    router: ModelRouter, system: str, prompt: str
) -> tuple[JudgeVerdict, float | None]:
    out = await router.step(
        [UserMessage(content=prompt)], complexity="judge", system=system, max_tokens=512
    )
    return parse_verdict(out.text), out.cost_usd


async def judge_faithfulness(
    router: ModelRouter, question: str, context: str, answer: str
) -> tuple[JudgeVerdict, float | None]:
    prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer to judge:\n{answer}"
    return await _judge(router, _FAITHFULNESS_SYSTEM, prompt)


async def judge_relevance(
    router: ModelRouter, question: str, answer: str
) -> tuple[JudgeVerdict, float | None]:
    prompt = f"Question: {question}\n\nAnswer to judge:\n{answer}"
    return await _judge(router, _RELEVANCE_SYSTEM, prompt)
