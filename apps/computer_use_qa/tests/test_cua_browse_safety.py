"""Safety-boundary tests for live-browse — pure-function and SSRF coverage.

These are deliberately Chromium-free and LLM-free (like the other deterministic
CUA tests): the SSRF start-URL guard short-circuits before any browser launch, and
the `_is_unsafe`/helper checks are pure functions. They therefore run in the
default suite (no `playwright` marker), unlike test_cua_browse which self-skips
without a chromium binary.
"""

import asyncio

import pytest

from workbench_app_cua.browse import (
    _is_sensitive_type,
    _is_unsafe,
    _looks_like_card_number,
    run_browse,
)

# --- SSRF guard on the start URL -------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/",  # cloud metadata endpoint
        "http://127.0.0.1/",  # loopback
        "http://localhost/",  # loopback by name
    ],
)
def test_run_browse_refuses_unsafe_start_url(url):
    # router is never consulted: the guard rejects before any browser launch, so we
    # can pass None and still never touch it. No Chromium / network required.
    result = asyncio.run(run_browse(None, url, "extract the page title"))

    assert result.completed is False
    assert result.url == url
    assert len(result.steps) == 1
    note = result.steps[0].note or ""
    assert "refused" in note
    assert "unsafe start url" in note
    assert "Refused to open unsafe URL" in result.answer


# --- Multi-step sensitive-data bypass (HIGH-1) -----------------------------------


def test_neutral_submit_blocked_after_sensitive_entry():
    # 1) type a card number into a sensitive field — raises the flag (not blocked).
    type_action = {"action": "type", "selector": "#cc-number", "text": "4111111111111111"}
    assert _is_sensitive_type(type_action) is True
    assert _is_unsafe(type_action, sensitive_entered=False) is False

    # 2) a neutral "Continue" button with an OPAQUE id (no pay/checkout/submit token
    #    in the selector) is now blocked solely because sensitive data was entered.
    click_action = {"action": "click", "selector": "#continue"}
    assert _is_unsafe(click_action, sensitive_entered=False) is False
    assert _is_unsafe(click_action, sensitive_entered=True) is True

    # Navigation away is still allowed even after sensitive entry.
    nav_action = {"action": "navigate", "url": "https://example.com/"}
    assert _is_unsafe(nav_action, sensitive_entered=True) is False


def test_sensitive_type_detection():
    # selector / name / placeholder markers
    assert _is_sensitive_type({"action": "type", "selector": "#cvv", "text": "123"}) is True
    assert _is_sensitive_type({"action": "type", "selector": "#pw", "name": "password"}) is True
    assert _is_sensitive_type({"action": "type", "selector": "#x", "placeholder": "IBAN"}) is True
    # value shaped like a card number even in a non-obvious field
    card = {"action": "type", "selector": "#x", "text": "4111 1111 1111 1111"}
    assert _is_sensitive_type(card) is True
    # benign input is not sensitive
    assert _is_sensitive_type({"action": "type", "selector": "#search", "text": "hello"}) is False
    # only `type` actions qualify
    assert _is_sensitive_type({"action": "click", "selector": "#cvv"}) is False


def test_card_number_shape():
    assert _looks_like_card_number("4111111111111111") is True  # 16
    assert _looks_like_card_number("4111-1111 1111-111") is True  # 15 w/ separators
    assert _looks_like_card_number("4111111111111") is True  # 13 (min)
    assert _looks_like_card_number("4111111111111111111") is True  # 19 (max)
    assert _looks_like_card_number("123") is False  # too short
    assert _looks_like_card_number("41111111111111111111") is False  # 20, too long
    assert _looks_like_card_number("hello world") is False


# --- Existing obvious-payment behaviour preserved (HIGH-1c) ----------------------


def test_obvious_payment_still_blocked_without_flag():
    assert _is_unsafe({"action": "click", "selector": "#pay-now"}) is True
    assert _is_unsafe({"action": "click", "selector": "#checkout-btn"}) is True
    assert _is_unsafe({"action": "click", "text": "Delete account"}) is True
    assert _is_unsafe({"action": "click", "selector": "#home-link"}) is False
