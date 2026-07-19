---
id: BUG-2685
type: BUG
priority: P2
status: open
captured_at: "2026-07-18T23:58:26Z"
discovered_date: 2026-07-18
discovered_by: capture-issue
---

# BUG-2685: refine-to-ready-issue phantom-convergence on max_steps exhaustion

## Summary

`refine-to-ready-issue` (max_steps: 20) exhausted its full step budget on four
separate invocations during a single autodev run, each time reporting
`final_state: done` / `terminated_by: max_steps` — a phantom-convergence
pattern where the loop reports success without actually reaching its natural
terminal state. The same children were re-dispatched into the loop repeatedly
via `recheck_set`, multiplying the wasted budget.

## Current Behavior

Children of ENH-134 (ENH-135/136/137) and children of ENH-138 (ENH-138/139)
each drove `refine-to-ready-issue` to burn its full 20-step budget, at four
separate timestamps in one run (09:44:47, 10:34:16, 11:10:26, 11:54:45). The
loop's completion event reports `final_state: done`, which reads as a
successful convergence, but `terminated_by: max_steps` shows it was actually
cut off mid-refinement. Autodev's `recheck_set` mechanism re-enters the same
children into the loop on a later cycle without any awareness that a prior
cycle already exhausted the budget on them, so the cost compounds instead of
surfacing as a stall.

## Expected Behavior

Either:
1. `refine-to-ready-issue` detects when no new FSM state has been visited for
   N consecutive iterations and exits with a distinct "stalled" verdict
   (instead of the misleading `final_state: done` / `terminated_by: max_steps`
   combination), or
2. autodev's `recheck_set` does not re-dispatch a child into
   `refine-to-ready-issue` if a prior cycle already exhausted `max_steps` on
   it — avoiding repeated budget burn on issues that are known not to
   converge within budget.

Either fix (or both) should stop the loop from silently reporting phantom
success when it never reached its natural terminal state.

## Motivation

Four exhausted-budget invocations in one run is a significant, repeated
waste — each one silently burns the entire 20-step allowance without
producing the intended refinement outcome, and the `final_state: done`
label hides this from anyone scanning run summaries for failures.

## Proposed Solution

TBD - requires investigation. Two candidate approaches (see Expected
Behavior): a stalled-state detector inside `refine-to-ready-issue.yaml`
(compare visited-state history across iterations), or a check in
`autodev.yaml`'s `recheck_set` dispatch path that skips/flags children whose
last `refine-to-ready-issue` run already terminated via `max_steps`.

## Impact

- **Priority**: P2 — recurring, budget-multiplying waste confirmed across
  four invocations in a single run; not data-destructive but materially
  inflates automation cost and obscures failures behind a `done` label.
- **Effort**: Medium — likely needs either a small stalled-detection addition
  to `refine-to-ready-issue.yaml`'s routing, or a dispatch-guard in
  `autodev.yaml`'s `recheck_set` handling; scope needs confirming against the
  FSM's existing state-visit tracking before implementation.
- **Risk**: Low-medium — changes touch a widely-used built-in loop
  (`refine-to-ready-issue.yaml`) and the autodev dispatch path, so a bad
  guard could cause the opposite failure mode (real work incorrectly skipped
  as "already stalled").

## Related Key Documentation

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`max_steps: 20`,
  confirmed still current)
- `scripts/little_loops/loops/autodev.yaml` (`recheck_set` dispatch)

## Status

- [ ] Root cause confirmed
- [ ] Fix implemented
- [ ] Tests added
- [ ] Verified

## Session Log
- `/ll:capture-issue` - 2026-07-18T23:58:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e0375ff-a00e-4840-8f31-93fc423e7780.jsonl`
