---
id: BUG-2127
title: general-task loop — verify_step false-pass on non-Python tasks and unbounded
  per-step retry spin
type: BUG
priority: P2
status: done
captured_at: '2026-06-13T19:15:00Z'
completed_at: '2026-06-13T19:15:00Z'
discovered_date: '2026-06-13'
relates_to:
- BUG-1766
size: Medium
---

# BUG-2127: general-task loop — verify_step false-pass on non-Python tasks and unbounded per-step retry spin

## Summary

Two correctness defects in the built-in `general-task` loop
(`scripts/little_loops/loops/general-task.yaml`), found while reviewing the loop
for improvements. Both undermine the loop's "general-purpose" claim:

1. **verify_step was Python-only.** The per-step verification gate hardcoded
   `python -m pytest $FILES` and matched on the strings `passed|no tests ran`.
   For any non-Python task (docs, YAML, JS, shell) pytest collected nothing →
   matched `"no tests ran"` → emitted a false `VERIFY_PASS`. The gate was a
   silent no-op for the majority of general tasks, shifting all real
   verification onto `check_done` + `count_done` while still paying a full shell
   round-trip with near-zero discriminating power.
2. **A step whose files never pass verify spins to max_iterations.** On
   `VERIFY_FAIL`, control flows `verify_step → continue_work → select_step`,
   which re-selects the **same** first unchecked step (it was never marked
   `[x]`) → `do_work` redoes it → fails again. The `repeated_failure` circuit
   (window 3) never trips: `do_work` *succeeds*, and `verify_step`'s `on_no` is
   a verdict, not a state failure. The only escape was the global
   `max_iterations: 200` cap — a long, expensive spin.

## Root Cause

- **File**: `scripts/little_loops/loops/general-task.yaml`
- **verify_step**: `if python -m pytest $FILES --tb=short -q 2>&1 | tail -1 |
  grep -qE "passed|no tests ran"` — hardcoded runner + output-string gating that
  only bites Python and false-passes on empty collection.
- **select_step**: no per-step attempt accounting, so a step is re-selectable an
  unbounded number of times without ever being marked done or abandoned.

## Resolution

- **Status**: Done
- **Closed**: 2026-06-13

### Fix #1 — config-driven, language-agnostic verify_step

`verify_step` now resolves its command from `${context.test_cmd}` (override) →
`project.test_cmd` in `.ll/ll-config.json` → bare `pytest` fallback, mirroring
the established pattern in `test-coverage-improvement.yaml`. It gates on the
command's **exit code** instead of grepping pytest output, so it works for any
test runner (`npm test`, `cargo test`, …). Output is captured to
`${context.run_dir}/verify-output.txt` for diagnosis.

### Fix #2 — per-step attempt cap in select_step

`select_step` counts attempts per exact step line in
`${context.run_dir}/step-attempts.txt`. Once a step reaches
`${context.max_step_attempts}` (default 3), it is marked `[x]` with an
`(abandoned: verify failed after N attempts)` note and the loop falls through to
`check_done` via the existing `on_no` edge — so the DoD machinery, not an
unbounded retry, decides whether the underlying criterion is satisfied. The two
fixes compose: a project whose suite is already red abandons each step after 3
tries and moves on instead of spinning.

New context vars: `test_cmd: ""` and `max_step_attempts: 3`.

## Files Modified

- `scripts/little_loops/loops/general-task.yaml`
  - `context:` — added `test_cmd` and `max_step_attempts`
  - `verify_step` — config-driven, exit-code gating (Fix #1)
  - `select_step` — per-step attempt cap with abandonment (Fix #2)

## Verification

- Resolved routing graph **byte-identical** before/after (proved via edge-set
  diff) — both fixes are internal to shell states; no topology change. The
  `STEP_ABANDONED` output routes via the pre-existing `select_step.on_no →
  check_done` edge.
- `ll-loop validate general-task` — valid.
- Config snippet confirmed to resolve `python -m pytest scripts/tests/` from
  `.ll/ll-config.json`.
- `pytest scripts/tests/test_general_task_loop.py` — 119 passed.
- `pytest scripts/tests/test_builtin_loops.py` — passed.

## Impact

The per-step verification gate now provides real signal for non-Python projects,
and a stuck step can no longer burn the full 200-iteration budget. No behavior
change for Python projects whose `project.test_cmd` is the pytest invocation.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-14T00:13:18 - `5b0c8c3b-50ed-4331-b2d7-bc48c1fba491.jsonl`
