"""A deterministic 'legacy CRM' web UI as a state machine — the QA sandbox.

The agent never touches a real browser in v0: `observe()` returns a structured
screen (an accessibility-tree-style 'screenshot') and `act()` applies a click or
keystroke. A production version would put Playwright + a vision model behind this
exact interface. Two bugs are planted on purpose so the QA agent has something to
report:
  BUG-1 (validation): the customer form accepts an invalid email (no '@').
  BUG-2 (content): the dashboard greeting is misspelled ("Welcom").
"""

from typing import Literal

from pydantic import BaseModel

State = Literal["login", "dashboard", "customer_form", "success"]
ActionKind = Literal["observe", "click", "type"]

_VALID_USER, _VALID_PASS = "admin", "secret"


class Element(BaseModel):
    id: str
    kind: Literal["input", "button", "text"]
    label: str
    value: str = ""


class Screen(BaseModel):
    state: State
    elements: list[Element]
    error: str | None = None

    def render(self) -> str:
        """Plain-text 'screenshot' of the screen."""
        lines = [f"[{self.state}]"]
        for e in self.elements:
            if e.kind == "button":
                lines.append(f"  <button id={e.id}>{e.label}</button>")
            elif e.kind == "input":
                lines.append(f"  {e.label}: [{e.value}] (id={e.id})")
            else:
                lines.append(f"  {e.label}")
        if self.error:
            lines.append(f"  ⚠ {self.error}")
        return "\n".join(lines)


class Action(BaseModel):
    kind: ActionKind
    target: str = ""
    value: str = ""


class UiSession:
    """One run of the legacy CRM. Mutable; driven via act()."""

    def __init__(self) -> None:
        self.state: State = "login"
        self.fields: dict[str, str] = {"username": "", "password": "", "name": "", "email": ""}
        self.error: str | None = None

    def observe(self) -> Screen:
        if self.state == "login":
            els = [
                Element(
                    id="username", kind="input", label="Username", value=self.fields["username"]
                ),
                Element(
                    id="password", kind="input", label="Password", value=self.fields["password"]
                ),
                Element(id="submit", kind="button", label="Sign in"),
            ]
        elif self.state == "dashboard":
            els = [
                # BUG-2: "Welcom" is a planted typo (should be "Welcome").
                Element(id="greeting", kind="text", label=f"Welcom, {self.fields['username']}"),
                Element(id="new_customer", kind="button", label="New customer"),
                Element(id="logout", kind="button", label="Log out"),
            ]
        elif self.state == "customer_form":
            els = [
                Element(id="name", kind="input", label="Name", value=self.fields["name"]),
                Element(id="email", kind="input", label="Email", value=self.fields["email"]),
                Element(id="save", kind="button", label="Save"),
                Element(id="cancel", kind="button", label="Cancel"),
            ]
        else:  # success
            els = [
                Element(id="confirmation", kind="text", label="Customer saved"),
                Element(id="back", kind="button", label="Back to dashboard"),
            ]
        return Screen(state=self.state, elements=els, error=self.error)

    def act(self, action: Action) -> Screen:
        self.error = None
        if action.kind == "type":
            if action.target in self.fields:
                self.fields[action.target] = action.value
            else:
                self.error = f"no such field: {action.target}"
        elif action.kind == "click":
            self._click(action.target)
        return self.observe()

    def _click(self, target: str) -> None:
        if self.state == "login" and target == "submit":
            if self.fields["username"] == _VALID_USER and self.fields["password"] == _VALID_PASS:
                self.state = "dashboard"
            else:
                self.error = "Invalid credentials"
        elif self.state == "dashboard" and target == "new_customer":
            self.fields["name"], self.fields["email"] = "", ""
            self.state = "customer_form"
        elif self.state == "dashboard" and target == "logout":
            self.state = "login"
        elif self.state == "customer_form" and target == "save":
            if not self.fields["name"].strip():
                self.error = "Name is required"
            else:
                # BUG-1: email is NOT validated — an invalid email is accepted.
                self.state = "success"
        elif (self.state == "customer_form" and target == "cancel") or (
            self.state == "success" and target == "back"
        ):
            self.state = "dashboard"
        else:
            self.error = f"no such control here: {target}"
