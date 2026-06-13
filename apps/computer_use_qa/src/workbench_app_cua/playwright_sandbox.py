"""A real-browser CRM session — Playwright behind the same interface as UiSession.

This mirrors `sandbox.UiSession`, but instead of a deterministic in-memory state
machine it drives a real chromium page (`legacy_ui.html`) and reads the live DOM.
The same `Screen`/`Element` pydantic objects come back, so the existing scenario
runner and assertions work unchanged — only now they run against a real browser.

`observe()` determines the current `state` from the visible container's
`data-state`, reads input values / button labels / text nodes, and maps the
uniform `#error` element to `Screen.error` (None when empty/hidden).
"""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Browser, Page, Playwright, async_playwright

from workbench_app_cua.sandbox import Action, Element, Screen, State

_UI_URL = Path(__file__).with_name("legacy_ui.html").as_uri()

# Per-state element layout, mirroring UiSession.observe(). Each entry is
# (element id, kind). Labels/values are read from the live DOM in observe().
_LAYOUT: dict[State, list[tuple[str, str]]] = {
    "login": [
        ("username", "input"),
        ("password", "input"),
        ("submit", "button"),
    ],
    "dashboard": [
        ("greeting", "text"),
        ("new_customer", "button"),
        ("logout", "button"),
    ],
    "customer_form": [
        ("name", "input"),
        ("email", "input"),
        ("save", "button"),
        ("cancel", "button"),
    ],
    "success": [
        ("confirmation", "text"),
        ("back", "button"),
    ],
}

# Static labels for inputs/buttons, matching UiSession's labels so that
# expect_text substring checks behave identically. Text-node labels (greeting,
# confirmation) are read live from the DOM instead.
_LABELS: dict[str, str] = {
    "username": "Username",
    "password": "Password",
    "submit": "Sign in",
    "new_customer": "New customer",
    "logout": "Log out",
    "name": "Name",
    "email": "Email",
    "save": "Save",
    "cancel": "Cancel",
    "back": "Back to dashboard",
}


class PlaywrightSession:
    """One run of the legacy CRM in a real chromium browser.

    Use the async factory `create()` and always pair it with `close()` (or use
    the `playwright_session()` async context manager, which does both).
    """

    def __init__(self, pw: Playwright, browser: Browser, page: Page) -> None:
        self._pw = pw
        self._browser = browser
        self._page = page

    @classmethod
    async def create(cls) -> PlaywrightSession:
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(_UI_URL)
        except Exception:
            await pw.stop()
            raise
        return cls(pw, browser, page)

    async def close(self) -> None:
        try:
            await self._browser.close()
        finally:
            await self._pw.stop()

    async def observe(self) -> Screen:
        state: State = await self._page.get_attribute("#app", "data-state")  # type: ignore[assignment]

        elements: list[Element] = []
        for el_id, kind in _LAYOUT.get(state, []):
            if kind == "input":
                value = await self._page.input_value(f"#{el_id}")
                elements.append(Element(id=el_id, kind="input", label=_LABELS[el_id], value=value))
            elif kind == "button":
                elements.append(Element(id=el_id, kind="button", label=_LABELS[el_id]))
            else:  # text node — read the live label from the DOM
                label = (await self._page.text_content(f"#{el_id}")) or ""
                elements.append(Element(id=el_id, kind="text", label=label.strip()))

        error_text = (await self._page.text_content("#error")) or ""
        error = error_text.strip() or None

        return Screen(state=state, elements=elements, error=error)

    async def act(self, action: Action) -> Screen:
        if action.kind == "type":
            selector = f"#{action.target}"
            if await self._page.query_selector(selector) is None:
                return await self._observe_with_error(f"no such field: {action.target}")
            await self._page.fill(selector, action.value)
        elif action.kind == "click":
            selector = f"#{action.target}"
            handle = await self._page.query_selector(selector)
            if handle is None:
                return await self._observe_with_error(f"no such control here: {action.target}")
            await handle.click()
        return await self.observe()

    async def _observe_with_error(self, message: str) -> Screen:
        screen = await self.observe()
        screen.error = message
        return screen


class playwright_session:  # noqa: N801 — used as an async context manager factory
    """Async context manager: yields a ready PlaywrightSession and closes it."""

    def __init__(self) -> None:
        self._session: PlaywrightSession | None = None

    async def __aenter__(self) -> PlaywrightSession:
        self._session = await PlaywrightSession.create()
        return self._session

    async def __aexit__(self, *_exc: object) -> None:
        if self._session is not None:
            await self._session.close()
