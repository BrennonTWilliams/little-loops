---
id: ENH-1948
title: Wire PII detection into sft-corpus.yaml filter chain
type: ENH
priority: P4
status: done
captured_at: '2026-06-04T20:01:37Z'
completed_at: '2026-06-04T21:55:00Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
relates_to:
- EPIC-1880
- ENH-1885
- FEAT-1826
labels:
- epic: EPIC-1880
- enhancement
- sft
- pii
- loop
---

# ENH-1948: Wire PII detection into sft-corpus.yaml filter chain

## Summary

`little_loops.pii` (ENH-1885) delivers `detect_pii()`, `redact_pii()`, and `apply_pii_action()` — but `sft-corpus.yaml` has no state calling them. Wire `apply_pii_action()` into the filter predicate chain as predicate 5 (`check_pii`), add the `pii_action` context key (`"flag"` default), and add a companion `reject_pii` state. All three PII actions (flag/redact/discard) are implemented with graceful fallback for unknown values.

## Current Behavior

**Post-implementation.** The PII wiring is complete in `sft-corpus.yaml` (`scripts/little_loops/loops/sft-corpus.yaml`):

- **Context key** (line 25): `pii_action: "flag"` — defaults to pass-through annotation, accepts `"flag" | "redact" | "discard"`
- **`check_pii` state** (lines 262-297): Predicate 5 in the filter chain. Calls `apply_pii_action()` from `little_loops.pii`:
  - `"flag"`: annotates with `pii_detected: true`, always prints 1 (pass)
  - `"redact"`: replaces PII spans with `[TYPE]` placeholders, writes back to enriched file, prints 1
  - `"discard"`: prints 0 (reject) when PII detected, prints 1 (pass) when clean
  - Unknown value: prints 1 (safe pass-through with `except ValueError` fallback)
- **`reject_pii` state** (lines 299-317): Appends `{path, score: 0, reason: "pii_detected", timestamp}` to `rejections.jsonl`, routes `next: publish`
- **Routing**: `check_files → check_pii` (line 239), `reject_files → check_pii` (line 260), `check_pii → publish | reject_pii` (lines 296-297), `reject_pii → publish` (line 317)

Full filter predicate chain: `check_issue_outcome → check_corrections → check_tools → check_files → check_pii → publish`

**Tests** (`scripts/tests/test_loops_sft_corpus.py`): 16 PII tests across 4 classes:
- `TestPiiFlagPassthrough` (lines 498-558): 3 tests — annotation, clean pass-through, predicate script
- `TestPiiRedact` (lines 561-658): 6 tests — email, phone, SSN, multiple types, non-PII preservation, predicate script
- `TestPiiDiscard` (lines 661-753): 4 tests — None on PII, unchanged on clean, prints 0, prints 1
- `TestPiiDefaultBehavior` (lines 756-810): 3 tests — flag is default, ValueError on invalid, unknown action fallthrough

**ENH-1885** delivered `scripts/little_loops/pii.py` with:
- `detect_pii(text)` → `list[str]` (email, phone, SSN via compiled regex patterns `_EMAIL`, `_PHONE`, `_SSN`)
- `redact_pii(text)` → `str` (replaces with `[EMAIL]`/`[PHONE]`/`[SSN]`)
- `apply_pii_action(example, action)` → `dict | None` (flag/redact/discard dispatch; raises `ValueError` on invalid action)

## Expected Behavior

1. ✅ `sft-corpus.yaml` context block includes `pii_action: "flag"` (line 25)
2. ✅ `check_pii` state runs as predicate 5 in the filter chain (lines 262-297)
3. ✅ `"redact"` replaces PII spans with `[TYPE]` placeholders before downstream states read the example
4. ✅ `"discard"` rejects examples with PII, logging to `rejections.jsonl` with reason `"pii_detected"`
5. ✅ `"flag"` annotates with `pii_detected: true`, no rejection
6. ✅ Unknown/unset action: safe pass-through (prints 1, no modification)

## Motivation

`pii_action: "redact"` in the config was a dead key — user data went out unfiltered regardless of setting. The PII module exists, works, and is tested; it just needed to be called from the loop. Closing this gap makes the `pii_action` context key functional, completing the work ENH-1885 started.

## Success Metrics

