"""Model-router endpoints: provider registry introspection and routed chat."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from workbench_runtime import ChatMessage, Completion, Complexity, get_router
from workbench_runtime.router import NoProviderAvailableError

router = APIRouter(prefix="/v1", tags=["llm"])


class ProviderInfo(BaseModel):
    name: str
    kind: str
    enabled: bool
    models: dict[str, str]


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    complexity: Complexity = "standard"
    system: str | None = None
    max_tokens: int = Field(default=1024, ge=1, le=64000)


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
