"""Built-in QA scenarios for the legacy CRM sandbox.

Three pass (happy path + error recovery) and two fail by design — surfacing the
planted bugs (no email validation; misspelled dashboard greeting).
"""

from workbench_app_cua.runner import Scenario, Step
from workbench_app_cua.sandbox import Action


def _login(user: str, pw: str) -> list[Step]:
    return [
        Step(action=Action(kind="type", target="username", value=user)),
        Step(action=Action(kind="type", target="password", value=pw)),
        Step(action=Action(kind="click", target="submit")),
    ]


SCENARIOS: list[Scenario] = [
    Scenario(
        name="login_valid",
        description="Sign in with valid credentials reaches the dashboard.",
        steps=[
            *_login("admin", "secret"),
            Step(action=Action(kind="observe"), expect_state="dashboard"),
        ],
    ),
    Scenario(
        name="login_invalid_recovers",
        description="Wrong password is rejected with an error (error recovery).",
        steps=[
            *_login("admin", "wrong"),
            Step(action=Action(kind="observe"), expect_state="login", expect_error=True),
        ],
    ),
    Scenario(
        name="create_customer_valid",
        description="A customer with a valid email saves successfully.",
        steps=[
            *_login("admin", "secret"),
            Step(action=Action(kind="click", target="new_customer")),
            Step(action=Action(kind="type", target="name", value="Acme Corp")),
            Step(action=Action(kind="type", target="email", value="ops@acme.com")),
            Step(action=Action(kind="click", target="save"), expect_state="success"),
        ],
    ),
    Scenario(
        name="email_validation",
        description="An invalid email (no @) should be rejected at save.",
        steps=[
            *_login("admin", "secret"),
            Step(action=Action(kind="click", target="new_customer")),
            Step(action=Action(kind="type", target="name", value="Acme Corp")),
            Step(action=Action(kind="type", target="email", value="notanemail")),
            # expect an error — the sandbox accepts it (BUG-1), so this fails.
            Step(action=Action(kind="click", target="save"), expect_error=True),
        ],
    ),
    Scenario(
        name="dashboard_copy",
        description="The dashboard greeting should be spelled 'Welcome'.",
        steps=[
            *_login("admin", "secret"),
            # expects 'Welcome' — the sandbox says 'Welcom' (BUG-2), so this fails.
            Step(action=Action(kind="observe"), expect_text="Welcome"),
        ],
    ),
]


def scenario_names() -> list[str]:
    return [s.name for s in SCENARIOS]
