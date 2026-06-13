"""Deterministic compliance checks: PII detection, policy rules, risk scoring.

These are pure, tested, LLM-free — the governance core. The risk *score* is
rule-based and reproducible (a defensible number, not an LLM guess); the LLM
later only writes the human-readable explanation around these findings.
"""

import re
from typing import Literal

from pydantic import BaseModel

PiiType = Literal["email", "phone", "ssn", "credit_card", "ipv4"]
Severity = Literal["low", "medium", "high"]
RiskBand = Literal["low", "medium", "high", "critical"]

# (type, compiled pattern, weight toward the risk score)
_PII_PATTERNS: list[tuple[PiiType, re.Pattern, int]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), 25),
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,16}\b"), 25),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), 8),
    ("phone", re.compile(r"\b(?:\+?\d{1,2}[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b"), 8),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), 4),
]


class PiiFinding(BaseModel):
    type: PiiType
    count: int
    example: str  # masked — never echoes the raw value


class PolicyRule(BaseModel):
    id: str
    description: str
    kind: Literal["forbidden_term", "required_clause"]
    pattern: str  # case-insensitive substring
    severity: Severity = "medium"


class PolicyViolation(BaseModel):
    rule_id: str
    description: str
    severity: Severity


def _luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 16:
        return False
    total, parity = 0, len(nums) % 2
    for i, d in enumerate(nums):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _mask(value: str) -> str:
    v = value.strip()
    if "@" in v:  # email
        name, _, domain = v.partition("@")
        return f"{name[0]}***@{domain}"
    digits = "".join(c for c in v if c.isdigit())
    if len(digits) >= 4:
        return f"***{digits[-4:]}"
    return "***"


def scan_pii(text: str) -> list[PiiFinding]:
    findings: list[PiiFinding] = []
    seen_spans: list[tuple[int, int]] = []
    for pii_type, pattern, _weight in _PII_PATTERNS:
        matches = []
        for m in pattern.finditer(text):
            span = m.span()
            # skip if already claimed by a higher-priority (earlier) pattern
            if any(span[0] < e and s < span[1] for s, e in seen_spans):
                continue
            if pii_type == "credit_card" and not _luhn_ok(m.group()):
                continue
            matches.append(m)
            seen_spans.append(span)
        if matches:
            findings.append(
                PiiFinding(type=pii_type, count=len(matches), example=_mask(matches[0].group()))
            )
    return findings


DEFAULT_RULES: list[PolicyRule] = [
    PolicyRule(
        id="no-plaintext-secrets",
        kind="forbidden_term",
        pattern="plaintext password",
        description="Credentials must not be stored or transmitted in plaintext.",
        severity="high",
    ),
    PolicyRule(
        id="no-disable-encryption",
        kind="forbidden_term",
        pattern="disable encryption",
        description="Encryption must not be disabled.",
        severity="high",
    ),
    PolicyRule(
        id="no-share-credentials",
        kind="forbidden_term",
        pattern="shared credentials",
        description="Shared credentials violate least-privilege policy.",
        severity="medium",
    ),
    PolicyRule(
        id="require-data-retention",
        kind="required_clause",
        pattern="data retention",
        description="A data retention policy must be stated.",
        severity="medium",
    ),
    PolicyRule(
        id="require-access-control",
        kind="required_clause",
        pattern="access control",
        description="Access control must be addressed.",
        severity="medium",
    ),
]

_SEVERITY_WEIGHT: dict[Severity, int] = {"low": 6, "medium": 14, "high": 28}


def check_policies(text: str, rules: list[PolicyRule]) -> list[PolicyViolation]:
    lowered = text.lower()
    violations: list[PolicyViolation] = []
    for rule in rules:
        present = rule.pattern.lower() in lowered
        violated = present if rule.kind == "forbidden_term" else not present
        if violated:
            violations.append(
                PolicyViolation(
                    rule_id=rule.id, description=rule.description, severity=rule.severity
                )
            )
    return violations


def score_risk(pii: list[PiiFinding], violations: list[PolicyViolation]) -> tuple[int, RiskBand]:
    """Deterministic 0–100 score from the findings, then a band."""
    weights = {t: w for t, _p, w in _PII_PATTERNS}
    score = sum(weights[f.type] * min(f.count, 3) for f in pii)
    score += sum(_SEVERITY_WEIGHT[v.severity] for v in violations)
    score = min(score, 100)
    if score >= 80:
        band: RiskBand = "critical"
    elif score >= 50:
        band = "high"
    elif score >= 20:
        band = "medium"
    else:
        band = "low"
    return score, band
