---
id: ENH-2989
title: autodev reports a Phase 1 verdict failure as a phantom implementation
type: ENH
priority: P3
status: open
captured_at: '2026-08-02T00:00:00Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2988
labels:
- automation
- resilience
- loops
testable: true
---

# ENH-2989: autodev reports a Phase 1 verdict failure as a phantom implementation

## Summary

When `ll-auto` exits non-zero without ever reaching Phase 2, `autodev.yaml`
records the issue as `unverified` with verdict `phantom` and the message
"threshold passed; implementation did not close — re-queue to retry". That is
materially wrong: no implementation was attempted. The run summary blames the
issue for a failure that happened before any work began.

Give autodev a probe that distinguishes "never reached implementation" from
"implemented but did not close."

## Current Behavior

`implement_current` evaluates on `exit_code` alone. On a non-zero exit it routes
through `check_learning_gate` (pattern `GATE_BLOCKED`) and `check_impl_auth`
(pattern `AUTH_FAILED`); neither matches a Phase 1 verdict failure, so control
falls through to `clear_inflight_after_impl_failure` and on to `finalize_done`,
which classifies the issue as `unverified` and writes
`{"verdict": "phantom", "not_closed": 1}`.

Observed in `.loops/runs/autodev-20260801T214427/` (ENH-2971). The full state
trace: `refine_issue`, `wire_issue` and `confidence_check` all succeeded —
Readiness 96, Outcome 79 — then `implement_current` failed in 11.5 seconds
because `ll-auto` Phase 1 got an unparseable `ready-issue` verdict and returned
"Issues processed: 0". `summary.json` reports `"verdict":"phantom"`.

The operator-visible output is actively misleading: it points at the issue's
implementation when the actual failure was a single non-compliant model turn
during validation.

## Expected Behavior

A run that never reached Phase 2 is reported as its own outcome — distinct from
`phantom` — and re-queued, rather than recorded as a failed implementation.

The distinction should be legible in both the run summary and `summary.json`.

## Program Design

`ll-auto`'s output already carries the signal. This run's `ll_auto_last.txt`
contains `ready-issue verdict: UNKNOWN`, `is NOT READY for implementation`, and
`Issues processed: 0` — any of which distinguishes the case from a real Phase 2
failure. The cheapest correct discriminator is probably a dedicated exit code
from `ll-auto`, so the FSM branches on a number rather than pattern-matching
prose that is free to change.

### Signatures

```yaml
# scripts/little_loops/loops/autodev.yaml — new state, mirroring check_impl_auth
check_impl_reached:
  action: <probe ll-auto output or exit code>
  evaluate:
    type: check_output
    pattern: "NOT_STARTED"
  on_yes: <record not_started + re-queue>
  on_no: check_learning_gate
```

```python
# scripts/little_loops/issue_manager.py — IssueProcessingResult already carries
# the fact; what is missing is a distinct process-level exit signal.
IssueProcessingResult.failure_reason  # e.g. "NOT READY: UNKNOWN - 0 concern(s)"
```

### Call Path

`implement_current` (`scripts/little_loops/loops/autodev.yaml`) shells out to
`ll-auto` and evaluates on `exit_code`. On non-zero it routes
`check_learning_gate` (pattern `GATE_BLOCKED`) → `check_impl_auth` (pattern
`AUTH_FAILED`) → `clear_inflight_after_impl_failure` → `dequeue_next` →
`finalize_done`. The new state inserts ahead of `check_learning_gate`, matching
the two existing probes' shape exactly.

The signal originates in `process_issue_inplace`
(`scripts/little_loops/issue_manager.py:719-930`), whose Phase 1 branches all
return a `_stamped_result(success=False, ...)` before Phase 2's
`run_with_continuation` is ever called — that early-return set is precisely the
"never reached implementation" population.

`finalize_done` is where the summary key is written; it currently emits
`verdict` / `closed` / `not_closed` / `skipped` / `gate_blocked` /
`decision_unresolved` / `inflight_unresolved` / `abandoned`.

### Open questions for refinement

- Whether the discriminator is a new `ll-auto` exit code or output pattern.
- Which summary key it emits — `not_started`, alongside the existing keys.
- Whether re-queueing is unconditional or bounded by an attempt counter, to
  avoid an issue looping on a persistently failing validation step.

Note that `little_loops.ready_issue`'s retry-on-`UNKNOWN` makes this case rarer,
but does not eliminate it: a retry that also whiffs, or any other Phase 1
terminal verdict, still lands here.

## Scope Boundaries

- **In scope**: distinguishing "never reached Phase 2" from "implemented but
  did not close" in `autodev.yaml`'s routing and `summary.json`; re-queue
  instead of a false `phantom`.
- **Out of scope**: fixing the Phase 1 failures themselves (that is
  `little_loops.ready_issue`'s retry and ENH-2988); the `phantom` verdict's
  meaning for runs that genuinely did implement; other loops' summary schemas.

## Impact

Run summaries stop misattributing validation failures to implementation.
Operators reading "implementation did not close" can trust it. Affects every
autodev run that fails in Phase 1.

## Status

open
