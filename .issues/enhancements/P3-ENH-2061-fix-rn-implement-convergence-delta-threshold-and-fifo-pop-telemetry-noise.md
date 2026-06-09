---
id: ENH-2061
title: "Fix rn-implement/rn-remediate: convergence delta threshold too sensitive and fifo_pop exit-code telemetry noise"
type: ENH
priority: P3
status: done
captured_at: '2026-06-09T19:40:55Z'
completed_at: '2026-06-09T19:40:55Z'
discovered_date: '2026-06-09'
discovered_by: capture-issue
labels:
- loops
- rn-implement
- rn-remediate
- telemetry
---

# ENH-2061: Fix rn-implement/rn-remediate: convergence delta threshold too sensitive and fifo_pop exit-code telemetry noise

## Summary

Two actionable findings from the 2026-06-09 rn-implement loop audit (`rn-implement-audit-2026-06-09.md`) were identified and fixed. Two other findings were evaluated and deliberately not implemented.

## Findings Addressed

### Finding 3 — Convergence delta threshold too sensitive (Fixed)

**File**: `scripts/little_loops/loops/rn-remediate.yaml`, `check_convergence` state

**Problem**: `check_convergence` used `TOTAL_DELTA -le 2` as the stall threshold. With only 4 integer-scored dimensions (confidence, outcome, complexity, ambiguity), a genuine improvement of +1 in any single dimension produces `total_delta=1`, which is ≤2 — triggering `CONVERGED_STALLED` or `NEEDS_MANUAL_REVIEW` instead of routing `CONVERGED_IMPROVED` for another remediation pass. The 2026-06-09 run correctly stalled (total_delta=0), but a future run where `decide` resolves ambiguity (complexity drops 2, outcome gains 1 → total_delta=3) would have been allowed through while a partial improvement of +1 would not.

**Fix**: Changed threshold from `TOTAL_DELTA -le 2` to `TOTAL_DELTA -le 0`. Only a zero-change result now triggers stall; any measurable improvement routes `CONVERGED_IMPROVED` for another pass.

### Finding 4 — fifo_pop/select_next exit-code 1 pollutes telemetry (Fixed)

**File**: `scripts/little_loops/loops/rn-implement.yaml`, `fifo_pop` and `select_next` states

**Problem**: Both `fifo_pop` and `select_next` exited with code 1 when the queue was empty — the expected "all issues processed" path. The `queue_pop` fragment evaluator (`type: exit_code`) treated exit 1 as a `no` verdict and routed correctly to `report`, but telemetry consumers scanning for `exit_code != 0` would flag these as action failures (false positives). The 2026-06-09 audit noted 2 such `exit_code: 1, verdict: "no"` events per run as expected noise.

**Fix**:
- Both states now emit `QUEUE_EMPTY` + exit 0 on empty-queue / no-candidates conditions.
- Overrode the `queue_pop` fragment's default `exit_code` evaluator with `output_contains: pattern: QUEUE_EMPTY` in each state.
- Inverted routing: `on_yes: report` / `on_no: check_blocked_by` (was `on_yes: check_blocked_by` / `on_no: report`).
- For `select_next`, the shell guard (`if [ -z "$CHOSEN" ]`) also emits `QUEUE_EMPTY` + exit 0 instead of bare exit 1, covering the "candidates exhausted by dep/blocked filtering" path.

## Findings Evaluated But Not Implemented

### Finding 1 — Outcome tolerance band (Deferred, policy choice)

The audit proposed an `outcome_tolerance: 2` context variable to let issues within 2 points of `outcome_threshold` proceed to implement with a warning. The audit itself labels this "a policy choice, not a correctness fix" — the current blocking behavior is correct-by-contract. Deferred pending more data on how often marginal threshold cases recur.

### Finding 2 — Verdict laundering: differentiate on_yes/on_no for run_remediation/run_decomposition (Not implemented — audit fix was incorrect)

The audit flagged `on_success == on_failure → classify_remediation` in `run_remediation` and `run_decomposition` as verdict laundering. The proposed fix (routing `on_failure` to `record_sub_loop_crash`) would misclassify all legitimate rn-remediate terminations as crashes. The design is intentional (ENH-2005): every path to rn-remediate's `failed` terminal goes through an `emit_*` state that writes the outcome token first. `on_error` (not `on_failure`) is the correct crash path, and it already routes to `record_sub_loop_crash`. The audit's proposed YAML diff used `on_yes`/`on_no` notation incorrectly for a `loop:` state type.

## Implementation

| File | Change |
|---|---|
| `scripts/little_loops/loops/rn-remediate.yaml` | `check_convergence`: `TOTAL_DELTA -le 2` → `TOTAL_DELTA -le 0` |
| `scripts/little_loops/loops/rn-implement.yaml` | `fifo_pop`: exit 0 + QUEUE_EMPTY token, output_contains evaluator, routing inverted |
| `scripts/little_loops/loops/rn-implement.yaml` | `select_next`: same QUEUE_EMPTY pattern, shell guard updated |

## Session Log
- `hook:posttooluse-status-done` - 2026-06-09T19:41:55 - `df9d284e-1fef-4970-8023-327c57799474.jsonl`
- `/ll:capture-issue` - 2026-06-09T19:40:55Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/df9d284e-1fef-4970-8023-327c57799474.jsonl`
