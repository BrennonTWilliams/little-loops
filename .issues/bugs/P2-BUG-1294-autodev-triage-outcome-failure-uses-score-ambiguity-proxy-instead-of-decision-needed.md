---
id: "1294"
type: BUG
priority: P2
title: "autodev triage_outcome_failure uses score_ambiguity proxy instead of decision_needed flag"
status: open
captured_at: "2026-04-26T20:35:25Z"
discovered_date: "2026-04-26"
discovered_by: capture-issue
---

# BUG-1294: autodev triage_outcome_failure uses score_ambiguity proxy instead of decision_needed flag

## Summary

In `scripts/little_loops/loops/autodev.yaml`, the `triage_outcome_failure` state routes to `run_decide` only when `score_ambiguity <= 10`, treating a low ambiguity score as a proxy for `decision_needed=true`. Issues with `decision_needed=true` but `score_ambiguity > 10` are not fast-pathed to `run_decide`; in the worst case (when `missing_artifacts=true` is also set), they are silently skipped from the pipeline without `/ll:decide-issue` ever being called.

## Root Cause

**File**: `scripts/little_loops/loops/autodev.yaml`
**State**: `triage_outcome_failure` (line ~407–433)
**Function**: The Python snippet exits 0 (→ `run_decide`) when `score_ambiguity <= 10`, and exits 1 (→ `check_missing_artifacts`) otherwise.

The condition never reads the `decision_needed` field. Three distinct routing scenarios result:

| `score_ambiguity` | `decision_needed` | `missing_artifacts` | Outcome |
|---|---|---|---|
| ≤ 10 | any | any | Fast path → `run_decide` ✓ |
| > 10 | true | false | Long path (6 extra states) → `check_decision_before_size_review` → `run_decide` ✓ |
| > 10 | true | **true** | `check_missing_artifacts` → `run_wire` → `enqueue_or_skip` → `recheck_after_size_review` (on_no) → **`dequeue_next`** — issue silently dropped ✗ |

In Case 3, wiring doesn't resolve the decision ambiguity, so `recheck_after_size_review` sees scores still below threshold and routes `on_no: dequeue_next` — skipping the issue entirely and never calling `/ll:decide-issue`.

## Steps to Reproduce

1. Create an issue with `decision_needed: true`, `score_ambiguity` in the 15–30 range, and `missing_artifacts: true`.
2. Run `ll-loop run autodev "<issue-id>"`.
3. Observe: `triage_outcome_failure` routes to `check_missing_artifacts` → `run_wire` rather than `run_decide`. After wiring (which doesn't clear the decision question), `recheck_after_size_review` drops the issue.

## Expected Behavior

`triage_outcome_failure` should route to `run_decide` when `decision_needed=true` OR when `score_ambiguity <= 10`. The `decision_needed` flag is the authoritative signal; `score_ambiguity` is only a proxy.

## Proposed Fix

Change the exit condition in `triage_outcome_failure` to check both signals:

```python
d = json.loads(r.stdout)
ambiguity_low = int(d.get('score_ambiguity') or 25) <= 10
decision_needed = d.get('decision_needed') == 'true'
sys.exit(0 if (ambiguity_low or decision_needed) else 1)
```

This makes all three cases fast-path to `run_decide` when the `decision_needed` flag is set, regardless of `score_ambiguity` or `missing_artifacts`.

## Impact

- **Data loss risk**: Issues with unresolved design decisions and missing artifacts are silently dropped from the autodev pipeline.
- **Incorrect routing**: Even in non-worst-case scenarios, `decision_needed=true` issues take 6 unnecessary extra states before reaching `run_decide`.

## Implementation Steps

1. Edit `triage_outcome_failure` action in `scripts/little_loops/loops/autodev.yaml` to include `decision_needed` in the exit condition (see Proposed Fix above).
2. Verify `check_missing_artifacts`'s comment is updated if it referenced this routing assumption.
3. Add a test case in `scripts/tests/` covering `triage_outcome_failure` routing with `decision_needed=true` and `score_ambiguity=20`.

## Session Log
- `/ll:capture-issue` - 2026-04-26T20:35:25Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52be9e23-3914-464f-97ac-e73aca9d145b.jsonl`
