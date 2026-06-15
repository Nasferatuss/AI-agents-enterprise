"""Process Investigator: a document becomes a structured process analysis.

One structured LLM call (complexity=complex — this is reasoning over a spec)
extracts entities, ordered process steps, contradictions/gaps, and a backlog.
The Mermaid process map is rendered from the steps by pure code, so the diagram
is deterministic given the extracted steps.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field

from workbench_runtime.router import ModelRouter
from workbench_runtime.types import UserMessage

_SYSTEM = (
    "You are a business analyst. Read the document (a spec / process description) "
    "and extract its structure. Respond with ONLY a JSON object with these keys:\n"
    '{"entities": [{"name": "...", "type": "actor|system|data"}],\n'
    ' "steps": [{"id": 1, "actor": "...", "action": "...", "next": [2]}],\n'
    ' "contradictions": ["short description of a gap or conflict"],\n'
    ' "backlog": [{"title": "...", "priority": "high|medium|low"}]}\n'
    "Steps must be ordered; `next` lists the ids of following steps (empty for an end). "
    "Surface real contradictions, ambiguities, and missing decisions."
)


class Entity(BaseModel):
    name: str
    type: Literal["actor", "system", "data"] = "actor"


class ProcessStep(BaseModel):
    id: int
    actor: str = ""
    action: str
    next: list[int] = Field(default_factory=list)


class BacklogItem(BaseModel):
    title: str
    priority: Literal["high", "medium", "low"] = "medium"


class ProcessReport(BaseModel):
    entities: list[Entity] = []
    steps: list[ProcessStep] = []
    contradictions: list[str] = []
    backlog: list[BacklogItem] = []
    mermaid: str = ""
    provider: str = ""
    model: str = ""
    cost_usd: float | None = None


class ProcessAnalysisError(Exception):
    pass


def _esc(text: str) -> str:
    """Make a label safe inside a Mermaid node."""
    return text.replace('"', "'").replace("\n", " ").strip()[:80]


def to_mermaid(steps: list[ProcessStep]) -> str:
    if not steps:
        return "flowchart TD\n  empty[No steps extracted]"
    ids = {s.id for s in steps}
    lines = ["flowchart TD"]
    for s in steps:
        label = f"{s.actor}: {s.action}" if s.actor else s.action
        lines.append(f'  s{s.id}["{_esc(label)}"]')
    for i, s in enumerate(steps):
        targets = [n for n in s.next if n in ids]
        if not targets and not s.next and i + 1 < len(steps):
            targets = [steps[i + 1].id]  # implicit sequential edge
        for t in targets:
            lines.append(f"  s{s.id} --> s{t}")
    return "\n".join(lines)


async def analyze_document(router: ModelRouter, document: str) -> ProcessReport:
    if not document.strip():
        raise ProcessAnalysisError("document is empty")
    out = await router.step(
        [UserMessage(content=document)],
        complexity="complex",
        system=_SYSTEM,
        max_tokens=2048,
    )
    start, end = out.text.find("{"), out.text.rfind("}")
    if start == -1 or end <= start:
        raise ProcessAnalysisError("model did not return a JSON analysis")
    try:
        data = json.loads(out.text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProcessAnalysisError(f"unparseable analysis: {exc}") from exc

    report = ProcessReport(
        entities=[Entity(**e) for e in data.get("entities", [])],
        steps=[ProcessStep(**s) for s in data.get("steps", [])],
        contradictions=[str(c) for c in data.get("contradictions", [])],
        backlog=[BacklogItem(**b) for b in data.get("backlog", [])],
        provider=out.provider,
        model=out.model,
        cost_usd=out.cost_usd,
    )
    report.mermaid = to_mermaid(report.steps)
    return report
