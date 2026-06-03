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

## Current Behavior

No `little_loops.pii` module exists in the codebase. The `sft-corpus` FSM loop defines `pii_action` as a configurable filter parameter, but the `filter` state has no backing PII implementation — it must either skip PII handling entirely or inline ad-hoc regex logic, making it untestable and non-reusable.

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

## API/Interface

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

## Integration Map

### Files to Modify
- `scripts/little_loops/pii.py` — new module (create)
- `scripts/little_loops/__init__.py` — optional export addition
- `loops/sft-corpus.yaml` — update `filter` state to call `apply_pii_action()` instead of inline regex

### Dependent Files (Callers/Importers)
- `loops/sft-corpus.yaml` — primary consumer via `filter` state (`pii_action` context key from FEAT-1826)

### Similar Patterns
- TBD - review existing utility modules in `scripts/little_loops/` for import/export conventions

### Tests
- `scripts/tests/test_pii.py` — new test file (create)

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- [ ] `detect_pii()` correctly identifies email, phone, and SSN patterns
- [ ] `redact_pii()` replaces all PII spans with `[EMAIL]`/`[PHONE]`/`[SSN]` placeholders
- [ ] `apply_pii_action(example, "flag")` returns example annotated with `pii_detected: true`
- [ ] `apply_pii_action(example, "redact")` returns example with redacted content
- [ ] `apply_pii_action(example, "discard")` returns `None`
- [ ] Unit tests pass for all three actions and all three PII pattern types

## Scope Boundaries

- **In scope**: Regex-based detection of email, phone, and SSN patterns; `flag`/`redact`/`discard` action dispatch via `apply_pii_action()`; unit tests for each pattern and each action
- **Out of scope**: ML-based or NLP-based PII detection; additional PII types beyond email/phone/SSN in v1; GDPR/CCPA compliance tooling; context-aware or production-grade redaction; integration with external PII scanning services

## Impact

- **Priority**: P4 — Low urgency; FEAT-1826 can function without this (treat `flag` as no-op), but a standalone module makes PII handling testable and reusable
- **Effort**: Small — Two new files (`pii.py` + `test_pii.py`) plus a minor update to `sft-corpus.yaml`; no existing code refactored
- **Risk**: Low — Additive only; no existing hot-path code modified
- **Breaking Change**: No

## Related Key Documentation

- FEAT-1826 — `sft-corpus` FSM loop (primary consumer of this utility)
- EPIC-1880 — SLM fine-tuning from session logs (parent epic)

## Labels

`data`, `sft`, `pii`, `utility`

## Session Log
- `/ll:format-issue` - 2026-06-03T01:13:39 - `474349fa-2cec-4e81-a51f-9755284932ed.jsonl`
- `/ll:capture-issue` - 2026-06-03T00:48:04Z - `dd96413d-220c-449b-8e81-593defe00fdc.jsonl`

---
## Status

**Open** | Created: 2026-06-03 | Priority: P4
