"""Small shared helpers used across the runtime package.

Kept in one place so the cost-accumulation and JSON-parsing logic don't drift
between clients.py / router.py / agent.py / tracing.py (code-review: duplicated
`_add_cost` / `_extract_json`).
"""

import json


def add_cost(total: float | None, delta: float | None) -> float | None:
    """Accumulate optional USD costs. None is contagious: if either the running
    total or the new delta has an unknown price, the sum is unknown (None)."""
    if total is None or delta is None:
        return None
    return total + delta


def extract_json(text: str | None) -> object | None:
    """Best-effort JSON parse. Returns the parsed value, or None when `text` is
    not a string or not valid JSON. Never raises."""
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
