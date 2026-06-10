"""Cross-provider request/response types for the model router."""

from typing import Literal

from pydantic import BaseModel

# Task complexity drives routing (ADR-008):
#   simple   — classification, extraction, short summaries → local first
#   standard — ordinary agent steps, drafting → cheap API first
#   complex  — multi-step reasoning, planning, hard synthesis → frontier
#   judge    — eval/LLM-as-judge: must be a stronger model than the one judged
Complexity = Literal["simple", "standard", "complex", "judge"]

Role = Literal["user", "assistant"]


class ChatMessage(BaseModel):
    role: Role
    content: str


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class Completion(BaseModel):
    text: str
    provider: str
    model: str
    usage: Usage
    cost_usd: float | None  # None when the model has no known price entry
    latency_ms: int
    complexity: Complexity
    attempts: list[str] = []  # "provider/model" candidates tried before success
