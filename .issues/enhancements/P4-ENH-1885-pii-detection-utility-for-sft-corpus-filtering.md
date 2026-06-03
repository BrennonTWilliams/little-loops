---
id: ENH-1885
title: Add PII detection utility for SFT corpus filtering
type: ENH
priority: P4
status: done
captured_at: '2026-06-03T00:48:04Z'
completed_at: '2026-06-03T06:04:07Z'
discovered_date: '2026-06-03'
discovered_by: capture-issue
parent: EPIC-1880
confidence_score: 100
outcome_confidence: 88
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 25
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

1. Create `scripts/little_loops/pii.py` — start with `from __future__ import annotations`, module-level compiled `re.Pattern` constants (following `text_utils.py:_BACKTICK_PATH` pattern) or keep `PII_PATTERNS` as a raw-string dict and compile lazily; add `Args:`/`Returns:` docstrings on all three public functions
2. Optionally add `pii` exports to `scripts/little_loops/__init__.py` — two-step pattern: import symbol at the top, add to `__all__`; the loop consumer can use `from little_loops.pii import apply_pii_action` directly without touching `__init__.py`
3. Create `scripts/tests/test_pii.py` — follow `scripts/tests/test_text_utils.py`: one class per public function (`TestDetectPii`, `TestRedactPii`, `TestApplyPiiAction`), inline inputs, no fixtures needed; add `pytest.raises` for invalid `action` values
4. Wire `loops/sft-corpus.yaml` filter state to call `apply_pii_action(example, context.pii_action)` — **note: this file does not exist yet** (FEAT-1826 deliverable); this step applies when FEAT-1826 creates the loop, not in this ENH

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/API.md` — add `little_loops.pii` row to `## Module Overview` table; add `## little_loops.pii` API section documenting `PII_PATTERNS`, `detect_pii()`, `redact_pii()`, `apply_pii_action()`
6. Update `CONTRIBUTING.md` — add `├── pii.py # PII detection and redaction utilities` entry to `## Project Structure` file tree
7. Update `docs/ARCHITECTURE.md` — add `pii.py` entry to `## Directory Structure` file tree
8. (If step 2 adds `__init__.py` exports) — add 3 `test_smoke_import_*` methods to `TestNewProtocols` in `scripts/tests/test_extension.py`

## Integration Map

### Files to Modify
- `scripts/little_loops/pii.py` — new module (create)
- `scripts/little_loops/__init__.py` — optional export addition
- `loops/sft-corpus.yaml` — update `filter` state to call `apply_pii_action()` instead of inline regex

### Dependent Files (Callers/Importers)
- `loops/sft-corpus.yaml` — primary consumer via `filter` state (`pii_action` context key from FEAT-1826)

### Similar Patterns
- `scripts/little_loops/text_utils.py` — closest structural analogue: module-level compiled regex constants (`_BACKTICK_PATH`, `_DURATION_RE`), pure functions with `Args:`/`Returns:` docstrings, `from __future__ import annotations` on line 1
- `scripts/little_loops/sft_formatter.py` — minimal pure-function utility in the same dependency graph (`to_chatml()`, `to_alpaca()`, `to_sharegpt()`); shows the expected function shape for this module
- `scripts/little_loops/output_parsing.py` — module-scope dict of compiled patterns (`SECTION_PATTERN`, `TABLE_ROW_PATTERN`); relevant if `PII_PATTERNS` stores `re.Pattern` objects instead of raw strings

### Tests
- `scripts/tests/test_pii.py` — new test file (create)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_extension.py` — if step 2 adds `__init__.py` exports: add 3 `test_smoke_import_*` methods to `TestNewProtocols` for `detect_pii`, `redact_pii`, `apply_pii_action` (pattern: `from little_loops import X  # noqa: F401 — import is the test`)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — add `little_loops.pii` row to `## Module Overview` table; add `## little_loops.pii` API section documenting `PII_PATTERNS`, `detect_pii()`, `redact_pii()`, `apply_pii_action()` (every `little_loops.*` module has an entry here — the N/A designation in the original issue was incorrect)
- `CONTRIBUTING.md` — add `pii.py` entry to `## Project Structure` file tree (e.g., `├── pii.py # PII detection and redaction utilities`)
- `docs/ARCHITECTURE.md` — add `pii.py` entry to `## Directory Structure` file tree

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
- `/ll:ready-issue` - 2026-06-03T06:00:22 - `d2bc90df-4353-43d3-bde1-06bb46b2fec3.jsonl`
- `/ll:confidence-check` - 2026-06-03T06:00:00Z - `668e8525-fcbc-4360-adf2-fac62db1d711.jsonl`
- `/ll:wire-issue` - 2026-06-03T05:56:41 - `40c6bee3-9163-491f-a2e2-50c9de9979de.jsonl`
- `/ll:refine-issue` - 2026-06-03T05:53:09 - `f0f0418c-bd1d-40f2-aed3-608a5aa4ba77.jsonl`
- `/ll:format-issue` - 2026-06-03T01:13:39 - `474349fa-2cec-4e81-a51f-9755284932ed.jsonl`
- `/ll:capture-issue` - 2026-06-03T00:48:04Z - `dd96413d-220c-449b-8e81-593defe00fdc.jsonl`

---
## Status

**Open** | Created: 2026-06-03 | Priority: P4
