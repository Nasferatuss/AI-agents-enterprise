"""Unified async LLM clients: native Anthropic SDK + OpenAI-compatible HTTP.

Anthropic goes through the official SDK (retries, typed errors, adaptive
thinking, native tool use). Everything else — OpenAI, DeepSeek, Kimi, Ollama,
Mimo — speaks the OpenAI-compatible /chat/completions protocol (function
calling) over a shared httpx client. Both sides consume the provider-agnostic
Transcript and return a normalized StepOutput.
"""

import json

import anthropic
import httpx

from workbench_runtime.providers import Provider
from workbench_runtime.tools import Tool
from workbench_runtime.types import (
    AssistantMessage,
    StepOutput,
    ToolCall,
    ToolResultMessage,
    Transcript,
    Usage,
    UserMessage,
)

_TIMEOUT_S = 120.0

# Models with adaptive thinking support; enabled for complex/judge calls
_ADAPTIVE_THINKING_PREFIXES = ("claude-opus-4", "claude-sonnet-4-6", "claude-fable")


class ProviderCallError(Exception):
    """A provider failed in a way that justifies falling back to the next one."""

    def __init__(self, provider: str, model: str, reason: str):
        self.provider, self.model, self.reason = provider, model, reason
        super().__init__(f"{provider}/{model}: {reason}")


# --- OpenAI-compatible rendering/parsing ---


def to_openai_messages(transcript: Transcript, system: str | None) -> list[dict]:
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    for item in transcript:
        match item:
            case UserMessage():
                messages.append({"role": "user", "content": item.content})
            case AssistantMessage():
                msg: dict = {"role": "assistant", "content": item.content or None}
                if item.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for c in item.tool_calls
                    ]
                messages.append(msg)
            case ToolResultMessage():
                messages.append(
                    {"role": "tool", "tool_call_id": item.tool_call_id, "content": item.content}
                )
    return messages


def to_openai_tools(tools: list[Tool]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


async def step_openai_compatible(
    http: httpx.AsyncClient,
    provider: Provider,
    model: str,
    transcript: Transcript,
    tools: list[Tool],
    system: str | None,
    max_tokens: int,
) -> StepOutput:
    payload: dict = {
        "model": model,
        "messages": to_openai_messages(transcript, system),
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = to_openai_tools(tools)

    headers = {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    try:
        resp = await http.post(
            f"{provider.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise ProviderCallError(provider.name, model, f"transport: {exc}") from exc
    if resp.status_code != 200:
        raise ProviderCallError(provider.name, model, f"HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise ProviderCallError(provider.name, model, f"malformed response: {exc}") from exc

    tool_calls = []
    for raw in message.get("tool_calls") or []:
        try:
            arguments = json.loads(raw["function"]["arguments"] or "{}")
        except (json.JSONDecodeError, KeyError):
            arguments = {}
        tool_calls.append(
            ToolCall(id=raw.get("id", ""), name=raw["function"]["name"], arguments=arguments)
        )

    usage = data.get("usage") or {}
    return StepOutput(
        text=message.get("content") or "",
        tool_calls=tool_calls,
        usage=Usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        ),
    )


# --- Anthropic rendering/parsing ---


def to_anthropic_messages(transcript: Transcript) -> list[dict]:
    messages: list[dict] = []
    for item in transcript:
        match item:
            case UserMessage():
                messages.append({"role": "user", "content": item.content})
            case AssistantMessage():
                blocks: list[dict] = []
                if item.content:
                    blocks.append({"type": "text", "text": item.content})
                blocks += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                    for c in item.tool_calls
                ]
                messages.append({"role": "assistant", "content": blocks})
            case ToolResultMessage():
                # Consecutive same-role messages are merged by the API
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": item.tool_call_id,
                                "content": item.content,
                                "is_error": item.is_error,
                            }
                        ],
                    }
                )
    return messages


def to_anthropic_tools(tools: list[Tool]) -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in tools
    ]


async def step_anthropic(
    client: anthropic.AsyncAnthropic,
    provider: Provider,
    model: str,
    transcript: Transcript,
    tools: list[Tool],
    system: str | None,
    max_tokens: int,
    use_thinking: bool,
) -> StepOutput:
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": to_anthropic_messages(transcript),
    }
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = to_anthropic_tools(tools)
    if use_thinking and model.startswith(_ADAPTIVE_THINKING_PREFIXES):
        kwargs["thinking"] = {"type": "adaptive"}

    try:
        resp = await client.messages.create(**kwargs)
    except anthropic.APIError as exc:
        raise ProviderCallError(provider.name, model, f"{type(exc).__name__}: {exc}") from exc

    text = "".join(b.text for b in resp.content if b.type == "text")
    tool_calls = [
        ToolCall(id=b.id, name=b.name, arguments=dict(b.input or {}))
        for b in resp.content
        if b.type == "tool_use"
    ]
    return StepOutput(
        text=text,
        tool_calls=tool_calls,
        usage=Usage(
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        ),
    )
