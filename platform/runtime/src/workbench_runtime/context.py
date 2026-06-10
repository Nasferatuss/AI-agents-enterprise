"""Context Engine v0 (Sprint 1.1, see wiki: context-engineering).

Three jobs:
1. build() — assemble the system prompt from ordered parts (instructions,
   memory, retrieved chunks, task state). Stable parts render first so the
   prefix stays cacheable; empty parts are skipped.
2. maybe_compact() — when the transcript outgrows the budget, summarize the
   older turns via the router at `simple` complexity (cheap/local model) and
   keep the recent turns verbatim. The cut never separates a tool call from
   its result.
3. Every run records the context it actually used — parts and compaction
   events land in AgentRun.context (the v0 of "сохраняет использованный
   контекст"; Postgres persistence arrives with the trace layer, Sprint 5).

Token counts are a chars/4 heuristic — good enough for budgeting; provider
tokenizers can replace it later without changing the interface.

v0 lives inside workbench-runtime to avoid a circular dependency on the
transcript types; it graduates to platform/context when RAG and persistent
memory land.
"""

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

from workbench_runtime.types import (
    AssistantMessage,
    CompactionEvent,
    ContextPart,
    ToolResultMessage,
    Transcript,
    UserMessage,
)
from workbench_shared.logging import get_logger

if TYPE_CHECKING:
    from workbench_runtime.router import ModelRouter

log = get_logger(__name__)

_CHARS_PER_TOKEN = 4
_PER_ITEM_OVERHEAD = 4

_SUMMARY_SYSTEM = (
    "You compress agent conversation history. Produce a dense summary that "
    "preserves: the user's goal, decisions made, tool calls with their key "
    "results, and any constraints or open questions. Plain text, no preamble."
)
_SUMMARY_MARKER = "[conversation summary — earlier turns compacted]"


class ContextPolicy(BaseModel):
    max_context_tokens: int = 16000  # keep modest: local models often run with small num_ctx
    compact_trigger_ratio: float = 0.8
    keep_recent_items: int = 8
    summary_max_tokens: int = 512


class ContextBundle(BaseModel):
    parts: list[ContextPart]

    def render_system(self) -> str:
        sections = [f"<{p.name}>\n{p.content}\n</{p.name}>" for p in self.parts if p.content]
        return "\n\n".join(sections)


def estimate_tokens(transcript: Transcript) -> int:
    total = 0
    for item in transcript:
        total += _PER_ITEM_OVERHEAD
        match item:
            case UserMessage() | ToolResultMessage():
                total += len(item.content) // _CHARS_PER_TOKEN
            case AssistantMessage():
                total += len(item.content) // _CHARS_PER_TOKEN
                for call in item.tool_calls:
                    total += len(call.name + json.dumps(call.arguments)) // _CHARS_PER_TOKEN
    return total


def render_transcript(transcript: Transcript) -> str:
    lines: list[str] = []
    for item in transcript:
        match item:
            case UserMessage():
                lines.append(f"user: {item.content}")
            case AssistantMessage():
                if item.content:
                    lines.append(f"assistant: {item.content}")
                for call in item.tool_calls:
                    lines.append(f"assistant → tool {call.name}({json.dumps(call.arguments)})")
            case ToolResultMessage():
                status = "error" if item.is_error else "ok"
                lines.append(f"tool {item.name} [{status}]: {item.content}")
    return "\n".join(lines)


def choose_cut(transcript: Transcript, keep_recent_items: int) -> int:
    """Index where 'recent' starts; never lands on a ToolResultMessage so a
    tool call is never separated from its results."""
    cut = max(len(transcript) - keep_recent_items, 0)
    while cut < len(transcript) and isinstance(transcript[cut], ToolResultMessage):
        cut += 1
    return cut


class ContextEngine:
    def __init__(self, router: "ModelRouter", policy: ContextPolicy | None = None):
        self.router = router
        self.policy = policy or ContextPolicy()

    def build(
        self,
        instructions: str,
        memory: list[str] | None = None,
        retrieved: list[str] | None = None,
        task_state: str | None = None,
    ) -> ContextBundle:
        parts = [ContextPart(name="instructions", content=instructions)]
        if memory:
            parts.append(ContextPart(name="memory", content="\n".join(memory)))
        if retrieved:
            parts.append(ContextPart(name="retrieved_context", content="\n\n".join(retrieved)))
        if task_state:
            parts.append(ContextPart(name="task_state", content=task_state))
        return ContextBundle(parts=parts)

    def should_compact(self, transcript: Transcript) -> bool:
        trigger = self.policy.max_context_tokens * self.policy.compact_trigger_ratio
        return estimate_tokens(transcript) >= trigger

    async def maybe_compact(
        self, transcript: Transcript, step: int
    ) -> tuple[Transcript, CompactionEvent | None]:
        if not self.should_compact(transcript):
            return transcript, None
        cut = choose_cut(transcript, self.policy.keep_recent_items)
        if cut < 2:  # nothing meaningful to fold
            return transcript, None

        old, recent = transcript[:cut], transcript[cut:]
        tokens_before = estimate_tokens(transcript)
        out = await self.router.step(
            [UserMessage(content=render_transcript(old))],
            complexity="simple",
            system=_SUMMARY_SYSTEM,
            max_tokens=self.policy.summary_max_tokens,
        )
        compacted: Transcript = [
            UserMessage(content=f"{_SUMMARY_MARKER}\n{out.text}"),
            *recent,
        ]
        event = CompactionEvent(
            step=step,
            tokens_before=tokens_before,
            tokens_after=estimate_tokens(compacted),
            summarized_items=len(old),
            usage=out.usage,
            cost_usd=out.cost_usd,
        )
        log.info(
            "context compacted",
            step=step,
            tokens_before=event.tokens_before,
            tokens_after=event.tokens_after,
            summarized_items=event.summarized_items,
            summarizer=f"{out.provider}/{out.model}",
        )
        return compacted, event
