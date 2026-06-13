"""Demo workflow `content_brief`: 5 steps with retry, branching and a review loop.

validate → draft (standard tier) → review (judge tier) →
  ├─ passed → finalize
  └─ failed and no revision yet → revise → review (bounded loop)

Shows the composable pattern from ADR-007: LLM calls live inside steps, the
control flow stays deterministic.
"""

import json

from workbench_orchestrator.engine import Step, WorkflowDef
from workbench_orchestrator.registry import register
from workbench_runtime.router import get_router
from workbench_runtime.types import ChatMessage

_MAX_REVISIONS = 1


async def validate(state: dict) -> dict:
    topic = str(state.get("topic", "")).strip()
    if not topic:
        raise ValueError("input must contain a non-empty 'topic'")
    return {"topic": topic, "revisions": 0}


async def draft(state: dict) -> dict:
    completion = await get_router().complete(
        [
            ChatMessage(
                role="user", content=f"Write a 5-bullet executive brief on: {state['topic']}"
            )
        ],
        complexity="standard",
        max_tokens=1024,
    )
    return {"draft": completion.text}


async def review(state: dict) -> dict:
    completion = await get_router().complete(
        [
            ChatMessage(
                role="user",
                content=(
                    "Review this executive brief for clarity and substance. Respond with "
                    'ONLY JSON: {"score": <0.0-1.0>, "passed": <true|false>, '
                    f'"feedback": "<one sentence>"}}\n\nBrief:\n{state["draft"]}'
                ),
            )
        ],
        complexity="judge",
        max_tokens=512,
    )
    text = completion.text
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start : end + 1])
        return {
            "review_score": float(data["score"]),
            "review_passed": bool(data["passed"]),
            "review_feedback": str(data.get("feedback", "")),
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # Unparseable review counts as failed so the workflow revises once
        return {
            "review_score": 0.0,
            "review_passed": False,
            "review_feedback": "unparseable review",
        }


def after_review(state: dict) -> str:
    if state.get("review_passed") or state.get("revisions", 0) >= _MAX_REVISIONS:
        return "finalize"
    return "revise"


async def revise(state: dict) -> dict:
    completion = await get_router().complete(
        [
            ChatMessage(
                role="user",
                content=(
                    f"Improve this executive brief. Reviewer feedback: "
                    f"{state.get('review_feedback', '')}\n\nBrief:\n{state['draft']}"
                ),
            )
        ],
        complexity="standard",
        max_tokens=1024,
    )
    return {"draft": completion.text, "revisions": state.get("revisions", 0) + 1}


async def finalize(state: dict) -> dict:
    header = f"# Executive brief: {state['topic']}\n\n"
    note = "" if state.get("review_passed") else "\n\n> note: shipped after max revisions"
    return {"brief": header + state["draft"] + note}


CONTENT_BRIEF = register(
    WorkflowDef(
        name="content_brief",
        description="Draft → judge review → optional revision → final brief",
        steps=[
            Step(name="validate", run=validate, next="draft"),
            Step(name="draft", run=draft, next="review", max_attempts=2),
            Step(name="review", run=review, next=after_review, max_attempts=2),
            Step(name="revise", run=revise, next="review"),
            Step(name="finalize", run=finalize, next=None),
        ],
    )
)
