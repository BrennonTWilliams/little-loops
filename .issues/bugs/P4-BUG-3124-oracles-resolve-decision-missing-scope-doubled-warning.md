---
id: BUG-3124
type: BUG
title: '`oracles/resolve-decision.yaml` missing `scope:` doubled the no-scope
  warning on `ll-loop validate sprint-refine-and-implement`'
priority: P4
status: done
captured_at: '2026-08-09T00:11:03Z'
discovered_date: 2026-08-09
discovered_by: user-report
labels:
- loop-authoring
- fsm-concurrency
- validation
relates_to:
- BUG-3088
- BUG-3106
- BUG-3107
completed_at: '2026-08-09T00:11:03Z'
---

# BUG-3124: `oracles/resolve-decision.yaml` missing `scope:` doubled the no-scope warning

## Summary

`ll-loop validate sprint-refine-and-implement` printed the BUG-3107 no-scope
WARNING twice, plus one `required_inputs` WARNING, even though
`sprint-refine-and-implement.yaml` itself already declares `scope: ["."]`.
The doubled warning was misleading — it looked like the requested loop's own
scope declaration wasn't taking effect.

## Root Cause

`_validate_with_bindings()` (`fsm/validation/structural_rules.py:258`)
recursively runs full validation on every child loop reachable via a
`loop:` + `with:` state, and `load_and_validate()` prints each WARNING via
`logger.warning(str(warning))` (`structural_rules.py:1679`) as a side effect
of loading — independent of the caller's own returned-and-deduped violation
list. Tracing the call chain:

```
sprint-refine-and-implement (scope: ["."], no warning)
  -> auto-refine-and-implement (scope declared, no warning; but input_key: scope
     with no required_inputs -> 1x required_inputs warning)
    -> autodev (scope declared, no warning)
      -> oracles/resolve-decision  (state: two `loop:`+`with:` call sites,
         lines 551 and 567 of autodev.yaml)
```

`oracles/resolve-decision.yaml` declared no `scope:`. Because `autodev.yaml`
calls it from *two* separate states, `_validate_with_bindings` recursively
loaded and validated it twice, printing the same no-scope WARNING each time
— exactly matching the two warnings observed. This loop was one of the 12
`oracles/*.yaml` sub-loops allowlisted as scope-exempt in
`test_builtin_loops.py` pending the BUG-3107 follow-up.

## Fix

- Added `scope: [".issues/", "${context.run_dir}"]` to
  `scripts/little_loops/loops/oracles/resolve-decision.yaml` — it writes
  `decide-options-deposited-*`/`decide-rate-limited-*` markers under
  `run_dir` and mutates the target issue under `.issues/` via
  `/ll:refine-issue` and `/ll:decide-issue`, matching the same pattern
  already used by the sibling `refine-to-ready-issue.yaml`.
- Removed `resolve-decision` from `_SCOPE_EXEMPT_STEMS` and the
  `("resolve-decision", "no-scope")` entry in `TestValidatorWarningBudget`'s
  `ALLOWLIST` (`scripts/tests/test_builtin_loops.py`), since it's no longer
  exempt.

`ll-loop validate sprint-refine-and-implement` now prints only the (expected,
still-allowlisted) `required_inputs` warning for `auto-refine-and-implement`.
Full suite verified: `python -m pytest scripts/tests/test_builtin_loops.py`
— 1459 passed.

## Out of Scope

The other 11 `oracles/*.yaml` sub-loops (`code-run-gate`,
`enumerate-and-prove`, `generator-evaluator`, `generator-evaluator-cli`,
`generator-evaluator-flux`, `integrate-node`, `oracle-capture-issue`,
`plan-node-refine`, `plan-research-iteration`, `research-coverage`,
`verify-confidence-scores`) still lack `scope:` and remain allowlisted —
that's the pre-existing BUG-3107 follow-up, untouched here.

## Impact

- **Severity**: low — cosmetic/diagnostic-output confusion only; no runtime
  behavior changed (validate output doesn't gate `ll-loop run`).
- **Blast radius**: one loop YAML (`scope:` addition) plus one test-file
  allowlist entry removed.

## Files Changed

- `scripts/little_loops/loops/oracles/resolve-decision.yaml`
- `scripts/tests/test_builtin_loops.py`

## Status

done

## Resolution

- **Status**: Fixed
- **Completed**: 2026-08-09T00:11:03Z
- **Verification**: `ll-loop validate sprint-refine-and-implement` no longer
  emits the no-scope warning; `python -m pytest scripts/tests/test_builtin_loops.py`
  passes (1459 passed).


## Session Log
- `hook:posttooluse-status-done` - 2026-08-09T00:11:28 - `3f5cbf8b-2803-481d-8698-98488887ab05.jsonl`
