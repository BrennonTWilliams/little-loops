---
id: ENH-1885
title: Add PII detection utility for SFT corpus filtering
type: ENH
priority: P4
status: open
captured_at: '2026-06-03T00:48:04Z'
discovered_date: '2026-06-03'
discovered_by: capture-issue
parent: EPIC-1880
---

# ENH-1885: Add PII detection utility for SFT corpus filtering

## Summary

Add a `little_loops.pii` module providing regex-based PII detection (email, phone, SSN patterns) to back the `pii_action: "flag" | "redact" | "discard"` context key in FEAT-1826's `sft-corpus` loop filter state. Currently no PII utility exists in the codebase; the FEAT-1826 refinement recommends a regex heuristic in v1 or treating `flag` as a no-op.

## Motivation

FEAT-1826 (`sft-corpus` FSM loop) defines `pii_action` as a configurable filter behavior but has no backing implementation. Without a utility module, the `filter` state must either skip PII handling entirely or inline ad-hoc regex — making the logic untestable and non-reusable. A standalone module makes PII handling testable, reusable across data pipelines, and extensible to more patterns later.

## Expected Behavior

```python
from little_loops.pii import detect_pii, redact_pii

text = "Contact john@example.com or call 555-867-5309"
flags = detect_pii(text)       # -> ["email", "phone"]
clean = redact_pii(text)       # -> "Contact [EMAIL] or call [PHONE]"
```

Three actions supported:
- `flag` — return the example with a `pii_detected: true` annotation; do not modify
- `redact` — replace PII spans with `[TYPE]` placeholders in-place
- `discard` — return `None` (caller drops the example)

## API / Interface

```python
# little_loops/pii.py

PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b",
    "ssn":   r"\b\d{3}-\d{2}-\d{4}\b",
}

def detect_pii(text: str) -> list[str]:
    """Return list of PII type names found in text."""

def redact_pii(text: str) -> str:
    """Replace PII spans with [TYPE] placeholders."""

def apply_pii_action(example: dict, action: str) -> dict | None:
    """Apply flag/redact/discard to a formatted SFT example dict."""
```

## Implementation Steps

1. Create `scripts/little_loops/pii.py` with `PII_PATTERNS`, `detect_pii()`, `redact_pii()`, `apply_pii_action()`
2. Add `pii` to `scripts/little_loops/__init__.py` exports (or leave as internal import)
3. Create `scripts/tests/test_pii.py` — unit tests for each pattern and each action
4. Update FEAT-1826's filter state to call `apply_pii_action(example, context.pii_action)` instead of inline regex

## Acceptance Criteria

- [ ] `detect_pii()` correctly identifies email, phone, and SSN patterns
- [ ] `redact_pii()` replaces all PII spans with `[EMAIL]`/`[PHONE]`/`[SSN]` placeholders
- [ ] `apply_pii_action(example, "flag")` returns example annotated with `pii_detected: true`
- [ ] `apply_pii_action(example, "redact")` returns example with redacted content
- [ ] `apply_pii_action(example, "discard")` returns `None`
- [ ] Unit tests pass for all three actions and all three PII pattern types

## Related

- FEAT-1826 — sft-corpus FSM loop (primary consumer of this utility)
- EPIC-1880 — SLM fine-tuning from session logs (parent epic)

## Labels

`data`, `sft`, `pii`, `utility`

## Session Log
- `/ll:capture-issue` - 2026-06-03T00:48:04Z - `dd96413d-220c-449b-8e81-593defe00fdc.jsonl`

---
## Status

`open`
