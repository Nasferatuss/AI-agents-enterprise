"""Live-browse tests — model-driven loop over a REAL chromium page.

Like test_cua_playwright, these self-skip cleanly when the chromium binary is not
installed, so the default run stays green; the dedicated CI job runs them with
`-m playwright`. The ModelRouter is stubbed via httpx.MockTransport (same approach
as apps/deep_research/tests) so no API keys or LLM network calls are needed. The
browser target is a local file:// fixture to avoid flaky live-site DOM.
"""

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from workbench_app_cua.browse import LiveBrowseSession, run_browse
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter

pytestmark = pytest.mark.playwright


def _chromium_available() -> bool:
    async def _probe() -> bool:
        session = await LiveBrowseSession.create()
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


_FIXTURE_HTML = """<!doctype html>
<html><head><title>Fixture Page</title></head>
<body>
  <h1 id="heading">Welcome to the Fixture</h1>
  <p>The answer to the question is forty-two.</p>
  <button id="go">Go</button>
</body></html>
"""


def _scripted_router(actions: list[dict]) -> ModelRouter:
    """A ModelRouter whose every step() returns the next scripted JSON action."""
    seq = iter(actions)

    def handler(_request: httpx.Request) -> httpx.Response:
        try:
            action = next(seq)
        except StopIteration:
            action = {"action": "finish", "answer": "done"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": json.dumps(action)}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 10},
            },
        )

    provider = Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )
    router = ModelRouter(
        registry={"fake": provider},
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    router.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]
    return router


def _allow_file_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let these loop/refusal tests keep using local file:// fixtures.

    run_browse now runs every start URL through the SSRF guard (assert_public_url),
    which correctly rejects the file:// scheme. These tests exercise the observe→act
    loop and the payment-refusal path, not the URL guard (that has dedicated coverage
    in test_cua_browse_safety.py), so we relax the guard for the local fixture here.
    """
    import workbench_app_cua.browse as browse

    monkeypatch.setattr(browse, "assert_public_url", lambda url, **_: url)


async def test_browse_observe_action_finish_cycle(monkeypatch):
    _allow_file_fixtures(monkeypatch)
    with tempfile.TemporaryDirectory() as d:
        fixture = Path(d) / "fixture.html"
        fixture.write_text(_FIXTURE_HTML, encoding="utf-8")
        url = fixture.as_uri()

        # One click, then finish with the answer — exercises observe→act→observe→finish.
        router = _scripted_router(
            [
                {"action": "click", "selector": "#go"},
                {"action": "finish", "answer": "The heading is 'Welcome to the Fixture'."},
            ]
        )
        result = await run_browse(router, url, "What is the heading on this page?")

    assert result.completed is True
    assert "Welcome to the Fixture" in result.answer
    assert result.url == url
    assert result.goal == "What is the heading on this page?"
    # Two model turns: the click and the finish.
    assert len(result.steps) == 2
    assert result.steps[0].action["action"] == "click"
    assert result.steps[1].action["action"] == "finish"
    # The observation summary reflects the live fixture page.
    assert "Fixture Page" in result.steps[0].observation_summary


async def test_browse_refuses_payment_action(monkeypatch):
    _allow_file_fixtures(monkeypatch)
    with tempfile.TemporaryDirectory() as d:
        fixture = Path(d) / "fixture.html"
        fixture.write_text(_FIXTURE_HTML, encoding="utf-8")
        url = fixture.as_uri()

        router = _scripted_router([{"action": "click", "selector": "#pay-now-checkout"}])
        result = await run_browse(router, url, "complete the purchase")

    assert result.completed is False
    assert result.steps[-1].note is not None
    assert "refused" in result.steps[-1].note


_CHECKOUT_HTML = """<!doctype html>
<html><head><title>Checkout</title></head>
<body>
  <h1 id="heading">Payment details</h1>
  <form>
    <input id="cc-number" name="cc-number" placeholder="Card number" />
    <button id="continue" type="submit">Continue</button>
  </form>
</body></html>
"""


async def test_browse_blocks_submit_after_card_entry(monkeypatch):
    # Multi-step bypass: type a card number into #cc-number, then click a NEUTRAL
    # "Continue" submit button. The second action must be refused because sensitive
    # data was entered — even though "Continue" contains no pay/checkout keyword.
    _allow_file_fixtures(monkeypatch)
    with tempfile.TemporaryDirectory() as d:
        fixture = Path(d) / "checkout.html"
        fixture.write_text(_CHECKOUT_HTML, encoding="utf-8")
        url = fixture.as_uri()

        router = _scripted_router(
            [
                {"action": "type", "selector": "#cc-number", "text": "4111111111111111"},
                {"action": "click", "selector": "#continue"},
            ]
        )
        result = await run_browse(router, url, "continue past the payment form")

    assert result.completed is False
    # First action (the type) went through; the second (submit click) is refused.
    assert result.steps[0].action["action"] == "type"
    assert result.steps[-1].action["action"] == "click"
    assert result.steps[-1].note is not None
    assert "refused" in result.steps[-1].note
