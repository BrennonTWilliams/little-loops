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

`little_loops.pii` (ENH-1885) is implemented and tested — `detect_pii()`, `redact_pii()`, and `apply_pii_action()` all work — but nothing in `sft-corpus.yaml` calls it. The `pii_action` context key (`"flag" | "redact" | "discard"`) is defined in FEAT-1826's API spec but missing from the loop's actual context block, and no filter state invokes PII detection. Wire `apply_pii_action()` into the filter predicate chain so the `pii_action` config key actually does something.

## Current Behavior

ENH-1885 delivered `scripts/little_loops/pii.py` with three public functions:
- `detect_pii(text)` → `list[str]` (email, phone, SSN)
- `redact_pii(text)` → `str` (replaces with `[EMAIL]`/`[PHONE]`/`[SSN]`)
- `apply_pii_action(example, action)` → `dict | None` (flag/redact/discard dispatch)

All three are tested and importable. But `sft-corpus.yaml`:
- Has no `pii_action` key in its context block
- Has no state calling `apply_pii_action()`
- The `filter` predicate chain (`check_issue_outcome → check_corrections → check_tools → check_files → publish`) has no PII step

ENH-1885's scope explicitly deferred this wiring: "Wire `loops/sft-corpus.yaml` filter state to call `apply_pii_action(example, context.pii_action)` — note: this file does not exist yet (FEAT-1826 deliverable); this step applies when FEAT-1826 creates the loop, not in this ENH." FEAT-1826's 5 remaining gaps don't mention PII at all.

## Expected Behavior

1. `sft-corpus.yaml` context block includes `pii_action: "flag"` with valid values `"flag" | "redact" | "discard"`, defaulting to `"flag"` (pass-through annotation, no content modification)
2. A PII check state runs in the filter predicate chain (after enrich, parallel to the 4 quality predicates), calling `apply_pii_action()` on each example
3. When `pii_action: "redact"` — PII spans are replaced with `[TYPE]` placeholders before downstream states process the example
4. When `pii_action: "discard"` — examples with detected PII are rejected and logged to `rejections.jsonl` with reason `"pii_detected"`
5. When `pii_action: "flag"` — examples pass through with `pii_detected: true` annotation, no rejection
6. Graceful degradation: the PII check is a no-op pass-through when `pii_action` is unset or `"flag"`

## Motivation

`pii_action: "redact"` in the config is currently a dead key — user data goes out unfiltered regardless of setting. The PII module exists, works, and is tested; it just needs to be called from the loop. Closing this gap makes the `pii_action` context key functional, completing the work ENH-1885 started.

## Success Metrics

- **PII detection rate**: 100% of examples with emails, phone numbers, or SSNs flagged when `pii_action` is set
- **Redaction coverage**: All detected PII spans replaced with `[EMAIL]`/`[PHONE]`/`[SSN]` placeholders when `pii_action: "redact"`
- **Rejection accuracy**: Examples with PII correctly rejected and logged to `rejections.jsonl` with reason `"pii_detected"` when `pii_action: "discard"`
- **Pass-through correctness**: No modification or rejection when `pii_action: "flag"` or unset
- **Test coverage**: 4 tests covering flag, redact, discard, and default behaviors

## Implementation Steps

1. **Add `pii_action` to `sft-corpus.yaml` context block:**
   ```yaml
   pii_action: "flag"  # flag | redact | discard
   ```

2. **Add a `check_pii` state** in the filter predicate chain — insert after `check_files` and before `publish` (or wherever the chain routing allows):
   ```yaml
   check_pii:
     action_type: shell
     action: |
       python3 << 'PYEOF'
       import json, sys
       sys.path.insert(0, "scripts")
       from little_loops.pii import apply_pii_action

       action = "${context.pii_action}"
       if action == "flag":
           print(1)
           sys.exit()

       with open("${captured.enrich_output.output}") as f:
           example = json.loads(f.readline())

       result = apply_pii_action(example, action)
       if result is None:
           print(0)  # discard
       else:
           # Write back redacted/flagged version
           with open("${captured.enrich_output.output}", "w") as f:
               json.dump(result, f)
           print(1)
       PYEOF
     evaluate:
       type: output_numeric
       operator: eq
       target: 1
     on_yes: publish
     on_no: reject_pii
   ```

3. **Add `reject_pii` state** — append `{path, score: 0, reason: "pii_detected", timestamp}` to rejections log (following the pattern of the 4 existing reject states).