- ✅ **PII detection rate**: 100% of examples with emails, phone numbers, or SSNs flagged when `pii_action` is set
- ✅ **Redaction coverage**: All detected PII spans replaced with `[EMAIL]`/`[PHONE]`/`[SSN]` placeholders when `pii_action: "redact"`
- ✅ **Rejection accuracy**: Examples with PII correctly rejected and logged to `rejections.jsonl` with reason `"pii_detected"` when `pii_action: "discard"`
- ✅ **Pass-through correctness**: No modification or rejection when `pii_action: "flag"` or unset
- ✅ **Test coverage**: 16 tests across 4 test classes covering flag, redact, discard, and default behaviors (exceeds original target of 4)

## Implementation Details

### Changes Made

**`scripts/little_loops/loops/sft-corpus.yaml`:**
- Context block line 25: added `pii_action: "flag"` (one line)
- Lines 262-297: `check_pii` state (35 lines) — `python3 << 'PYEOF'` heredoc importing `apply_pii_action`, dispatching on action value with `output_numeric` evaluator (`operator: eq`, `target: 1`)
- Lines 299-317: `reject_pii` state (18 lines) — standard reject pattern with `reason: "pii_detected"`, routes `next: publish`
- Line 239: `check_files.on_yes` updated from `publish` → `check_pii`
- Line 260: `reject_files.next` updated from `publish` → `check_pii`

**`scripts/tests/test_loops_sft_corpus.py`:**
- Lines 498-810: 16 PII tests across 4 classes (flag, redact, discard, default behaviors)

### Implementation Pattern

`check_pii` follows the same filter predicate pattern as the 4 existing quality checks:
- `action_type: shell` with `python3 << 'PYEOF'` heredoc (same as `enrich` and `publish`)
- `captured.enrich_output.output` for reading AND writing the enriched example
- `evaluate: {type: output_numeric, operator: eq, target: 1}` for binary routing
- Companion `reject_pii` state using identical reject-entry template (`path`, `score: 0`, `reason`, `timestamp`)

Key deviation from other predicates: `check_pii` is the only predicate that **writes back** to `${captured.enrich_output.output}` (for `flag` and `redact` actions), overwriting the enriched file with the annotated/redacted version before downstream states read it.

## Integration Map

### Files Modified
- `scripts/little_loops/loops/sft-corpus.yaml:25` — `pii_action: "flag"` context key
- `scripts/little_loops/loops/sft-corpus.yaml:262-297` — `check_pii` state (predicate 5)
- `scripts/little_loops/loops/sft-corpus.yaml:299-317` — `reject_pii` state
- `scripts/little_loops/loops/sft-corpus.yaml:239` — `check_files.on_yes: check_pii` routing
- `scripts/little_loops/loops/sft-corpus.yaml:260` — `reject_files.next: check_pii` routing
- `scripts/tests/test_loops_sft_corpus.py:498-810` — 16 PII tests across 4 classes

### Dependent Files (Callers/Importers)
- N/A — `sft-corpus.yaml` is a leaf loop file; no other loops or scripts reference it directly
- `scripts/little_loops/pii.py` — the PII module imported by `check_pii` (ENH-1885, `done`)

### Similar Patterns
- `check_issue_outcome` / `check_corrections` / `check_tools` / `check_files` in `sft-corpus.yaml` — the 4 existing quality predicates that `check_pii` follows
- `reject_issue_outcome` / `reject_corrections` / `reject_tools` / `reject_files` — the 4 existing reject states that `reject_pii` mirrors
- `dataset-curation.yaml:quality_gate` — alternative filter predicate using `output_numeric` evaluator

### Tests
- `scripts/tests/test_loops_sft_corpus.py:498-558` — `TestPiiFlagPassthrough` (3 tests)
- `scripts/tests/test_loops_sft_corpus.py:561-658` — `TestPiiRedact` (6 tests)
- `scripts/tests/test_loops_sft_corpus.py:661-753` — `TestPiiDiscard` (4 tests)
- `scripts/tests/test_loops_sft_corpus.py:756-810` — `TestPiiDefaultBehavior` (3 tests)
- `scripts/tests/test_pii.py` — PII module unit tests (ENH-1885 deliverable)
- `scripts/tests/test_builtin_loops.py:119` — auto-validates sft-corpus loads and validates

