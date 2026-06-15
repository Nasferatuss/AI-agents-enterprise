"""Autonomous Agent engine: plan → act (tools) → reflect → repeat (flagship).

Unlike a single tool-calling pass, this drives a real outer loop. Each iteration:
  1. PLAN    — one complex LLM call decomposes the goal (or the current focus)
               into an ordered list of concrete steps.
  2. ACT     — the runtime's tool-calling agent loop (`run_agent`) executes the
               plan with a safe, network-free toolset, fed the accumulated MEMORY
               so far. New facts/results are appended to MEMORY.
  3. REFLECT — one complex LLM call judges progress against the goal and returns
               {"goal_met", "missing", "next_focus"}.
  4. REPEAT  — if the goal is not met and the iteration cap is not reached, loop
               back focused on `next_focus`, accumulating MEMORY across rounds.

Stops when `goal_met` is true or after `max_iterations` (cap ~3-4). LLM JSON is
parsed defensively: prose-wrapped JSON is extracted; on failure the engine
degrades (goal as a single-step plan / stop reflecting) rather than crashing.
"""

import json

from pydantic import BaseModel, Field

from workbench_runtime.agent import Agent, run_agent
from workbench_runtime.demo import (
    CalculatorInput,
    UtcNowInput,
    calculator,
    utc_now,
)
from workbench_runtime.router import ModelRouter
from workbench_runtime.tools import Tool
from workbench_runtime.types import UserMessage

_DEFAULT_MAX_ITERATIONS = 3
_MAX_PLAN_STEPS = 6

_PLAN_SYSTEM = (
    "You are an autonomous planner. Decompose the goal into an ordered list of "
    "concrete, actionable steps. Keep it short (<= 6 steps). Respond with ONLY "
    'JSON: {"steps": ["...", "..."]}'
)
_REFLECT_SYSTEM = (
    "You are a strict progress judge. Given the goal and what the agent has done "
    "so far, decide whether the goal is fully met. Respond with ONLY JSON: "
    '{"goal_met": true|false, "missing": "what is still missing (empty if met)", '
    '"next_focus": "what to focus on next (empty if met)"}'
)
_ACT_INSTRUCTIONS = (
    "You are an autonomous execution agent working toward a goal. Use the "
    "calculator tool for any arithmetic and utc_now for the current time instead "
    "of guessing. Use the remember tool to record any durable fact or result you "
    "discover. Work through the given plan and report concrete results."
)


# --- API response models ---


class Plan(BaseModel):
    steps: list[str]


class Reflection(BaseModel):
    goal_met: bool
    missing: str = ""
    next_focus: str = ""


class Iteration(BaseModel):
    plan: Plan
    actions: str  # the acting agent's final answer for this round
    reflection: Reflection


class AutonomousResult(BaseModel):
    goal: str
    iterations: list[Iteration]
    memory: list[str]
    final_answer: str
    completed: bool
    cost_usd: float | None = None


# --- JSON parsing helpers (models may wrap JSON in prose) ---


def _extract_json(text: str, opener: str, closer: str) -> dict | list | None:
    start, end = text.find(opener), text.rfind(closer)
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _parse_plan(text: str, goal: str) -> Plan:
    data = _extract_json(text, "{", "}")
    if isinstance(data, dict):
        steps = [str(s).strip() for s in data.get("steps", []) if str(s).strip()]
        if steps:
            return Plan(steps=steps[:_MAX_PLAN_STEPS])
    # Degrade: treat the goal as a single-step plan.
    return Plan(steps=[goal])


def _parse_reflection(text: str) -> Reflection:
    data = _extract_json(text, "{", "}")
    if isinstance(data, dict) and "goal_met" in data:
        return Reflection(
            goal_met=bool(data.get("goal_met")),
            missing=str(data.get("missing", "")),
            next_focus=str(data.get("next_focus", "")),
        )
    # Degrade: cannot judge → assume done so the loop stops cleanly.
    return Reflection(goal_met=True, missing="", next_focus="")


def _add_cost(total: float | None, part: float | None) -> float | None:
    return None if (total is None or part is None) else total + part


# --- Acting agent (safe, network-free toolset) ---


class RememberInput(BaseModel):
    note: str = Field(description="A fact or result worth remembering, one sentence.")


def _build_act_agent(memory: list[str]) -> Agent:
    """An agent whose `remember` tool appends durable facts into shared MEMORY."""

    def remember(inp: RememberInput) -> str:
        note = inp.note.strip()
        if note and note not in memory:
            memory.append(note)
        return f"remembered: {note}"

    return Agent(
        name="autonomous-actor",
        instructions=_ACT_INSTRUCTIONS,
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
            Tool(
                name="remember",
                description="Record a durable fact or result into the scratchpad "
                "memory so it is available in later steps.",
                input_model=RememberInput,
                handler=remember,
            ),
        ],
        complexity="standard",
    )


# --- Engine ---


async def _plan(router: ModelRouter, goal: str, focus: str | None) -> tuple[Plan, float | None]:
    prompt = f"Goal: {goal}"
    if focus:
        prompt += f"\n\nFocus this plan on what is still missing: {focus}"
    out = await router.step(
        [UserMessage(content=prompt)],
        complexity="complex",
        system=_PLAN_SYSTEM,
        max_tokens=512,
    )
    return _parse_plan(out.text, goal), out.cost_usd


async def _reflect(
    router: ModelRouter, goal: str, memory: list[str], last_actions: str
) -> tuple[Reflection, float | None]:
    mem = "\n".join(f"- {m}" for m in memory) or "(empty)"
    prompt = (
        f"Goal: {goal}\n\nScratchpad memory so far:\n{mem}\n\n"
        f"Most recent actions/result:\n{last_actions}"
    )
    out = await router.step(
        [UserMessage(content=prompt)],
        complexity="complex",
        system=_REFLECT_SYSTEM,
        max_tokens=512,
    )
    return _parse_reflection(out.text), out.cost_usd


async def run_autonomous(
    router: ModelRouter,
    goal: str,
    *,
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
) -> AutonomousResult:
    memory: list[str] = []
    iterations: list[Iteration] = []
    cost: float | None = 0.0
    focus: str | None = None
    final_answer = ""
    completed = False

    for _ in range(max_iterations):
        # 1. PLAN
        plan, plan_cost = await _plan(router, goal, focus)
        cost = _add_cost(cost, plan_cost)

        # 2. ACT — run the tool-calling loop with accumulated memory in context.
        agent = _build_act_agent(memory)
        act_input = (
            f"Goal: {goal}\n\nPlan for this round:\n"
            + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(plan.steps))
            + "\n\nExecute the plan and report concrete results."
        )
        run = await run_agent(agent, act_input, router=router, memory=memory or None)
        cost = _add_cost(cost, run.cost_usd)
        final_answer = run.final_text or final_answer
        if run.final_text:
            memory.append(f"Round result: {run.final_text}")

        # 3. REFLECT
        reflection, reflect_cost = await _reflect(router, goal, memory, run.final_text)
        cost = _add_cost(cost, reflect_cost)

        iterations.append(Iteration(plan=plan, actions=run.final_text, reflection=reflection))

        # 4. REPEAT?
        if reflection.goal_met:
            completed = True
            break
        focus = reflection.next_focus or reflection.missing or None

    return AutonomousResult(
        goal=goal,
        iterations=iterations,
        memory=memory,
        final_answer=final_answer,
        completed=completed,
        cost_usd=cost,
    )
