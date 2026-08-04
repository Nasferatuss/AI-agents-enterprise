"""Unified async LLM clients: native Anthropic SDK + OpenAI-compatible HTTP.

Anthropic goes through the official SDK (retries, typed errors, adaptive
thinking, native tool use). Everything else — OpenAI, DeepSeek, Kimi, Ollama,
Mimo — speaks the OpenAI-compatible /chat/completions protocol (function
calling) over a shared httpx client. Both sides consume the provider-agnostic
Transcript and return a normalized StepOutput.
"""

import asyncio
import json

import anthropic
import httpx

from workbench_runtime._util import extract_json
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
from workbench_shared.config import get_settings

_TIMEOUT_S = 120.0

# A dead local box should fail fast so fallback kicks in; we cap how long we wait
# to *establish* the connection while still allowing a long read for slow models.
_LOCAL_CONNECT_TIMEOUT_S = 2.0

# Transient-overload statuses worth a short retry before falling to next provider.
_RETRYABLE_STATUSES = (429, 503)
_MAX_RETRIES = 2  # → up to 3 attempts total
_BACKOFF_BASE_S = 0.5

# Models with adaptive thinking support; enabled for complex/judge calls
_ADAPTIVE_THINKING_PREFIXES = ("claude-opus-4", "claude-sonnet-4-6", "claude-fable")

# Ollama serves a reasoning model's chain of thought in a non-standard "reasoning"
# field and leaves "content" empty. Under a small max_tokens the whole budget can
# go to thinking: the caller then gets an empty string, not an error, and reports
# an unexplainable parse failure. This asks the server to answer without thinking.
# Local providers only — hosted APIs reject the value.
_NO_THINKING = {"reasoning_effort": "none"}
_REASONING_FIELDS = ("reasoning", "reasoning_content")


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
    rendered = len(messages)
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
    if transcript and len(messages) == rendered:
        # Items were given but none rendered → they aren't Transcript types (e.g. a
        # ChatMessage passed straight to step()). Fail loudly: an empty user turn
        # makes OpenAI-compatible models answer from the system prompt alone.
        raise ValueError(
            f"transcript produced no messages; got item types "
            f"{[type(i).__name__ for i in transcript]} (expected UserMessage/"
            f"AssistantMessage/ToolResultMessage)"
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

    # Local box: short connect timeout so an offline 4090 fails fast → fallback,
    # while the read budget is settable (WB_LOCAL_READ_TIMEOUT_S) because a cold or
    # large local model needs longer than a hosted API does. API providers keep the
    # full single-value timeout.
    timeout: httpx.Timeout | float
    if provider.api_key_env == "":
        read = get_settings().local_read_timeout_s
        timeout = httpx.Timeout(connect=_LOCAL_CONNECT_TIMEOUT_S, read=read, write=read, pool=read)
    else:
        timeout = _TIMEOUT_S

    async def post(body: dict) -> httpx.Response:
        resp: httpx.Response | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await http.post(
                    f"{provider.base_url}/chat/completions",
                    json=body,
                    headers=headers,
                    timeout=timeout,
                )
            except httpx.HTTPError as exc:
                raise ProviderCallError(provider.name, model, f"transport: {exc}") from exc
            # Transient overload (429/503): back off and retry this provider before
            # giving up on it and falling to the next. (Anthropic SDK retries itself.)
            if resp.status_code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                continue
            break

        if resp is None:  # unreachable in practice, but `assert` is stripped under `python -O`
            raise ProviderCallError(provider.name, model, "no response produced")
        if resp.status_code != 200:
            raise ProviderCallError(
                provider.name, model, f"HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp

    def unwrap(resp: httpx.Response) -> tuple[dict, dict]:
        data = resp.json()
        try:
            return data, data["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise ProviderCallError(provider.name, model, f"malformed response: {exc}") from exc

    resp = await post(payload)
    data, message = unwrap(resp)

    # A reasoning model that spent the whole budget thinking (see _NO_THINKING):
    # retry once without thinking rather than hand the caller an empty string.
    thought_only = (
        not (message.get("content") or "").strip()
        and not message.get("tool_calls")
        and any(message.get(field) for field in _REASONING_FIELDS)
    )
    if thought_only and provider.api_key_env == "":
        data, message = unwrap(await post({**payload, **_NO_THINKING}))
        if not (message.get("content") or "").strip() and not message.get("tool_calls"):
            raise ProviderCallError(
                provider.name,
                model,
                f"only chain-of-thought returned; raise max_tokens (now {max_tokens}) "
                "or serve a non-reasoning model",
            )

    tool_calls = []
    for raw in message.get("tool_calls") or []:
        try:
            parsed = extract_json(raw["function"]["arguments"] or "{}")
        except KeyError:
            parsed = None
        arguments = parsed if isinstance(parsed, dict) else {}
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
    # Each transcript item becomes a (role, content-blocks) pair; consecutive
    # items of the same role are merged into ONE message. This matters for
    # parallel tool calls: several ToolResultMessages in a row must land in a
    # single user message with multiple tool_result blocks — Anthropic rejects
    # consecutive same-role messages, and the tool_result(s) for a tool_use must
    # appear in the immediately following message.
    messages: list[dict] = []

    def emit(role: str, blocks: list[dict]) -> None:
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": blocks})

    for item in transcript:
        match item:
            case UserMessage():
                emit("user", [{"type": "text", "text": item.content}])
            case AssistantMessage():
                blocks: list[dict] = []
                if item.content:
                    blocks.append({"type": "text", "text": item.content})
                blocks += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                    for c in item.tool_calls
                ]
                emit("assistant", blocks)
            case ToolResultMessage():
                emit(
                    "user",
                    [
                        {
                            "type": "tool_result",
                            "tool_use_id": item.tool_call_id,
                            "content": item.content,
                            "is_error": item.is_error,
                        }
                    ],
                )
    if transcript and not messages:
        # See to_openai_messages: Anthropic rejects an empty messages array outright
        # (400 "at least one message is required"). Surface the real cause instead.
        raise ValueError(
            f"transcript produced no messages; got item types "
            f"{[type(i).__name__ for i in transcript]} (expected UserMessage/"
            f"AssistantMessage/ToolResultMessage)"
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
