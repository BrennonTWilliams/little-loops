---
id: ENH-2892
status: open
priority: P3
captured_at: "2026-07-28T00:00:00Z"
discovered_date: 2026-07-28
discovered_by: capture-issue
labels: [loops, general-task, fsm, verification]
relates_to: [ENH-2814, ENH-2825, ENH-2857]
---

# ENH-2892: general-task.yaml has no `failure: true` terminal — ENH-2814 exit-code plumbing is inert

## Summary

`scripts/little_loops/loops/general-task.yaml` defines three terminals — `partial`,
`done`, and `failed` — and **none** of them carries `failure: true`. Since
`FSM.get_failure_states()` (`scripts/little_loops/fsm/schema.py:1559-1568`) is the
single source of truth for failure-ness and derives it solely from that flag, every
general-task run exits 0 and persists as `completed`, including runs that reach
`failed` via the `diagnose` state.

This makes ENH-2814's failure plumbing (exit 2, `final_status: "failed"`,
`loop_runs.failure_terminal`) completely inert for this loop, and it means a parent
loop dispatching general-task as a sub-loop cannot distinguish a diagnosed failure
from a clean success.

## Discovery context

Found while fixing the ENH-2825 gate failure on `check_abandoned_route.on_error`
(`test_builtin_loops.py::test_no_failure_edge_routes_to_a_success_terminal`). The
obvious fix — route the edge to "the loop's failure terminal" — was unavailable
because no such terminal exists. That edge was routed to the non-terminal `diagnose`
instead, which satisfies the gate and is the loop's established convention for
unrecoverable errors, but it deliberately sidesteps this underlying gap.

## Proposed change

Add `failure: true` to the `failed` terminal in `general-task.yaml`.

Deliberately **not** `partial`: ENH-2575 designed `partial` as a distinct non-`done`,
non-`failed` terminal precisely so a verify timeout is neither laundered as success
nor discards the run's verified progress. Marking it a failure terminal would undo
that.

## Blast radius (must be assessed before implementing)

This is a behavior change, not a lint fix — it is why it was split out rather than
folded into the test-fix pass:

- Every path reaching `failed` (~15 `on_error: diagnose` edges plus `final_verify`'s
  chain) starts exiting 2 instead of 0.
- Any caller that shells out to `ll-loop run general-task` and checks the exit code
  will begin seeing failures it previously did not.
- Sub-loop dispatch routing for parents delegating to general-task changes from
  on_success to on_failure for those paths.

## Acceptance Criteria

- [ ] `failed` in `general-task.yaml` carries `failure: true`
- [ ] A test asserts `get_failure_states()` for general-task is non-empty
- [ ] Existing tests that drive general-task to `failed` are audited for exit-code
      assumptions and updated where they assumed exit 0
- [ ] `python -m pytest scripts/tests/` exits 0

## Status

open
