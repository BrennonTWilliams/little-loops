---
id: BUG-2636
type: BUG
priority: P2
status: done
discovered_date: "2026-07-13"
discovered_by: manual
completed_at: "2026-07-13"
labels: [loops, fsm, observability, auto-refine-and-implement]
relates_to:
- BUG-2633
---

# BUG-2636: auto-refine-and-implement reports green "done" when a dispatched issue is left in-flight

## Summary

`ll-loop run auto-refine-and-implement` reported `Loop completed: done` for a run
(`.loops/runs/auto-refine-and-implement-20260713T190717/`) that closed **nothing**
and left its only dispatched issue (ENH-2578, scope `EPIC-2575`) stuck in the
`autodev-inflight` sentinel. The implementation attempt had surfaced a blocker
(BUG-2633) and filed new issues instead of completing, but the run's terminal
status gave no hint that the work was abandoned.

## Status

`done` — fixed 2026-07-13 in `auto-refine-and-implement.yaml` with regression
tests in `TestAutoRefineAndImplementLoop`.

## Steps to Reproduce

1. `ll-loop run auto-refine-and-implement --context scope=<EPIC>` where the epic's
   only actionable child gets dispatched but its implementation session ends
   without closing the issue (e.g. it hits a blocker and files new issues).
2. Observe `Loop completed: done` (green) even though nothing closed.
3. Inspect `.loops/runs/<run>/`: `autodev-inflight` still holds the issue,
   `autodev-passed.txt`/`-skipped.txt`/`-gate-blocked.txt` are all empty, and
   `summary.json` reports `verdict: no-op`.

## Current Behavior

A dispatched-but-abandoned issue is invisible to `finalize`'s ledger-based
verdict, so the run scores `no-op` and — because `finalize` always routes to the
`done` terminal — `ll-loop` prints a green success line. The unresolved work is
silently lost.

## Expected Behavior

An issue left in `autodev-inflight` (and not actually closed) is counted as
`inflight_unresolved`, escalates the verdict to `phantom`, and routes the FSM to a
non-`done` `incomplete` terminal so `ll-loop` renders the run as not-success and
surfaces the verdict as the failure reason.

## Impact

Silent false-success on autonomous runs: an operator scanning loop outcomes sees
`done` and moves on, leaving genuinely blocked/abandoned issues unaddressed and
skewing any history/analytics that trusts the terminal status.

## Root Cause

Two independent gaps compounded:

1. **Invisible in-flight issue.** The outer loop's `finalize` state derived its
   verdict purely from autodev's `passed`/`skipped`/`gate-blocked`/`errored`
   ledgers. An issue dequeued (sentinel written) but never re-classified — because
   autodev reached its terminal via an env-abort/cut-off path that neither closes
   the issue nor records a skip — appears in **none** of those ledgers. With
   `CLOSED=0`, `ERR=0`, `NOT_CLOSED=0`, `SKIP=0`, the verdict fell through to
   `no-op` (a benign empty-backlog result), masking a real abandonment.

2. **Terminal name always `done`.** `finalize` unconditionally routed `next: done`.
   `ll-loop`'s completion line derives success from the terminal state's *name*
   (`cli/loop/_helpers.py` `_is_success`: any terminal != `done` renders orange and
   surfaces the failing state's stdout). So even the richer `subloop_outcome`
   verdict `finalize` already computed (`phantom`/`no-op`/…) never reached the user.

## Fix

`scripts/little_loops/loops/auto-refine-and-implement.yaml`, `finalize` state:

- Added an `INFLIGHT_UNRESOLVED` signal sourced from the raw `autodev-inflight`
  sentinel, counted only when that issue did **not** actually close (guards against
  a lingering-but-resolved sentinel). Folded it into `parked_rate`, the `phantom`
  verdict trigger, and a new `inflight_unresolved` key in `summary.json` + the
  human summary line (mirrors the ENH-2404 `gate_blocked` / BUG-2595
  `decision_unresolved` first-class-signal pattern).
- Converted `finalize` to the `shell_exit` fragment and route on verdict:
  `on_yes → done` for `success`/`partial`/`partial-with-errors`/`no-op` (real
  progress or a genuinely empty backlog); `on_no → incomplete` for `phantom`
  (attempted work, closed nothing, left issues parked/not-closed/in-flight/errored).
  Added a non-`done` `incomplete` terminal so `ll-loop` renders such runs as
  not-success and surfaces the verdict summary as the failure reason.

Reading the raw sentinel at `finalize` (the outer loop's last state, after all
`delegate`/`recheck_set` passes) covers both the reached-terminal and the
step/time-cut-off cases without depending on the autodev sub-loop's own `done`
action running.

## Acceptance Criteria

- [x] A run that leaves an issue in `autodev-inflight` (not closed) reports
      `inflight_unresolved >= 1` and verdict `phantom` in `summary.json`.
- [x] A lingering sentinel whose issue actually closed does **not** count as
      unresolved (verdict stays `success`).
- [x] A `phantom` verdict routes the FSM to the `incomplete` terminal (exit
      non-zero); every other verdict routes to `done`.
- [x] `ll-loop validate auto-refine-and-implement` passes with the new state.
- [x] `python -m pytest scripts/tests/` passes (regression tests added in
      `TestAutoRefineAndImplementLoop`).

## Notes

Surfaced while working BUG-2633 under `EPIC-2575`. ENH-2578 was marked
`blocked_by: BUG-2633` as part of the same investigation.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-14T01:03:25 - `7d581b2b-0986-4991-85b6-b00abd29d4e5.jsonl`
