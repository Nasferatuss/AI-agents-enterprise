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


# --- access_request: human-in-the-loop demo (Sprint 4.1) ---
# The risky action (granting access) sits behind an approval gate. The engine
# suspends before `grant` runs, so nothing is granted until a human approves —
# and the LLM risk assessment is in run state for the reviewer to read.


async def validate_access(state: dict) -> dict:
    resource = str(state.get("resource", "")).strip()
    requester = str(state.get("requester", "")).strip()
    if not resource or not requester:
        raise ValueError("input must contain non-empty 'resource' and 'requester'")
    return {"resource": resource, "requester": requester}


async def assess_access(state: dict) -> dict:
    completion = await get_router().complete(
        [
            ChatMessage(
                role="user",
                content=(
                    f"In one sentence, summarize the security risk of granting "
                    f"'{state['requester']}' access to '{state['resource']}'."
                ),
            )
        ],
        complexity="standard",
        max_tokens=256,
    )
    return {"risk_assessment": completion.text}


async def grant_access(state: dict) -> dict:
    return {
        "granted": True,
        "grant_note": f"Access to '{state['resource']}' granted to '{state['requester']}'.",
    }


ACCESS_REQUEST = register(
    WorkflowDef(
        name="access_request",
        description="Validate → assess risk → HUMAN APPROVAL → grant access",
        steps=[
            Step(name="validate", run=validate_access, next="assess"),
            Step(name="assess", run=assess_access, next="grant", max_attempts=2),
            Step(
                name="grant",
                run=grant_access,
                next=None,
                requires_approval=True,
                approval_prompt=(
                    "Approve granting this access? Review `risk_assessment` in the run "
                    "state before deciding."
                ),
            ),
        ],
    )
)
