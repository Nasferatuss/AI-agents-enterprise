"""Demo agent: smallest end-to-end proof of the runtime (loop + tools + routing).

Real business agents live in apps/ (Sprints 2+); this one exists so the platform
can be exercised via POST /v1/agents/demo/run without any app installed.
"""

import ast
import datetime
import operator

from pydantic import BaseModel, Field

from workbench_runtime.agent import Agent
from workbench_runtime.tools import Tool

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.expr) -> float:
    match node:
        case ast.Constant(value=int() | float() as v):
            return v
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _OPS:
            return _OPS[type(op)](_safe_eval(left), _safe_eval(right))
        case ast.UnaryOp(op=op, operand=operand) if type(op) in _OPS:
            return _OPS[type(op)](_safe_eval(operand))
        case _:
            raise ValueError(f"unsupported expression: {ast.dump(node)}")


class CalculatorInput(BaseModel):
    expression: str = Field(description="Arithmetic expression, e.g. '2 * (3 + 4) / 5'")


def calculator(inp: CalculatorInput) -> str:
    tree = ast.parse(inp.expression, mode="eval")
    return str(_safe_eval(tree.body))


class UtcNowInput(BaseModel):
    pass


def utc_now(_: UtcNowInput) -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


DEMO_AGENT = Agent(
    name="demo",
    instructions=(
        "You are the Workbench demo agent. Use the calculator tool for any "
        "arithmetic instead of computing yourself, and utc_now for the current "
        "time. Answer concisely."
    ),
    tools=[
        Tool(
            name="calculator",
            description="Evaluate an arithmetic expression (+, -, *, /, **, %). "
            "Use for any calculation.",
            input_model=CalculatorInput,
            handler=calculator,
        ),
        Tool(
            name="utc_now",
            description="Get the current UTC date and time.",
            input_model=UtcNowInput,
            handler=utc_now,
        ),
    ],
    complexity="standard",
)

AGENTS: dict[str, Agent] = {DEMO_AGENT.name: DEMO_AGENT}
