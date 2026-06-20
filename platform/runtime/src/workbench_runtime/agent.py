"""Agent contract and the manual agentic loop (Sprint 1 + Context Engine 1.1).

The loop: build context → model turn → execute requested tools → feed results
back → repeat, until the model answers without tool calls or max_steps is hit.
Between steps the Context Engine compacts the transcript when it outgrows the
budget. Every step is recorded into AgentRun — the seed of the trace schema
(ADR-006): tool args, results, per-step usage/cost and the context actually
used are never thrown away.
"""

from dataclasses import dataclass, field

from workbench_runtime._util import add_cost
from workbench_runtime.context import ContextEngine, ContextPolicy
from workbench_runtime.router import ModelRouter, get_router
from workbench_runtime.tools import Tool, execute_tool
from workbench_runtime.types import (
    AgentRun,
    AgentStep,
    AssistantMessage,
    Complexity,
    RunContext,
    ToolExecution,
    ToolResultMessage,
    Transcript,
    Usage,
    UserMessage,
)
from workbench_shared.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Agent:
    name: str
    instructions: str
    tools: list[Tool] = field(default_factory=list)
    complexity: Complexity = "standard"
    max_steps: int = 8
    max_tokens: int = 2048
    context_policy: ContextPolicy = field(default_factory=ContextPolicy)

    def tool(self, name: str) -> Tool | None:
        return next((t for t in self.tools if t.name == name), None)


async def run_agent(
    agent: Agent,
    user_input: str,
    router: ModelRouter | None = None,
    memory: list[str] | None = None,
    retrieved: list[str] | None = None,
    task_state: str | None = None,
) -> AgentRun:
    router = router or get_router()
    engine = ContextEngine(router, agent.context_policy)
    bundle = engine.build(
        agent.instructions, memory=memory, retrieved=retrieved, task_state=task_state
    )
    system = bundle.render_system()
    run_context = RunContext(parts=bundle.parts)

    transcript: Transcript = [UserMessage(content=user_input)]
    steps: list[AgentStep] = []
    usage = Usage()
    cost: float | None = 0.0

    for step_index in range(agent.max_steps):
        transcript, compaction = await engine.maybe_compact(transcript, step_index)
        if compaction:
            run_context.compactions.append(compaction)
            usage = usage + compaction.usage
            cost = add_cost(cost, compaction.cost_usd)

        out = await router.step(
            transcript,
            complexity=agent.complexity,
            tools=agent.tools,
            system=system,
            max_tokens=agent.max_tokens,
        )
        usage = usage + out.usage
        cost = add_cost(cost, out.cost_usd)
        transcript.append(AssistantMessage(content=out.text, tool_calls=out.tool_calls))

        if not out.tool_calls:
            steps.append(AgentStep(output=out))
            log.info("agent run completed", agent=agent.name, steps=len(steps), cost_usd=cost)
            return AgentRun(
                agent=agent.name,
                status="completed",
                final_text=out.text,
                steps=steps,
                usage=usage,
                cost_usd=cost,
                context=run_context,
            )

        executions: list[ToolExecution] = []
        for call in out.tool_calls:
            tool = agent.tool(call.name)
            if tool is None:
                result, is_error = f"Unknown tool: {call.name}", True
            else:
                result, is_error = await execute_tool(tool, call.arguments)
            executions.append(
                ToolExecution(
                    tool_call_id=call.id,
                    name=call.name,
                    arguments=call.arguments,
                    result=result,
                    is_error=is_error,
                )
            )
            transcript.append(
                ToolResultMessage(
                    tool_call_id=call.id, name=call.name, content=result, is_error=is_error
                )
            )
        steps.append(AgentStep(output=out, tool_executions=executions))

    log.warning("agent hit max_steps", agent=agent.name, max_steps=agent.max_steps)
    return AgentRun(
        agent=agent.name,
        status="max_steps_reached",
        final_text="",
        steps=steps,
        usage=usage,
        cost_usd=cost,
        context=run_context,
    )
