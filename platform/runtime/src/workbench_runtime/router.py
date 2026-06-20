"""Model router (ADR-008): complexity → ordered candidate chain with fallback.

Local-first cost policy (user preference + ADR-003): everything that a small
local model can handle goes to the 4090 box; the chain degrades gracefully to
cheap API and only reaches frontier models when the task demands it. A candidate
that is unreachable or errors is skipped; the first success wins.

step() is the primitive (one model turn, optionally with tools) used by both
the plain /v1/chat path and the agent loop. The transcript is provider-agnostic,
so fallback can switch providers even mid-agent-run.
"""

import time
from functools import lru_cache

import anthropic
import httpx

from workbench_runtime.clients import (
    ProviderCallError,
    step_anthropic,
    step_openai_compatible,
)
from workbench_runtime.pricing import estimate_cost_usd
from workbench_runtime.providers import Provider, build_registry
from workbench_runtime.tools import Tool
from workbench_runtime.types import (
    AssistantMessage,
    ChatMessage,
    Completion,
    Complexity,
    StepOutput,
    Transcript,
    UserMessage,
)
from workbench_shared.config import get_settings
from workbench_shared.logging import get_logger

log = get_logger(__name__)

Candidate = tuple[str, str]  # (provider name, model role) — resolved against the registry

# Provider health cooldown (deliberately not a full circuit breaker): after a
# provider fails with a network/timeout error we mark it unhealthy for a short
# cooldown and skip it in the chain — so a dead local box isn't retried on every
# single request. Reset on the next success; there are no closed/open/half-open
# states or a consecutive-failure threshold. Kept short; tests monkeypatch this
# to 0 to avoid flakes.
_HEALTH_COOLDOWN_S = 30.0


class NoProviderAvailableError(Exception):
    def __init__(self, complexity: Complexity, attempts: list[str]):
        self.attempts = attempts
        super().__init__(
            f"no provider succeeded for complexity={complexity}; tried: {attempts or 'none'}"
        )


class ModelRouter:
    def __init__(
        self,
        registry: dict[str, Provider] | None = None,
        http: httpx.AsyncClient | None = None,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
    ):
        self.registry = registry if registry is not None else build_registry()
        self._http = http or httpx.AsyncClient()
        self._anthropic = anthropic_client  # lazily created: needs ANTHROPIC_API_KEY
        self._unhealthy_until: dict[str, float] = {}  # provider name → monotonic deadline

    def _is_healthy(self, provider_name: str) -> bool:
        deadline = self._unhealthy_until.get(provider_name)
        return deadline is None or time.monotonic() >= deadline

    def _mark_unhealthy(self, provider_name: str) -> None:
        if _HEALTH_COOLDOWN_S > 0:
            self._unhealthy_until[provider_name] = time.monotonic() + _HEALTH_COOLDOWN_S

    def chain(self, complexity: Complexity) -> list[Candidate]:
        """Ordered (provider, model-role) candidates; disabled providers filtered out."""
        cheap: list[Candidate] = [("deepseek", "default"), ("kimi", "default")]
        frontier: list[Candidate] = [("anthropic", "default"), ("openai", "default")]
        local: list[Candidate] = [("local", "default")]

        match complexity:
            case "simple":
                chain = local + cheap + [("anthropic", "small")]
            case "standard":
                prefix = local if get_settings().route_standard_via_local else []
                chain = prefix + cheap + frontier
            case "complex" | "judge":
                chain = frontier

        return [(p, role) for p, role in chain if p in self.registry and self.registry[p].enabled]

    async def step(
        self,
        transcript: Transcript,
        complexity: Complexity = "standard",
        tools: list[Tool] | None = None,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> StepOutput:
        """One model turn with fallback across the complexity chain."""
        tools = tools or []
        attempts: list[str] = []
        chain = self.chain(complexity)
        # Prefer healthy providers, but never end up with nothing to try: if the
        # whole chain is in cooldown, fall back to the full chain (the box may be
        # back). Order within each group is preserved.
        candidates = [c for c in chain if self._is_healthy(c[0])] or chain
        for provider_name, role in candidates:
            provider = self.registry[provider_name]
            model = provider.models[role]
            started = time.monotonic()
            try:
                if provider.kind == "anthropic":
                    out = await step_anthropic(
                        self._get_anthropic(),
                        provider,
                        model,
                        transcript,
                        tools,
                        system,
                        max_tokens,
                        use_thinking=complexity in ("complex", "judge"),
                    )
                else:
                    out = await step_openai_compatible(
                        self._http, provider, model, transcript, tools, system, max_tokens
                    )
            except ProviderCallError as exc:
                attempts.append(f"{provider_name}/{model}")
                self._mark_unhealthy(provider_name)
                log.warning("provider failed, falling back", error=str(exc))
                continue

            # Success → provider is healthy again; clear any stale cooldown.
            self._unhealthy_until.pop(provider_name, None)
            out.provider = provider_name
            out.model = model
            out.latency_ms = int((time.monotonic() - started) * 1000)
            out.cost_usd = estimate_cost_usd(model, out.usage.input_tokens, out.usage.output_tokens)
            out.attempts = attempts
            log.info(
                "model step",
                provider=provider_name,
                model=model,
                complexity=complexity,
                tools=len(tools),
                tool_calls=len(out.tool_calls),
                input_tokens=out.usage.input_tokens,
                output_tokens=out.usage.output_tokens,
                cost_usd=out.cost_usd,
                latency_ms=out.latency_ms,
                fallbacks=len(attempts),
            )
            return out

        raise NoProviderAvailableError(complexity, attempts)

    async def complete(
        self,
        messages: list[ChatMessage],
        complexity: Complexity = "standard",
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> Completion:
        """Plain chat completion (no tools) — thin wrapper over step()."""
        transcript: Transcript = [
            UserMessage(content=m.content)
            if m.role == "user"
            else AssistantMessage(content=m.content)
            for m in messages
        ]
        out = await self.step(
            transcript, complexity=complexity, system=system, max_tokens=max_tokens
        )
        return Completion(
            text=out.text,
            provider=out.provider,
            model=out.model,
            usage=out.usage,
            cost_usd=out.cost_usd,
            latency_ms=out.latency_ms,
            complexity=complexity,
            attempts=out.attempts,
        )

    def _get_anthropic(self) -> anthropic.AsyncAnthropic:
        if self._anthropic is None:
            self._anthropic = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY
        return self._anthropic

    async def aclose(self) -> None:
        await self._http.aclose()


@lru_cache
def get_router() -> ModelRouter:
    return ModelRouter()
