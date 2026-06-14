---
id: ENH-2128
title: FSM validator recognizes :default= guard in capture-reachability check (BUG-2112
  Approach B)
type: ENH
priority: P3
status: done
captured_at: '2026-06-13T19:15:00Z'
completed_at: '2026-06-13T19:15:00Z'
discovered_date: '2026-06-13'
relates_to:
- BUG-2112
- BUG-2094
- ENH-1961
size: Small
---

# ENH-2128: FSM validator recognizes :default= guard in capture-reachability check (BUG-2112 Approach B)

## Summary

Implements the deferred **Approach B** from BUG-2112. The capture-reachability
validator (`_validate_capture_reachability` in `scripts/little_loops/fsm/validation.py`)
was suffix-blind: its extraction regex `\$\{captured\.(\w+)` could not see a
`:default=` guard, so it emitted bypass-path WARNINGs even for references that
are provably safe. BUG-2112 chose Approach A (add `:default=` everywhere, keep
the warnings in `TestValidatorWarningBudget.ALLOWLIST`) precisely because the
validator could not self-suppress. This change teaches the validator to parse
the suffix, making the warnings disappear and retiring the "Bucket B" allowlist
entries.

## Root Cause

- **File**: `scripts/little_loops/fsm/validation.py`
- **Anchor**: `_validate_capture_reachability()` reference-extraction step (used
  `_CAPTURED_REF_RE`, which captures only the var name).
- **Cause**: A reference written `${captured.x.output:default=fallback}` is safe
  even on paths that bypass the capturing state — the interpolation engine
  (`interpolation.py`, `${path:default=value}`) substitutes the default when the
  path is missing. The validator extracted `x` regardless of the guard and
  flagged it, producing false-positive WARNINGs.

## Resolution

- **Status**: Done
- **Closed**: 2026-06-13
- **Approach**: B (the alternative BUG-2112 documented but did not take)

### Validator change

Added `_CAPTURED_REF_FULL_RE` (captures var name + remainder up to `}`) and
`_unguarded_captured_refs(text)`, which returns a captured var only if it has at
least one reference **without** a `:default=` guard. Wired it into the
reference-extraction step so both the bypass-path check and the missing-capture
check skip fully-guarded references. A var with a mix of guarded and unguarded
references still warns (any unguarded occurrence is unsafe).

### Allowlist cleanup

The fix cleared 17 allowlisted false positives across 11 loops (all "Bucket B"
`:default=`-guarded entries). Removed them from
`TestValidatorWarningBudget.ALLOWLIST` in `test_builtin_loops.py`, keeping the 4
genuine "Bucket A" entries — captures injected by a child loop's namespace, which
the static validator legitimately cannot resolve:
`adopt-third-party-api` (build_playbook, build_playbook_partial),
`examples-miner` (synthesize), `goal-cluster` (reassess),
`integrate-sdk` (scaffold_integration).

`general-task` now validates with **0 warnings** (was 4).

## Files Modified

- `scripts/little_loops/fsm/validation.py` — `_CAPTURED_REF_FULL_RE`,
  `_unguarded_captured_refs()`, wired into `_validate_capture_reachability`.
- `scripts/tests/test_fsm_validation.py` — 3 new cases in
  `TestCaptureReachabilityValidation`: guarded-bypass → no warning,
  guarded-missing → no error, mixed guarded/unguarded → still warns.
- `scripts/tests/test_builtin_loops.py` — retired Bucket B `ALLOWLIST` entries;
  updated the rationale comment to reflect Approach B.

## Verification

- `pytest scripts/tests/test_fsm_validation.py` + `test_builtin_loops.py` — 999
  passed (includes `TestValidatorWarningBudget` no-stale-entries gate).
- `pytest scripts/tests/test_general_task_loop.py` — 119 passed.
- `mypy scripts/little_loops/fsm/validation.py` — clean.
- `ruff check` — clean.
- Validated every built-in loop — no new ERRORs introduced.

## Impact

Removes false-positive validator noise for the documented `:default=` guard
pattern across all loops, and retires standing allowlist tech debt so future
genuine capture-ordering regressions surface instead of hiding behind a broad
allowlist.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-14T00:13:48 - `5b0c8c3b-50ed-4331-b2d7-bc48c1fba491.jsonl`
