"""Live computer-use: drive a REAL website by URL toward a natural-language goal.

This is the open-web counterpart to the bundled QA scenarios (playwright_runner).
Instead of a fixed legacy-CRM fixture, it opens an arbitrary http(s) URL in real
headless chromium and runs a model-driven loop:

    observe page → model picks ONE json action → act → re-observe → repeat

until the model emits a ``finish`` action or the step cap is hit. The model only
ever sees a compact, bounded observation (title, url, a capped list of
interactable elements with stable selectors, and a trimmed text snapshot) so the
prompt stays small.

SAFETY boundary: this is read-only-ish browsing for navigation/extraction demos.
The action space is deliberately limited to click / type / navigate / finish, and
the loop refuses to submit obvious payment/checkout forms (see `_is_unsafe`). It
does NOT perform destructive or transactional actions. Keep demo goals to
navigation and information extraction.
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any

from playwright.async_api import Browser, Page, Playwright, async_playwright
from pydantic import BaseModel

from workbench_runtime.router import ModelRouter, NoProviderAvailableError
from workbench_runtime.types import UserMessage
from workbench_shared.netguard import UnsafeUrlError, assert_public_url

# Keep the model prompt small and the loop bounded.
_MAX_STEPS = 7
_MAX_ELEMENTS = 30
_MAX_TEXT_CHARS = 1500
_MAX_LABEL_CHARS = 80
_VIEWPORT = {"width": 1280, "height": 800}
_NAV_TIMEOUT_MS = 15_000

# Action keywords that indicate a destructive / transactional submit we refuse.
_UNSAFE_TOKENS = (
    "pay",
    "payment",
    "checkout",
    "purchase",
    "buy now",
    "place order",
    "confirm order",
    "delete account",
)

# Field markers that indicate a `type` action is entering sensitive data (card
# numbers, CVV, passwords, etc.) into the page. Matched against the action's
# selector / field text.
_SENSITIVE_FIELD_TOKENS = (
    "card",
    "cc-number",
    "cardnumber",
    "cvv",
    "cvc",
    "iban",
    "password",
    "passwd",
    "ssn",
)

# Strip separators commonly found in entered card numbers before length check.
_DIGIT_RUN = re.compile(r"[\s\-]")

_SYSTEM = (
    "You are a careful web agent driving a real headless browser toward a goal. "
    "On each turn you receive the current page observation (title, url, a numbered "
    "list of interactable elements with selectors, and a text snapshot). Decide the "
    "single best next action and reply with ONE JSON object and nothing else. "
    "Valid actions:\n"
    '  {"action":"click","selector":"<css selector from the list>"}\n'
    '  {"action":"type","selector":"<css selector>","text":"<text>"}\n'
    '  {"action":"navigate","url":"<absolute http(s) url>"}\n'
    '  {"action":"finish","answer":"<final answer to the goal>"}\n'
    "Use only selectors shown in the element list. When you can already answer the "
    "goal from the observation, emit a finish action with the answer. Do NOT submit "
    "payment, checkout, or otherwise destructive forms — this is read-only browsing."
)


class BrowseStep(BaseModel):
    observation_summary: str
    action: dict[str, Any]
    note: str | None = None  # set when an action was skipped/failed


class BrowseResult(BaseModel):
    url: str
    goal: str
    steps: list[BrowseStep]
    answer: str
    completed: bool
    provider: str | None = None
    cost_usd: float | None = None


class _Observation(BaseModel):
    title: str
    url: str
    elements: list[dict[str, str]]  # {selector, kind, text}
    text: str


class LiveBrowseSession:
    """A real chromium page that can navigate to arbitrary http(s) URLs.

    Mirrors PlaywrightSession's create()/close() lifecycle, but is goal-agnostic:
    it exposes generic goto/observe/click/type/navigate primitives over the live
    DOM rather than the legacy-CRM-specific layout.
    """

    def __init__(self, pw: Playwright, browser: Browser, page: Page) -> None:
        self._pw = pw
        self._browser = browser
        self._page = page

    @classmethod
    async def create(cls) -> LiveBrowseSession:
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport=_VIEWPORT)
            page.set_default_timeout(_NAV_TIMEOUT_MS)
        except Exception:
            await pw.stop()
            raise
        return cls(pw, browser, page)

    async def close(self) -> None:
        try:
            await self._browser.close()
        finally:
            await self._pw.stop()

    async def goto(self, url: str) -> None:
        await self._page.goto(url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)

    async def observe(self) -> _Observation:
        """A compact, bounded snapshot of the live page for the model."""
        title = (await self._page.title()) or ""
        url = self._page.url

        # Stable-ish selectors for interactable elements, with visible text.
        elements: list[dict[str, str]] = await self._page.evaluate(
            """(max) => {
                const out = [];
                const sel = 'a, button, input, textarea, select, [role=button]';
                const nodes = Array.from(document.querySelectorAll(sel));
                let n = 0;
                for (const el of nodes) {
                    if (out.length >= max) break;
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    const style = window.getComputedStyle(el);
                    if (style.visibility === 'hidden' || style.display === 'none') continue;
                    let selector;
                    if (el.id) selector = '#' + CSS.escape(el.id);
                    else {
                        el.setAttribute('data-cua-ref', String(n));
                        selector = '[data-cua-ref="' + n + '"]';
                        n++;
                    }
                    const tag = el.tagName.toLowerCase();
                    let kind = tag;
                    if (tag === 'a') kind = 'link';
                    else if (tag === 'input' || tag === 'textarea') kind = 'input';
                    const text = (el.innerText || el.value || el.getAttribute('aria-label')
                        || el.getAttribute('placeholder') || el.getAttribute('name') || '').trim();
                    out.push({selector, kind, text});
                }
                return out;
            }""",
            _MAX_ELEMENTS,
        )
        for el in elements:
            if len(el["text"]) > _MAX_LABEL_CHARS:
                el["text"] = el["text"][:_MAX_LABEL_CHARS] + "…"

        body_text = (
            await self._page.evaluate("() => document.body ? document.body.innerText : ''")
        ) or ""
        text = " ".join(body_text.split())[:_MAX_TEXT_CHARS]

        return _Observation(title=title, url=url, elements=elements, text=text)

    async def click(self, selector: str) -> None:
        await self._page.click(selector, timeout=_NAV_TIMEOUT_MS)
        await self._settle()

    async def type(self, selector: str, text: str) -> None:
        await self._page.fill(selector, text, timeout=_NAV_TIMEOUT_MS)

    async def navigate(self, url: str) -> None:
        await self.goto(url)

    async def _settle(self) -> None:
        # Clicks may trigger navigation; tolerate pages that never go fully idle.
        with contextlib.suppress(Exception):
            await self._page.wait_for_load_state("domcontentloaded", timeout=_NAV_TIMEOUT_MS)


def _render_observation(obs: _Observation) -> str:
    lines = [f"TITLE: {obs.title}", f"URL: {obs.url}", "ELEMENTS:"]
    for el in obs.elements:
        lines.append(f'  [{el["kind"]}] {el["selector"]} — {el["text"]}')
    if not obs.elements:
        lines.append("  (none)")
    lines.append("TEXT SNAPSHOT:")
    lines.append(obs.text or "(empty)")
    return "\n".join(lines)


def _summarize_observation(obs: _Observation) -> str:
    return f"{obs.title or '(untitled)'} @ {obs.url} ({len(obs.elements)} interactable)"


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Pull the first balanced top-level JSON object out of a model reply."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    return obj if isinstance(obj, dict) else None
        start = text.find("{", start + 1)
    return None


def _looks_like_card_number(value: str) -> bool:
    """True if `value` is a bare 13–19 digit run (typical PAN length)."""
    digits = _DIGIT_RUN.sub("", value)
    return digits.isdigit() and 13 <= len(digits) <= 19


def _is_sensitive_type(action: dict[str, Any]) -> bool:
    """True if a `type` action puts sensitive data into a sensitive-looking field."""
    if str(action.get("action")) != "type":
        return False
    selector = str(action.get("selector", ""))
    name = str(action.get("name", ""))
    placeholder = str(action.get("placeholder", ""))
    field = f"{selector} {name} {placeholder}".lower()
    if any(tok in field for tok in _SENSITIVE_FIELD_TOKENS):
        return True
    return _looks_like_card_number(str(action.get("text", "")))


def _is_unsafe(action: dict[str, Any], *, sensitive_entered: bool = False) -> bool:
    """Refuse destructive/transactional submits and sensitive-data exfiltration.

    Two layers of defence:
      1. Obvious pay/checkout/delete/purchase keywords in any action field.
      2. Once sensitive data has been entered (`sensitive_entered` — raised by the
         caller when a `type` action matches ``_is_sensitive_type``), ANY subsequent
         submit/button click is blocked — even a neutral "Continue"/"Next" — so a
         multi-step `type → click` cannot smuggle the submission past the keyword
         filter.
    """
    blob = " ".join(str(v) for v in action.values()).lower()
    if any(tok in blob for tok in _UNSAFE_TOKENS):
        return True
    # After sensitive entry, block any click. The model only hands us a CSS selector
    # (often an opaque id like `#continue` that hides the element's true nature), so a
    # selector-token heuristic is trivially bypassed; the conservative rule is to refuse
    # every click once a card/cvv/password has been typed. Navigation away (the navigate
    # action) stays allowed.
    return sensitive_entered and str(action.get("action")) == "click"


async def run_browse(
    router: ModelRouter,
    url: str,
    goal: str,
    *,
    max_steps: int = _MAX_STEPS,
) -> BrowseResult:
    """Open `url` in real chromium and drive the page toward `goal` with the model."""
    steps: list[BrowseStep] = []
    answer = ""
    completed = False
    provider: str | None = None
    cost_usd: float | None = None
    sensitive_entered = False

    # SSRF guard: validate the start URL before launching a browser or navigating.
    # A prompt-injected / hostile start URL pointing at loopback, RFC-1918, or the
    # cloud metadata endpoint (169.254.169.254) must never be opened.
    try:
        assert_public_url(url)
    except UnsafeUrlError as exc:
        steps.append(
            BrowseStep(
                observation_summary=f"(not opened) {url}",
                action={"action": "navigate", "url": url},
                note=f"refused: unsafe start url blocked by safety policy: {exc}",
            )
        )
        return BrowseResult(
            url=url,
            goal=goal,
            steps=steps,
            answer=f"Refused to open unsafe URL: {exc}",
            completed=False,
            provider=provider,
            cost_usd=cost_usd,
        )

    session = await LiveBrowseSession.create()
    try:
        await session.goto(url)

        for _ in range(max_steps):
            obs = await session.observe()
            prompt = (
                f"GOAL: {goal}\n\n"
                f"CURRENT PAGE OBSERVATION:\n{_render_observation(obs)}\n\n"
                "Reply with ONE JSON action object."
            )
            try:
                out = await router.step(
                    [UserMessage(content=prompt)],
                    complexity="standard",
                    system=_SYSTEM,
                    max_tokens=512,
                )
            except NoProviderAvailableError:
                steps.append(
                    BrowseStep(
                        observation_summary=_summarize_observation(obs),
                        action={"action": "finish"},
                        note="no model provider available",
                    )
                )
                break

            provider = out.provider or provider
            if out.cost_usd is not None:
                cost_usd = (cost_usd or 0.0) + out.cost_usd

            action = _extract_json_object(out.text)
            if action is None or "action" not in action:
                steps.append(
                    BrowseStep(
                        observation_summary=_summarize_observation(obs),
                        action={"raw": out.text[:200]},
                        note="could not parse a JSON action; stopping",
                    )
                )
                break

            kind = str(action.get("action"))
            summary = _summarize_observation(obs)

            if kind == "finish":
                answer = str(action.get("answer", "")).strip()
                completed = True
                steps.append(BrowseStep(observation_summary=summary, action=action))
                break

            if _is_unsafe(action, sensitive_entered=sensitive_entered):
                steps.append(
                    BrowseStep(
                        observation_summary=summary,
                        action=action,
                        note="refused: payment/sensitive/destructive action blocked by policy",
                    )
                )
                break

            note: str | None = None
            stop = False
            try:
                if kind == "click":
                    await session.click(str(action.get("selector", "")))
                elif kind == "type":
                    await session.type(str(action.get("selector", "")), str(action.get("text", "")))
                    # Track sensitive input so a later neutral submit/click is blocked.
                    if _is_sensitive_type(action):
                        sensitive_entered = True
                elif kind == "navigate":
                    target = str(action.get("url", ""))
                    try:
                        assert_public_url(target)
                    except UnsafeUrlError as exc:
                        note = f"refused: unsafe navigate blocked by safety policy: {exc}"
                        stop = True
                    else:
                        await session.navigate(target)
                else:
                    note = f"unknown action: {kind}; stopping"
                    stop = True
            except Exception as exc:  # noqa: BLE001 — surface DOM/nav failures in the transcript
                note = f"action failed: {type(exc).__name__}: {exc}"
                stop = True  # hard failure — stop rather than spin

            steps.append(BrowseStep(observation_summary=summary, action=action, note=note))
            if stop:
                break
    finally:
        await session.close()

    if not completed and not answer:
        answer = "Goal not completed within the step budget."

    return BrowseResult(
        url=url,
        goal=goal,
        steps=steps,
        answer=answer,
        completed=completed,
        provider=provider,
        cost_usd=cost_usd,
    )
