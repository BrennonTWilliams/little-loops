---
id: BUG-2397
title: "FSM runner emits `terminated_by: \"max_iterations\"` instead of `\"interrupted\"` when session is killed between state transitions"
type: BUG
status: open
priority: P3
captured_at: '2026-06-30T00:00:00Z'
discovered_date: '2026-06-30'
discovered_by: audit-loop-run
labels:
- fsm
- runner
- termination
- observability
---

# BUG-2397: FSM runner emits `terminated_by: "max_iterations"` on session kill instead of `"interrupted"`

## Summary

When a Claude session ends (SIGTERM, context limit, user interruption) while the
FSM runner is between state transitions — i.e., after a `route` event but before
the next `state_enter` — the runner's shutdown handler writes a `loop_complete`
event with `terminated_by: "max_iterations"` regardless of whether the iteration
budget was actually reached. This contradicts the `state.json` `status:
"interrupted"` field written by the same shutdown path, and misleads users and
audit tooling into diagnosing iteration budget exhaustion when the real cause is
external session death.

**Observed in run:** `.loops/.history/2026-06-14T024943-sprint-refine-and-implement/`

- `events.jsonl` → `loop_complete.terminated_by: "max_iterations"`, `iterations: 1`
- `state.json` → `status: "interrupted"`
- YAML had `max_iterations: 500` at commit `38a158b` — hitting the limit at
  iteration 1 is impossible through normal execution
- Total wall clock: 104ms; only `get_next_issue` ran (103ms); `refine_issue` was
  never entered

## Root Cause

The FSMRunner shutdown / signal handler writes a `loop_complete` event before
exiting. The current implementation uses `"max_iterations"` as the `terminated_by`
label as a fallback whenever a `loop_complete` fires outside a natural terminal
state — without checking whether `self._iteration >= self.max_iterations`.

When a session is killed between a `route` event and the next `state_enter`:
1. The iteration counter has not yet incremented for the next state
2. The shutdown handler fires and emits `terminated_by: "max_iterations"`
3. `state.json` is updated with `status: "interrupted"` by the same path

The two fields end up contradicting each other.

**Likely location:** `scripts/little_loops/fsm/runner.py` — shutdown handler /
`loop_complete` emission path.

## Impact

- Users (and `/ll:audit-loop-run`) must cross-reference `state.json` against the
  `loop_complete` event to determine the real cause of a truncated run
- Budget-utilization analysis (`STEPS_CONSUMED / MAX_STEPS < 0.3`) correctly
  rejects budget-exhaustion as root cause, but only if the auditor knows to apply
  it; the `terminated_by` label alone is misleading
- Downstream tooling that branches on `terminated_by` (e.g., retry logic, fleet
  dashboards) may misclassify interrupted runs as budget-exhausted ones

## Proposed Fix

In the FSMRunner shutdown / interrupt path, check the actual iteration count before
choosing the `terminated_by` label:

```python
# scripts/little_loops/fsm/runner.py — loop_complete emission
if self._iteration >= self.max_iterations:
    terminated_by = "max_iterations"
elif self._interrupted:   # flag set by SIGTERM / session-end handler
    terminated_by = "interrupted"
else:
    terminated_by = "max_iterations"  # genuine unknown fallback

# Sync state.json status to match
status = "max_steps_reached" if terminated_by == "max_iterations" else "interrupted"
```

Also ensure `state.json` `status` and `events.jsonl` `terminated_by` always agree:
- `terminated_by: "max_iterations"` → `status: "max_steps_reached"`
- `terminated_by: "interrupted"` → `status: "interrupted"`

## Acceptance Criteria

- [ ] Killing a loop mid-run with SIGTERM emits `terminated_by: "interrupted"` (not `"max_iterations"`) in `events.jsonl`
- [ ] `state.json` `status` matches `terminated_by` semantics after any shutdown path
- [ ] A loop that genuinely exhausts `max_iterations` still emits `terminated_by: "max_iterations"`
- [ ] `/ll:audit-loop-run` on a SIGTERM-interrupted run reports `honest-failure` with root cause "session interrupted" rather than prompting budget-exhaustion analysis
