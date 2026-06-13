from workbench_app_cua.runner import build_cua_gateway, run_qa
from workbench_app_cua.sandbox import Action, UiSession
from workbench_app_cua.scenarios import SCENARIOS

# --- sandbox state machine ---


def test_login_success_and_failure():
    s = UiSession()
    s.act(Action(kind="type", target="username", value="admin"))
    s.act(Action(kind="type", target="password", value="wrong"))
    screen = s.act(Action(kind="click", target="submit"))
    assert screen.state == "login" and screen.error == "Invalid credentials"

    s.act(Action(kind="type", target="password", value="secret"))
    screen = s.act(Action(kind="click", target="submit"))
    assert screen.state == "dashboard"


def test_screen_render_is_textual_screenshot():
    text = UiSession().observe().render()
    assert "[login]" in text and "Username" in text and "Sign in" in text


def test_planted_email_bug_accepts_invalid_email():
    s = UiSession()
    for t, v in [("username", "admin"), ("password", "secret")]:
        s.act(Action(kind="type", target=t, value=v))
    s.act(Action(kind="click", target="submit"))
    s.act(Action(kind="click", target="new_customer"))
    s.act(Action(kind="type", target="name", value="Acme"))
    s.act(Action(kind="type", target="email", value="notanemail"))
    screen = s.act(Action(kind="click", target="save"))
    # the bug: invalid email is accepted → success, no error
    assert screen.state == "success" and screen.error is None


# --- guarded gateway ---


async def test_actions_go_through_gateway_audit():
    gw = build_cua_gateway(UiSession())
    await gw.call(
        "type", {"target": "username", "value": "admin"}, allowlist={"observe", "click", "type"}
    )
    await gw.call("observe", {}, allowlist={"observe", "click", "type"})
    assert [a.tool for a in gw.audit] == ["type", "observe"]
    assert all(a.allowed for a in gw.audit)


async def test_unlisted_action_is_denied():
    gw = build_cua_gateway(UiSession())
    result = await gw.call("type", {"target": "username", "value": "x"}, allowlist={"observe"})
    assert result.allowed is False  # 'type' not permitted by this allowlist


# --- scenario runner / bug report ---


async def test_run_qa_passes_happy_paths_and_finds_two_bugs():
    report = await run_qa(SCENARIOS)
    by_name = {r.name: r for r in report.scenarios}

    assert by_name["login_valid"].passed
    assert by_name["login_invalid_recovers"].passed  # error recovery works
    assert by_name["create_customer_valid"].passed

    assert not by_name["email_validation"].passed  # BUG-1 surfaced
    assert not by_name["dashboard_copy"].passed  # BUG-2 surfaced

    assert report.passed == 3 and report.failed == 2
    bug_scenarios = {b.scenario for b in report.bugs}
    assert bug_scenarios == {"email_validation", "dashboard_copy"}
    # every action was driven through the gateway and audited
    assert len(report.action_trace) > 0
    assert all(a.allowed for a in report.action_trace)
