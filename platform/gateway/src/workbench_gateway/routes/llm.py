"""Model-router endpoints: provider registry introspection and routed chat."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from workbench_runtime import ChatMessage, Completion, Complexity, get_router
from workbench_runtime.router import NoProviderAvailableError

router = APIRouter(prefix="/v1", tags=["llm"])

# /v1/chat is the gateway's only open-ended text input forwarded to a paid provider —
# bound it at the boundary (the core ChatMessage type stays uncapped for internal use
# like long tool results / compaction). ~256k chars ≈ a large but finite transcript.
_MAX_CHAT_CHARS = 256_000


class ProviderInfo(BaseModel):
    name: str
    kind: str
    enabled: bool
    models: dict[str, str]


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    complexity: Complexity = "standard"
    system: str | None = Field(default=None, max_length=16_000)
    max_tokens: int = Field(default=1024, ge=1, le=64000)

    @field_validator("messages")
    @classmethod
    def _bound_total_size(cls, messages: list[ChatMessage]) -> list[ChatMessage]:
        if sum(len(m.content) for m in messages) > _MAX_CHAT_CHARS:
            raise ValueError(f"total message content exceeds {_MAX_CHAT_CHARS} chars")
        return messages


@router.get("/models", response_model=list[ProviderInfo])
async def list_models() -> list[ProviderInfo]:
    return [
        ProviderInfo(name=p.name, kind=p.kind, enabled=p.enabled, models=p.models)
        for p in get_router().registry.values()
    ]


@router.post("/chat", response_model=Completion)
async def chat(req: ChatRequest) -> Completion:
    try:
        return await get_router().complete(
            messages=req.messages,
            complexity=req.complexity,
            system=req.system,
            max_tokens=req.max_tokens,
        )
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
