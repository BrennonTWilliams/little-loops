"""PII detection and redaction utilities for SFT corpus filtering.

Provides regex-based detection and redaction of email, phone, and SSN patterns.
Primary consumer is the ``sft-corpus`` FSM loop's ``filter`` state via
``apply_pii_action()``.
"""

from __future__ import annotations

import re

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


def detect_pii(text: str) -> list[str]:
    """Return list of PII type names found in text.

    Args:
        text: Input text to scan for PII.

    Returns:
        List of PII type names (e.g. ``["email", "phone"]``) present in the
        text.  Returns an empty list when no PII is detected.
    """
    return [name for name, pattern in PII_PATTERNS.items() if pattern.search(text)]


def redact_pii(text: str) -> str:
    """Replace PII spans with ``[TYPE]`` placeholders.

    Args:
        text: Input text to redact.

    Returns:
        Text with all PII spans replaced by their uppercased type placeholder
        (e.g. ``[EMAIL]``, ``[PHONE]``, ``[SSN]``).
    """
    for name, pattern in PII_PATTERNS.items():
        text = pattern.sub(f"[{name.upper()}]", text)
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
        raise ValueError(
            f"Invalid pii_action {action!r}. Must be one of: {sorted(_VALID_ACTIONS)}"
        )

    combined = " ".join(v for v in example.values() if isinstance(v, str))

    if action == "discard":
        return None if detect_pii(combined) else example

    if action == "flag":
        if detect_pii(combined):
            return {**example, "pii_detected": True}
        return example

    # redact: replace PII in all string values
    return {k: redact_pii(v) if isinstance(v, str) else v for k, v in example.items()}
