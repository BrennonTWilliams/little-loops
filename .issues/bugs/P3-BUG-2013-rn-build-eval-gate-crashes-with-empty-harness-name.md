---
id: BUG-2013
title: "rn-build \u2014 eval_gate crashes with empty harness name when eval_harness\
  \ errors"
type: BUG
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-06-08T01:29:25Z'
completed_at: '2026-06-08T01:51:14Z'
discovered_date: 2026-06-08
discovered_by: capture-issue
size: Small
blocked_by:
- FEAT-1992
relates_to:
- FEAT-1990
- FEAT-1992
labels:
- loops
- rn-build
- bug
confidence_score: 100
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2013: `rn-build` — `eval_gate` crashes with empty harness name when `eval_harness` errors

## Summary

When the `eval_harness` state errors, `on_error: cluster_execute` bypasses
harness setup and leaves `captured.harness_name.output` empty. The subsequent
`eval_gate` state then attempts `loop: "${captured.harness_name.output}"` with
an empty string, which fails opaquely — the FSM executor cannot resolve an
empty loop name and the run crashes without a meaningful error message.

## Current Behavior

When `eval_harness` errors in `rn-build.yaml`, the `on_error: cluster_execute` path bypasses harness name extraction (`read_harness_name` state). The subsequent `eval_gate` state evaluates `loop: "${captured.harness_name.output}"` with an empty string. The FSM executor's `resolve_loop_path` receives `""` and raises an unhandled exception, crashing the run without a meaningful error message.

## Steps to Reproduce

1. Run `ll-loop run rn-build` against a spec where `eval_harness` will error (e.g., network failure, harness install failure, or LLM timeout).
2. Confirm `eval_harness` errors and routes to `cluster_execute` via `on_error`.
3. Allow `cluster_execute` to complete and route to `eval_gate`.
4. Observe: the FSM executor crashes with an unhandled exception; no meaningful error message is surfaced.

## Root Cause

**File**: `scripts/little_loops/loops/rn-build.yaml`

**States**: `eval_harness` → `cluster_execute` (on_error path) → `eval_gate`

`eval_harness` (line ~186) has `on_error: cluster_execute`, which skips both
the harness name extraction in `read_harness_name` and the harness name write
to `${context.run_dir}/harness-name.txt`. When `cluster_execute` finishes and
routes to `eval_gate` (line ~280), `eval_gate` evaluates:
```yaml
loop: "${captured.harness_name.output}"
```
`captured.harness_name` was never populated, so the interpolation resolves to
an empty string. The FSM executor's `resolve_loop_path` receives `""` and
raises an unhandled exception.

## Expected Behavior

When `harness_name` is empty or unset after `cluster_execute`, `rn-build`
should skip the eval gate entirely and route to `synthesize_result` with
`eval_passed: false` rather than crashing. The synthesis JSON should note that
harness evaluation was skipped due to harness setup failure.

## Proposed Solution

Add a `check_harness_name` shell state between `cluster_execute` and
`eval_gate` that tests whether `captured.harness_name.output` is non-empty:

```yaml
check_harness_name:
  action_type: shell
  action: |
    NAME="${captured.harness_name.output:-}"
    if [ -z "$NAME" ]; then
      echo "no_harness"
      exit 1
    fi
    echo "$NAME"
  evaluate:
    type: exit_code
  on_yes: eval_gate
  on_no: synthesize_result
  on_error: synthesize_result
```

Update `cluster_execute.on_yes` / `on_no` / `on_error` to route to
`check_harness_name` instead of `eval_gate` directly.

## Implementation Steps

1. Add `check_harness_name` shell state to `rn-build.yaml` between `cluster_execute` and `eval_gate`
2. Update `cluster_execute` routing: `on_yes/on_no/on_error` → `check_harness_name`
3. Add a test to `scripts/tests/test_rn_build.py`: `test_check_harness_name_routes_to_synthesize_when_empty`
4. Run `ll-loop validate rn-build.yaml` and `pytest scripts/tests/test_rn_build.py -v`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-build.yaml` — add `check_harness_name` state; update `cluster_execute` routing
- `scripts/tests/test_rn_build.py` — add guard test

### Dependent Files (Callers/Importers)
- N/A — `rn-build.yaml` is a self-contained loop; routing is internal state machine transitions

### Similar Patterns
- Other guard states in `rn-build.yaml` that validate intermediate captured values before routing downstream

### Tests
- `scripts/tests/test_rn_build.py` — add `test_check_harness_name_routes_to_synthesize_when_empty`

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- `ll-loop validate rn-build.yaml` passes with no errors.
- `cluster_execute` routes to `check_harness_name`, not `eval_gate`.
- `check_harness_name` routes to `synthesize_result` when harness name is empty.
- `check_harness_name` routes to `eval_gate` when harness name is set.
- New test `test_check_harness_name_routes_to_synthesize_when_empty` passes.

## Impact

- **Priority**: P3 — triggered any time `eval_harness` errors (network failure,
  harness install failure, LLM timeout); produces an opaque crash
- **Effort**: Small — one new guard state, routing update, one test
- **Risk**: Low — purely additive; does not change the happy path
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-08

## Session Log
- `/ll:ready-issue` - 2026-06-08T01:48:14 - `19613609-a3d9-4bff-a948-8681f232210c.jsonl`
- `/ll:confidence-check` - 2026-06-08T02:00:00Z - `444d6dd7-7cec-47b3-ae6e-d9e1d7a9e8bc.jsonl`
- `/ll:format-issue` - 2026-06-08T01:35:29 - `607880e5-794c-461f-a405-8b9dc39719f8.jsonl`
- `/ll:capture-issue` - 2026-06-08T01:29:25Z - `00fefddf-56f7-43f8-8a57-dd53f6c3526d.jsonl`
