"""Playwright-backed gateway + QA runner — same shape as runner.py, real browser.

`build_playwright_gateway` registers the same observe/click/type action space as
`runner.build_cua_gateway`, but the handlers are ASYNC and await a real
`PlaywrightSession`. `run_qa_playwright` reuses the GENERIC `runner._run_scenario`
and returns the same `QAReport` shape as `runner.run_qa` — so a real-browser run
reproduces the virtual run's results (3 pass, 2 fail, the two planted bugs).
"""

from __future__ import annotations

from workbench_app_cua.playwright_sandbox import PlaywrightSession
from workbench_app_cua.runner import (
    Bug,
    QAReport,
    Scenario,
    ScenarioResult,
    _run_scenario,
)
from workbench_app_cua.sandbox import Action
from workbench_toolgateway import AuditEntry, ToolGateway, ToolSpec

_ALLOWLIST = {"observe", "click", "type"}


def build_playwright_gateway(session: PlaywrightSession) -> ToolGateway:
    gw = ToolGateway()

    async def _observe(_args: dict) -> dict:
        return (await session.observe()).model_dump()

    async def _click(args: dict) -> dict:
        return (
            await session.act(Action(kind="click", target=str(args.get("target", ""))))
        ).model_dump()

    async def _type(args: dict) -> dict:
        return (
            await session.act(
                Action(
                    kind="type",
                    target=str(args.get("target", "")),
                    value=str(args.get("value", "")),
                )
            )
        ).model_dump()

    gw.register(
        ToolSpec(name="observe", description="Read the current screen.", input_schema={}),
        _observe,
    )
    gw.register(
        ToolSpec(
            name="click",
            description="Click a control by id.",
            input_schema={"type": "object", "properties": {"target": {"type": "string"}}},
        ),
        _click,
    )
    gw.register(
        ToolSpec(
            name="type",
            description="Type a value into an input by id.",
            input_schema={
                "type": "object",
                "properties": {"target": {"type": "string"}, "value": {"type": "string"}},
            },
        ),
        _type,
    )
    return gw


async def run_qa_playwright(scenarios: list[Scenario]) -> QAReport:
    all_results: list[ScenarioResult] = []
    all_bugs: list[Bug] = []
    trace: list[AuditEntry] = []
    for scenario in scenarios:
        session = await PlaywrightSession.create()  # fresh real browser per scenario
        try:
            gateway = build_playwright_gateway(session)
            result, bugs = await _run_scenario(scenario, gateway)
        finally:
            await session.close()
        all_results.append(result)
        all_bugs.extend(bugs)
        trace.extend(gateway.audit)
    passed = sum(1 for r in all_results if r.passed)
    return QAReport(
        scenarios=all_results,
        bugs=all_bugs,
        passed=passed,
        failed=len(all_results) - passed,
        action_trace=trace,
    )
