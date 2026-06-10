"""Cross-provider request/response types for the model router and agent loop."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

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

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class Completion(BaseModel):
    text: str
    provider: str
    model: str
    usage: Usage
    cost_usd: float | None  # None when the model has no known price entry
    latency_ms: int
    complexity: Complexity
    attempts: list[str] = []  # "provider/model" candidates tried before success


# --- Provider-agnostic transcript (agent loop) ---
# Tool-call ids live in our transcript and are rendered into each provider's wire
# format, so the loop can even switch providers mid-run on fallback.


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str = ""
    tool_calls: list[ToolCall] = []


class ToolResultMessage(BaseModel):
    role: Literal["tool"] = "tool"
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


TranscriptItem = Annotated[
    UserMessage | AssistantMessage | ToolResultMessage, Field(discriminator="role")
]
Transcript = list[UserMessage | AssistantMessage | ToolResultMessage]


class StepOutput(BaseModel):
    """One model turn inside the agent loop."""

    text: str
    tool_calls: list[ToolCall] = []
    provider: str = ""
    model: str = ""
    usage: Usage = Usage()
    cost_usd: float | None = None
    latency_ms: int = 0
    attempts: list[str] = []


class ToolExecution(BaseModel):
    tool_call_id: str
    name: str
    arguments: dict
    result: str
    is_error: bool


class AgentStep(BaseModel):
    output: StepOutput
    tool_executions: list[ToolExecution] = []


class AgentRun(BaseModel):
    agent: str
    status: Literal["completed", "max_steps_reached"]
    final_text: str
    steps: list[AgentStep]
    usage: Usage
    cost_usd: float | None
