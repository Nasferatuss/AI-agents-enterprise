"""Real-browser QA tests — the Playwright-driven sandbox behind the same interface.

These reproduce the virtual results (test_cua.py) through a REAL chromium browser.
They self-skip cleanly when the chromium binary is not installed, so the default
test run stays green; the dedicated CI job installs chromium and runs them for real.
"""

import asyncio

import pytest

from workbench_app_cua.playwright_runner import run_qa_playwright
from workbench_app_cua.playwright_sandbox import PlaywrightSession
from workbench_app_cua.scenarios import SCENARIOS

pytestmark = pytest.mark.playwright


def _chromium_available() -> bool:
    """Best-effort: can we actually launch chromium? Skip the suite if not."""

    async def _probe() -> bool:
        session = await PlaywrightSession.create()
        await session.close()
        return True

    try:
        return asyncio.run(_probe())
    except Exception:
        return False


if not _chromium_available():
    pytest.skip(
        "chromium not installed — run `playwright install chromium`",
        allow_module_level=True,
    )


async def test_real_browser_reproduces_virtual_results():
    report = await run_qa_playwright(SCENARIOS)
    by_name = {r.name: r for r in report.scenarios}

    # Happy paths pass through a real browser.
    assert by_name["login_valid"].passed
    assert by_name["login_invalid_recovers"].passed  # error recovery works
    assert by_name["create_customer_valid"].passed

    # Planted bugs surface through the real DOM.
    assert not by_name["email_validation"].passed  # BUG-1: no email validation
    assert not by_name["dashboard_copy"].passed  # BUG-2: "Welcom" typo

    assert report.passed == 3 and report.failed == 2
    bug_scenarios = {b.scenario for b in report.bugs}
    assert bug_scenarios == {"email_validation", "dashboard_copy"}

    # Every action was driven through the audited gateway.
    assert len(report.action_trace) > 0
    assert all(a.allowed for a in report.action_trace)
