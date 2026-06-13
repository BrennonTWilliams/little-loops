---
id: BUG-2117
title: loop-composer validate_plan crashes on catalog string interpolation
type: BUG
priority: P1
status: done
discovered_date: '2026-06-13'
discovered_by: audit-loop-run
captured_at: '2026-06-13T00:00:00Z'
labels:
- loops
- loop-composer
- fsm
- regression
- string-escaping
confidence_score: 99
completed_at: '2026-06-13T00:00:00Z'
---

# BUG-2117: loop-composer validate_plan crashes on catalog string interpolation

## Summary

The shared composer fragment library `validate_plan` state crashed with a Python
`SyntaxError` on **every** invocation, making both `loop-composer` and
`loop-composer-adaptive` unusable past plan validation. The bug was surfaced by an
audit of `loop-composer-adaptive` run `2026-06-13T175920`, which never reached plan
execution: it cycled `discover_loops → decompose_goal → parse_plan → validate_plan →
re_decompose` three times and terminated in `failed` after exhausting the decompose
retry budget — despite the LLM producing a structurally valid 3-step plan every time.

## Root Cause

- **File**: `scripts/little_loops/loops/lib/composer.yaml`
- **Anchor**: `validate_plan` fragment, line 107 (pre-fix)
- **Cause**: The fragment interpolated the captured catalog directly into a
  single-quoted Python string literal:

  ```python
  catalog_raw = '${captured.catalog.output}'
  ```

  At runtime the loop runner substituted the full multi-line catalog JSON (a
  pretty-printed `{project: [...], builtin: [...]}` of 70+ loops, ~17KB) into that
  literal. The catalog JSON contains newlines and both single and double quotes, so
  the resulting Python was unterminated:

  ```
  File "<stdin>", line 29
      catalog_raw = '{
                    ^
  SyntaxError: unterminated string literal
  ```

  Because the state uses `evaluate: { type: exit_code }`, the crash (`exit 1`) was
  indistinguishable from a legitimate "plan invalid" verdict, so the runner routed to
  `re_decompose` and burned the entire `max_replans` budget on blind retries — each
  re-decomposition received no feedback about why the prior plan was rejected, so all
  three attempts reproduced similar plans (~70s of wasted LLM time).

  The same fragment already read the *plan* file from disk
  (`composer-plan.json`); only the catalog was inlined.

## Steps to Reproduce

1. Run `loop-composer` or `loop-composer-adaptive` with any goal.
2. Observe the loop reach `validate_plan` and immediately fail with a Python
   `SyntaxError` (visible only in `validation_result.stderr`).
3. The loop retries decomposition up to `max_replans` and terminates `failed`,
   never reaching `execute_plan`.

## Expected Behavior

`validate_plan` parses the plan, cross-checks loop names against the catalog,
detects cycles, enforces the node cap, and writes `topo-order.json` on success.

## Actual Behavior

`validate_plan` crashed before any validation logic executed, on every run.

## Resolution

- **Action**: fix
- **Completed**: 2026-06-13
- **Status**: Completed (manual, this session)

### Changes

1. **Critical fix** (`scripts/little_loops/loops/lib/composer.yaml`): read the
   catalog from disk (`composer-catalog.json`, already written by `discover_loops`)
   instead of interpolating `${captured.catalog.output}` into a string literal.
   This is escaping-proof and matches how the fragment already reads the plan file.
   Fixes both `loop-composer` and `loop-composer-adaptive` (shared fragment).

2. **Blind-retry fix** (`loop-composer.yaml`, `loop-composer-adaptive.yaml`): added a
   `PREVIOUS VALIDATION ERRORS` block to the `decompose_goal` prompt, fed from
   `${captured.validation_result.output:default=...}`, so retries see the actual
   rejection reasons rather than re-deriving similar plans blindly. `:default=`
   keeps the first attempt clean.

3. **Regression tests** (`scripts/tests/test_loop_composer.py`): added
   `TestValidatePlanFragmentExecution` (4 tests) that *execute* the fragment Python
   (prior tests were purely structural, which is why this shipped): guards the
   string-literal anti-pattern from returning, confirms a valid plan passes and
   writes `topo-order.json`, confirms unknown-loop-name rejection via the disk
   catalog, and reproduces the exact quotes/newlines failure mode.

### Files Changed

- `scripts/little_loops/loops/lib/composer.yaml`
- `scripts/little_loops/loops/loop-composer.yaml`
- `scripts/little_loops/loops/loop-composer-adaptive.yaml`
- `scripts/tests/test_loop_composer.py`

### Verification Results

- `ll-loop validate loop-composer` / `loop-composer-adaptive`: both valid.
- `python -m pytest scripts/tests/test_loop_composer.py
  scripts/tests/test_loop_composer_adaptive.py`: **88 passed** (84 prior + 4 new).

## Audit Proposals Not Actioned (with rationale)

- **`diff_stall` evaluator on `validate_plan`** (audit #3): declined. After the
  catalog fix the deterministic crash is gone, and the error-feedback fix makes
  retries vary; `max_replans` already bounds waste to 3 attempts. Reconsider only if
  LLMs are observed stubbornly repeating identical invalid plans.
- **`capture_file` for `validation-errors.txt`** (audit #4): declined as redundant —
  errors are printed to stdout and captured in `validation_result.output`, which the
  error-feedback fix now surfaces.
- **"Retry counter not cleaned up"** (audit structural obs.): invalid concern.
  `decompose-retries.txt` lives under per-run-isolated `${context.run_dir}`
  (`.loops/runs/<loop>-<ts>/`); a stale cross-run counter cannot occur.

## Follow-up (open)

- The audit's appendix noted the run had an **empty `goal`** yet still produced a
  plan; `required_inputs: ["goal"]` does not reject an empty string. Tracked
  separately — not part of this fix.

## Session Log
- `hook:posttooluse-status-done` - 2026-06-13T18:27:30 - `ee353f27-a9c0-4b18-9ab1-282ea1c38a32.jsonl`
- audit-loop-run (manual) - 2026-06-13 - source: `audit-loop-composer-adaptive-2026-06-13.md`
- manual fix + tests - 2026-06-13
