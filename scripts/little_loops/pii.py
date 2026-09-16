"""PII detection and redaction utilities for SFT corpus filtering.

Provides regex-based detection and redaction of email, phone, SSN, and
credential-shaped (API key/token/PEM/JWT) patterns. Primary consumer is the
``sft-corpus`` FSM loop's ``filter`` state via ``apply_pii_action()``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

# Compiled PII patterns — module-level to avoid recompilation on each call
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": _EMAIL,
    "phone": _PHONE,
    "ssn": _SSN,
}

_VALID_ACTIONS = frozenset({"flag", "redact", "discard"})


@dataclass(frozen=True)
class CredentialRule:
    """One shape of credential/API-key/token pattern."""

    name: str
    pattern: re.Pattern[str]
    rationale: str


CREDENTIAL_RULES: tuple[CredentialRule, ...] = (
    CredentialRule(
        name="aws_access_key",
        pattern=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        rationale="AWS long-term access key ID prefix",
    ),
    CredentialRule(
        name="github_token",
        pattern=re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        rationale="GitHub PAT / OAuth / user-server / refresh token prefixes",
    ),
    CredentialRule(
        name="anthropic_key",
        pattern=re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
        rationale="Anthropic API / OAuth key prefix",
    ),
    CredentialRule(
        name="slack_token",
        pattern=re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        rationale="Slack bot/app/user token prefixes",
    ),
    CredentialRule(
        name="private_key_pem",
        pattern=re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        rationale="PEM private-key block header",
    ),
    CredentialRule(
        name="jwt",
        pattern=re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        rationale="Three-segment base64url JWT",
    ),
)

CREDENTIAL_SCANNER_VERSION: int = 1  # bump only when scan semantics change


@dataclass(frozen=True)
class CredentialFinding:
    """One unsuppressed credential-pattern match. Redacted by construction —
    no ``excerpt`` field, so the finding itself never re-leaks the secret."""

    rule: str
    line: int
    fingerprint: str


def scan_text(
    text: str, rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES
) -> list[CredentialFinding]:
    """Scan *text* for credential-shaped patterns.

    Args:
        text: Input text to scan.
        rules: Rule table to scan against. Defaults to ``CREDENTIAL_RULES``.

    Returns:
        Findings sorted by ``(line, rule)`` for deterministic output.
        1-based line numbers. A line matching multiple rules yields one
        finding per rule.
    """
    findings: list[CredentialFinding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule in rules:
            for match in rule.pattern.finditer(line):
                fingerprint = hashlib.sha256(match.group().encode()).hexdigest()[:12]
                findings.append(
                    CredentialFinding(rule=rule.name, line=line_no, fingerprint=fingerprint)
                )
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def scan_file(
    path: Path, rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES
) -> list[CredentialFinding]:
    """Thin wrapper: read *path* as text and scan it with ``scan_text``."""
    return scan_text(path.read_text(encoding="utf-8", errors="replace"), rules)


def credential_rules_sha(rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES) -> str:
    """Stable sha256 over the rule table's name/pattern/flags (not rationale)."""
    payload = "\n".join(f"{r.name}\t{r.pattern.pattern}\t{r.pattern.flags}" for r in rules)
    return hashlib.sha256(payload.encode()).hexdigest()


def detect_pii(text: str) -> list[str]:
    """Return list of PII type names found in text.

    Args:
        text: Input text to scan for PII.

    Returns:
        List of PII type names (e.g. ``["email", "phone"]``) present in the
        text, including credential rule names (e.g. ``"aws_access_key"``)
        from ``CREDENTIAL_RULES``. Returns an empty list when no PII is
        detected.
    """
    found = [name for name, pattern in PII_PATTERNS.items() if pattern.search(text)]
    found.extend(rule.name for rule in CREDENTIAL_RULES if rule.pattern.search(text))
    return found


def redact_pii(text: str) -> str:
    """Replace PII spans with ``[TYPE]`` placeholders.

    Args:
        text: Input text to redact.

    Returns:
        Text with all PII spans replaced by their uppercased type placeholder
        (e.g. ``[EMAIL]``, ``[PHONE]``, ``[SSN]``, ``[AWS_ACCESS_KEY]``).
    """
    for name, pattern in PII_PATTERNS.items():
        text = pattern.sub(f"[{name.upper()}]", text)
    for rule in CREDENTIAL_RULES:
        text = rule.pattern.sub(f"[{rule.name.upper()}]", text)
    return text


def apply_pii_action(example: dict, action: str) -> dict | None:
    """Apply flag/redact/discard to a formatted SFT example dict.

    Scans all top-level string values for PII and applies the requested action.

    Args:
        example: SFT example dict (e.g. Alpaca ``{"instruction": ..., "output": ...}``).
        action: One of ``"flag"``, ``"redact"``, or ``"discard"``.

    Returns:
        - ``"flag"``: original example with ``pii_detected: True`` added if PII
          is present; original example unchanged if no PII found.
        - ``"redact"``: copy of example with PII in string values replaced by
          ``[TYPE]`` placeholders.
        - ``"discard"``: ``None`` when PII is detected; original example when
          no PII is found.

    Raises:
        ValueError: If *action* is not ``"flag"``, ``"redact"``, or ``"discard"``.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"Invalid pii_action {action!r}. Must be one of: {sorted(_VALID_ACTIONS)}")

    combined = " ".join(v for v in example.values() if isinstance(v, str))

    if action == "discard":
        return None if detect_pii(combined) else example

    if action == "flag":
        if detect_pii(combined):
            return {**example, "pii_detected": True}
        return example

    # redact: replace PII in all string values
    return {k: redact_pii(v) if isinstance(v, str) else v for k, v in example.items()}
