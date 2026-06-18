---
id: ENH-2135
title: Harden error-routing in loop-composer and loop-composer-adaptive (re_decompose
  on_error, check_auto_plan error → HITL gate)
type: ENH
priority: P3
status: done
captured_at: '2026-06-13T21:18:00Z'
completed_at: '2026-06-13T21:18:00Z'
discovered_date: '2026-06-13'
relates_to:
- FEAT-1809
size: Small
---

# ENH-2135: Harden error-routing in loop-composer and loop-composer-adaptive

## Summary

Two error-routing gaps in the composer loop pair
(`scripts/little_loops/loops/loop-composer.yaml` and
`loop-composer-adaptive.yaml`) left evaluator states without an explicit
`on_error` route and routed one error case to silent auto-execution. Both
were surfaced by `/ll:review-loop` (QC-2: missing `on_error` on a shell
evaluator state). The fixes restore error-routing consistency so every
pre-execution evaluator failure terminates explicitly rather than hitting an
unhandled-error stop, and ensure an error in the auto-approve gate falls back
to the human-in-the-loop approval path rather than auto-executing an
unapproved plan.

## Root Cause

- **Files**: `scripts/little_loops/loops/loop-composer.yaml`,
  `scripts/little_loops/loops/loop-composer-adaptive.yaml`
- **Anchors**: state `re_decompose` (both loops); state `check_auto_plan`
  (static `loop-composer` only).
- **Cause**:
  1. `re_decompose` is a `shell` state with an `output_numeric` evaluator
     (retry counter `< 3`) but defined only `on_yes`/`on_no` — no `on_error`.
     Every sibling evaluator state in these loops routes errors explicitly;
     `re_decompose` was the lone gap. An evaluator failure (e.g. non-numeric
     output) would be treated as an unhandled error instead of routing to the
     `failed` terminal like its neighbors.
  2. In the static `loop-composer`, `check_auto_plan` routed
     `on_error: execute_plan` — an error evaluating the auto-approve gate would
     execute the plan *without* HITL approval, the less-safe default.

## Resolution

- **Status**: Done
- **Closed**: 2026-06-13

### `re_decompose` — add `on_error` (both loops)

```yaml
# Before
    on_yes: decompose_goal
    on_no: failed

# After
    on_yes: decompose_goal
    on_no: failed
    on_error: failed
```

Pre-execution evaluator errors now terminate explicitly via the `failed`
terminal, consistent with `decompose_goal` and `parse_plan` (which already
route errors to `failed`/`re_decompose`).

### `check_auto_plan` — error falls back to HITL gate (`loop-composer` only)

```yaml
# Before
    on_yes: execute_plan
    on_no: present_plan
    on_error: execute_plan

# After
    on_yes: execute_plan
    on_no: present_plan
    on_error: present_plan
```

On error, route to the human approval gate (`present_plan`) rather than
silently auto-executing an unapproved plan — fail safe, not fail open.

## Files Modified

- `scripts/little_loops/loops/loop-composer-adaptive.yaml` — `re_decompose`
  gains `on_error: failed` (applied via `/ll:review-loop loop-composer-adaptive`).
- `scripts/little_loops/loops/loop-composer.yaml` — `re_decompose` gains
  `on_error: failed`; `check_auto_plan` `on_error` changed from `execute_plan`
  to `present_plan`.

## Verification

- `ll-loop validate loop-composer-adaptive` — valid, 0 errors / 0 warnings.
- `ll-loop validate loop-composer` — valid.
- `ll-loop simulate loop-composer-adaptive` — terminates cleanly at
  `abort_composer` in 10 iterations under the default failure scenario; no
  stall, no max-iterations overrun.
- `/ll:review-loop loop-composer-adaptive` composite scorecard: 28/30
  (Resilience 4/5 after fix).

## Impact

Closes the single error-routing gap that kept the composer pair from having
fully universal `on_error` discipline, and removes a fail-open path where an
auto-approve-gate error would have executed an unapproved plan. Both are
robustness-only changes with no happy-path behavior difference.

Review artifact: `.loops/reviews/loop-composer-adaptive-20260614-021846.md`.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-14T02:23:15 - `0594bfb6-edae-46bb-918e-ee20c55eb241.jsonl`
