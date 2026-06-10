"""Price table for cost telemetry, USD per 1M tokens (input, output).

Anthropic prices verified 2026-06 (platform.claude.com). Third-party prices are
approximations for telemetry only — verify before relying on them for billing.
Unknown models yield cost None, never a guessed number.
"""

PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    # Anthropic (verified)
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # OpenAI (approximate)
    "gpt-5.1": (1.25, 10.00),
    # DeepSeek (approximate)
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    # Moonshot / Kimi (approximate)
    "kimi-k2-0905-preview": (0.60, 2.50),
}

_LOCAL_PREFIXES = ("qwen", "llama", "mistral", "gemma", "phi")


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    if model in PRICES_PER_MTOK:
        in_price, out_price = PRICES_PER_MTOK[model]
        return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    if model.lower().startswith(_LOCAL_PREFIXES):
        return 0.0  # local GPU inference
    return None
