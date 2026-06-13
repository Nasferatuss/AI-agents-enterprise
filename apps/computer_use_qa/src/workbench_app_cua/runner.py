"""Guarded action space + scenario runner → QA bug report.

The agent drives the sandbox only through the Tool Gateway (Sprint 7): observe /
click / type are the entire action space (allowlisted + audited — 'guarded'), so
there is no way to do anything the UI doesn't expose. The runner executes scripted
scenarios; a failed assertion is a found bug. This is deterministic and needs no
LLM — the optional narrative is written separately by the reviewer.
"""

from pydantic import BaseModel

from workbench_app_cua.sandbox import Action, Screen, UiSession
from workbench_toolgateway import AuditEntry, ToolGateway, ToolSpec

_ALLOWLIST = {"observe", "click", "type"}


def build_cua_gateway(session: UiSession) -> ToolGateway:
    gw = ToolGateway()
    gw.register(
        ToolSpec(name="observe", description="Read the current screen.", input_schema={}),
        lambda args: session.observe().model_dump(),
    )
    gw.register(
        ToolSpec(
            name="click",
            description="Click a control by id.",
            input_schema={"type": "object", "properties": {"target": {"type": "string"}}},
        ),
        lambda args: session.act(
            Action(kind="click", target=str(args.get("target", "")))
        ).model_dump(),
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
        lambda args: session.act(
            Action(
                kind="type", target=str(args.get("target", "")), value=str(args.get("value", ""))
            )
        ).model_dump(),
    )
    return gw


class Step(BaseModel):
    action: Action
    expect_state: str | None = None
    expect_text: str | None = None  # substring required in some element label/value
    expect_error: bool | None = None  # True: an error must be shown; False: none


class Scenario(BaseModel):
    name: str
    description: str
    steps: list[Step]


class StepResult(BaseModel):
    description: str
    passed: bool
    detail: str = ""


class Bug(BaseModel):
    scenario: str
    expected: str
    actual: str


class ScenarioResult(BaseModel):
    name: str
    description: str
    passed: bool
    steps: list[StepResult]


class QAReport(BaseModel):
    scenarios: list[ScenarioResult]
    bugs: list[Bug]
    passed: int
    failed: int
    action_trace: list[AuditEntry]
    summary: str = ""  # optional LLM narrative
    provider: str = ""
    cost_usd: float | None = None


def _screen_has_text(screen: Screen, needle: str) -> bool:
    n = needle.lower()
    return any(n in (e.label + e.value).lower() for e in screen.elements)


async def _run_scenario(
    scenario: Scenario, gateway: ToolGateway
) -> tuple[ScenarioResult, list[Bug]]:
    steps: list[StepResult] = []
    bugs: list[Bug] = []
    for step in scenario.steps:
        a = step.action
        result = await gateway.call(a.kind, a.model_dump(exclude={"kind"}), allowlist=_ALLOWLIST)
        screen = Screen(**result.output) if result.output else None

        checks: list[tuple[bool, str]] = []
        if screen is None:
            checks.append((False, f"action {a.kind} returned nothing"))
        else:
            if step.expect_state is not None:
                checks.append(
                    (
                        screen.state == step.expect_state,
                        f"state={screen.state}, expected {step.expect_state}",
                    )
                )
            if step.expect_text is not None:
                checks.append(
                    (
                        _screen_has_text(screen, step.expect_text),
                        f"text '{step.expect_text}' not found on screen",
                    )
                )
            if step.expect_error is not None:
                has_err = screen.error is not None
                checks.append(
                    (
                        has_err == step.expect_error,
                        f"error={'shown' if has_err else 'none'}, "
                        f"expected {'an error' if step.expect_error else 'no error'}",
                    )
                )

        ok = all(c for c, _ in checks)
        detail = "; ".join(msg for c, msg in checks if not c)
        steps.append(StepResult(description=_describe(step), passed=ok, detail=detail))
        if not ok:
            bugs.append(Bug(scenario=scenario.name, expected=_describe(step), actual=detail))

    return (
        ScenarioResult(
            name=scenario.name,
            description=scenario.description,
            passed=all(s.passed for s in steps),
            steps=steps,
        ),
        bugs,
    )


def _describe(step: Step) -> str:
    a = step.action
    base = (
        a.kind
        if a.kind == "observe"
        else f"{a.kind} {a.target}" + (f"='{a.value}'" if a.value else "")
    )
    exp = []
    if step.expect_state:
        exp.append(f"→ {step.expect_state}")
    if step.expect_text:
        exp.append(f"shows '{step.expect_text}'")
    if step.expect_error is True:
        exp.append("shows error")
    if step.expect_error is False:
        exp.append("no error")
    return base + (" (" + ", ".join(exp) + ")" if exp else "")


async def run_qa(scenarios: list[Scenario]) -> QAReport:
    all_results: list[ScenarioResult] = []
    all_bugs: list[Bug] = []
    trace: list[AuditEntry] = []
    for scenario in scenarios:
        gateway = build_cua_gateway(UiSession())  # fresh session per scenario
        result, bugs = await _run_scenario(scenario, gateway)
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