### Documentation
- `docs/reference/API.md` — documents `little_loops.pii` module API (ENH-1885)
- N/A — No documentation changes needed for this wiring (loop self-documents via comments)

## Scope Boundaries

- ✅ **In scope**: `pii_action` context key + `check_pii`/`reject_pii` states in `sft-corpus.yaml`; tests
- **Out of scope**: Changes to `little_loops.pii` (ENH-1885 is done); new PII pattern types; NLP-based PII detection

## Verification

- `ll-loop validate sft-corpus` → valid (14 states), exit 0
- `python -m pytest scripts/tests/test_loops_sft_corpus.py` → 33 passed (17 pre-existing + 16 PII)
- `python -m pytest scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_all_validate_as_valid_fsm` → passed
- `python -m pytest scripts/tests/test_pii.py` → all passed (ENH-1885 deliverable)
- `ruff check scripts/tests/test_loops_sft_corpus.py` → all checks passed

## Impact

- **Priority**: P4 — Low urgency; PII module exists and is tested, just unwired
- **Effort**: Small — Two new states (53 lines YAML total) + context key (1 line) + routing updates (2 lines) + 16 tests (~310 lines)
- **Risk**: Low — Additive only; defaults to `"flag"` (pass-through, no content change); unknown values fall through safely
- **Breaking Change**: No
- **Depends on**: ENH-1885 ✅ (pii module), ENH-1944 ✅ (sft-corpus quality predicates), ENH-1943 ✅ (lookup_session_metadata)

## Related

- ENH-1885 — `little_loops.pii` module (primary dependency; `done`)
- ENH-1944 — sft-corpus quality predicates (added the first 4 predicates this builds on; `done`)
- ENH-1943 — `lookup_session_metadata()` helper (enrich state dependency; `done`)
- FEAT-1826 — `sft-corpus` FSM loop (the file this modifies; `open`)
- ENH-1949 — dataset-curation parameters block (sibling handoff issue; `done`)
- EPIC-1880 — parent epic (SLM fine-tuning from session logs; `open`)

## Session Log
- `/ll:refine-issue` - 2026-06-04T20:55:22 - `992c93b5-ba45-42d7-986c-f2f1e2002ebc.jsonl`
- `hook:posttooluse-status-done` - 2026-06-04T20:55:11 - `992c93b5-ba45-42d7-986c-f2f1e2002ebc.jsonl`

- `/ll:format-issue` - 2026-06-04T20:09:28 - `4351963c-953f-4d5b-bad4-b310cea71f8f.jsonl`
- `/ll:capture-issue` - 2026-06-04T20:01:37Z - `b0ca5e28-1c3f-4a31-b1d5-f67d60516393.jsonl`
- `/ll:manage-issue` - 2026-06-04T21:55:00Z - `<current-session>`
- `/ll:refine-issue` - 2026-06-04T23:30:00Z - `<current-session>`

---

## Resolution

**Completed**: Added `pii_action` context key (`"flag"` default), `check_pii` predicate state (flag/redact/discard dispatch), and `reject_pii` rejection state to `sft-corpus.yaml`. Updated routing so the filter chain flows `check_files` → `check_pii` → `publish` (and `reject_files` → `check_pii`, `reject_pii` → `publish`). Added 16 tests across 4 test classes covering flag, redact, discard, and default behaviors. All 33 sft-corpus tests pass, `ll-loop validate sft-corpus` exits 0, auto-validation passes.

### Changes Made
- `scripts/little_loops/loops/sft-corpus.yaml` — added `pii_action: "flag"` context key, `check_pii` state (35 lines), `reject_pii` state (18 lines), routing updates (2 lines)
- `scripts/tests/test_loops_sft_corpus.py` — added 16 PII tests: `TestPiiFlagPassthrough` (3), `TestPiiRedact` (6), `TestPiiDiscard` (4), `TestPiiDefaultBehavior` (3)

### Verification
- `ll-loop validate sft-corpus` → valid (14 states), exit 0
- `python -m pytest scripts/tests/test_loops_sft_corpus.py` → 33 passed
- `python -m pytest scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_all_validate_as_valid_fsm` → passed
- `ruff check scripts/tests/test_loops_sft_corpus.py` → all checks passed

---

## Status

**Done** | Created: 2026-06-04 | Priority: P4
