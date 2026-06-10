"""Tool contract: name + description + pydantic input model + handler.

The input schema shown to the model is derived from the pydantic model, and the
same model validates arguments before the handler runs — the handler never sees
malformed input. Tool failures are returned to the model as is_error results,
not raised: the agent should get a chance to recover.
"""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], str | Awaitable[str]]

    @property
    def input_schema(self) -> dict:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return schema


async def execute_tool(tool: Tool, arguments: dict) -> tuple[str, bool]:
    """Run a tool; returns (result, is_error). Never raises on tool failure."""
    try:
        parsed = tool.input_model.model_validate(arguments)
    except ValidationError as exc:
        return f"Invalid arguments for {tool.name}: {exc}", True
    try:
        result = tool.handler(parsed)
        if inspect.isawaitable(result):
            result = await result
        return str(result), False
    except Exception as exc:  # noqa: BLE001 — tool errors go back to the model
        return f"Tool {tool.name} failed: {type(exc).__name__}: {exc}", True
