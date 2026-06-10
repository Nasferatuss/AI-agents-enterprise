"""Unified async LLM clients: native Anthropic SDK + OpenAI-compatible HTTP.

Anthropic goes through the official SDK (retries, typed errors, adaptive
thinking). Everything else — OpenAI, DeepSeek, Kimi, Ollama, Mimo — speaks the
OpenAI-compatible /chat/completions protocol over a shared httpx client.
"""

import anthropic
import httpx

from workbench_runtime.providers import Provider
from workbench_runtime.types import ChatMessage, Usage

_TIMEOUT_S = 120.0

# Models with adaptive thinking support; enabled for complex/judge calls
_ADAPTIVE_THINKING_PREFIXES = ("claude-opus-4", "claude-sonnet-4-6", "claude-fable")


class ProviderCallError(Exception):
    """A provider failed in a way that justifies falling back to the next one."""

    def __init__(self, provider: str, model: str, reason: str):
        self.provider, self.model, self.reason = provider, model, reason
        super().__init__(f"{provider}/{model}: {reason}")


async def complete_openai_compatible(
    http: httpx.AsyncClient,
    provider: Provider,
    model: str,
    messages: list[ChatMessage],
    system: str | None,
    max_tokens: int,
) -> tuple[str, Usage]:
    payload_messages: list[dict[str, str]] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages += [m.model_dump() for m in messages]

    headers = {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    try:
        resp = await http.post(
            f"{provider.base_url}/chat/completions",
            json={"model": model, "messages": payload_messages, "max_tokens": max_tokens},
            headers=headers,
            timeout=_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise ProviderCallError(provider.name, model, f"transport: {exc}") from exc
    if resp.status_code != 200:
        raise ProviderCallError(provider.name, model, f"HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise ProviderCallError(provider.name, model, f"malformed response: {exc}") from exc
    usage = data.get("usage") or {}
    return text, Usage(
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
    )


async def complete_anthropic(
    client: anthropic.AsyncAnthropic,
    provider: Provider,
    model: str,
    messages: list[ChatMessage],
    system: str | None,
    max_tokens: int,
    use_thinking: bool,
) -> tuple[str, Usage]:
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [m.model_dump() for m in messages],
    }
    if system:
        kwargs["system"] = system
    if use_thinking and model.startswith(_ADAPTIVE_THINKING_PREFIXES):
        kwargs["thinking"] = {"type": "adaptive"}

    try:
        resp = await client.messages.create(**kwargs)
    except anthropic.APIError as exc:
        raise ProviderCallError(provider.name, model, f"{type(exc).__name__}: {exc}") from exc

    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, Usage(
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
    )