4. **Update routing** — point the last quality predicate's `on_yes` at `check_pii` instead of `publish`.

5. **Tests** — add to `scripts/tests/test_loops_sft_corpus.py`:
   - `test_pii_flag_passthrough` — example with PII passes when `pii_action: "flag"`
   - `test_pii_redact_replaces_spans` — email/phone/SSN replaced with placeholders
   - `test_pii_discard_rejects_example` — example dropped, logged to rejections
   - `test_pii_action_unset_defaults_to_flag` — no key = pass-through

## Integration Map

### Files to Modify
- `loops/sft-corpus.yaml` — Add `pii_action` context key, `check_pii` state, `reject_pii` state, and routing updates

### Dependent Files (Callers/Importers)
- N/A — `sft-corpus.yaml` is a leaf loop file; no other loops or scripts reference it directly

### Similar Patterns
- `reject_low_quality` / `reject_no_tools` / `reject_no_files` / `reject_uncorrected` states in `sft-corpus.yaml` — the new `reject_pii` state follows the same pattern (append to `rejections.jsonl`)

### Tests
- `scripts/tests/test_loops_sft_corpus.py` — Add 4 PII-specific tests (listed in Implementation Steps)

### Documentation
- N/A — No documentation changes needed

### Configuration
- N/A — No configuration file changes beyond the loop YAML itself

## Scope Boundaries

- **In scope**: Add `pii_action` context key + `check_pii`/`reject_pii` states to `sft-corpus.yaml`; tests
- **Out of scope**: Changes to `little_loops.pii` (ENH-1885 is done); new PII pattern types; NLP-based PII detection

## API/Interface

N/A — No public API changes. This enhancement only modifies the `sft-corpus.yaml` loop YAML and adds tests. The `little_loops.pii` module's public interface (`detect_pii`, `redact_pii`, `apply_pii_action`) remains unchanged (ENH-1885 scope, already delivered).

## Impact

- **Priority**: P4 — Low urgency; PII module exists and is tested, just unwired
- **Effort**: Small — Two new states (~30 lines YAML each) + context key + ~4 tests
- **Risk**: Low — Additive only; defaults to `"flag"` (pass-through, no content change)
- **Breaking Change**: No
- **Depends on**: ENH-1885 ✅ (pii module), ENH-1944 ✅ (sft-corpus.yaml exists)

## Related

- ENH-1885 — `little_loops.pii` module (primary dependency; done)
- FEAT-1826 — `sft-corpus` FSM loop (the file this modifies; open)
- EPIC-1880 — parent epic (SLM fine-tuning from session logs)

## Labels

`enhancement`, `sft`, `pii`, `loop`

## Session Log
- `/ll:format-issue` - 2026-06-04T20:09:28 - `4351963c-953f-4d5b-bad4-b310cea71f8f.jsonl`
- `/ll:capture-issue` - 2026-06-04T20:01:37Z - `b0ca5e28-1c3f-4a31-b1d5-f67d60516393.jsonl`
- `/ll:manage-issue` - 2026-06-04T21:55:00Z - `<current-session>`

---
## Resolution

**Completed**: Added `pii_action` context key (`"flag"` default), `check_pii` predicate state (flag/redact/discard dispatch), and `reject_pii` rejection state to `sft-corpus.yaml`. Updated routing so the filter chain flows `check_files` → `check_pii` → `publish` (and `reject_files` → `check_pii`, `reject_pii` → `publish`). Added 16 tests across 4 test classes covering flag, redact, discard, and default behaviors. All 33 sft-corpus tests pass, `ll-loop validate sft-corpus` exits 0, auto-validation passes.

### Changes Made
- `scripts/little_loops/loops/sft-corpus.yaml` — added `pii_action: "flag"` context key, `check_pii` state (34 lines), `reject_pii` state (18 lines), routing updates
- `scripts/tests/test_loops_sft_corpus.py` — added 16 PII tests: `TestPiiFlagPassthrough` (3), `TestPiiRedact` (6), `TestPiiDiscard` (4), `TestPiiDefaultBehavior` (3)

### Verification
- `ll-loop validate sft-corpus` → valid (14 states), exit 0
- `python -m pytest scripts/tests/test_loops_sft_corpus.py` → 33 passed
- `python -m pytest scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_all_validate_as_valid_fsm` → passed
- `ruff check scripts/tests/test_loops_sft_corpus.py` → all checks passed

---
## Status

**Done** | Created: 2026-06-04 | Priority: P4
