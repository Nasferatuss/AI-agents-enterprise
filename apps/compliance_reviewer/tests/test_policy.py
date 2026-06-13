from pathlib import Path

from workbench_app_compliance.policy import (
    DEFAULT_RULES,
    check_policies,
    scan_pii,
    score_risk,
)

_DOCS = Path(__file__).resolve().parents[3] / "examples" / "docs"


def test_pii_detection_masks_values():
    text = "Contact jane.doe@example.com, SSN 123-45-6789, card 4111 1111 1111 1111."
    findings = {f.type: f for f in scan_pii(text)}
    assert set(findings) >= {"email", "ssn", "credit_card"}
    assert findings["email"].example == "j***@example.com"
    assert findings["ssn"].example == "***6789"
    # raw values never echoed
    assert "123-45-6789" not in findings["ssn"].example


def test_invalid_credit_card_is_not_flagged():
    # 16 digits that fail Luhn → not a credit card
    assert not any(f.type == "credit_card" for f in scan_pii("number 1234 5678 9012 3456"))


def test_clean_document_has_no_pii_and_no_violations():
    text = (_DOCS / "clean_policy.md").read_text()
    assert scan_pii(text) == []
    assert check_policies(text, DEFAULT_RULES) == []
    score, band = score_risk([], [])
    assert score == 0 and band == "low"


def test_forbidden_terms_and_missing_clauses_flagged():
    text = "We use shared credentials and may disable encryption in staging."
    violations = {v.rule_id for v in check_policies(text, DEFAULT_RULES)}
    assert "no-share-credentials" in violations  # forbidden term present
    assert "no-disable-encryption" in violations
    assert "require-data-retention" in violations  # required clause missing
    assert "require-access-control" in violations


def test_risk_score_is_deterministic_and_banded():
    text = (_DOCS / "sample_spec.md").read_text()
    pii = scan_pii(text)
    violations = check_policies(text, DEFAULT_RULES)
    score, band = score_risk(pii, violations)
    # SSN(25) + email(8) + violations push this well into high/critical
    assert score >= 50
    assert band in ("high", "critical")
    # deterministic: same inputs → same score
    assert score_risk(pii, violations) == (score, band)
