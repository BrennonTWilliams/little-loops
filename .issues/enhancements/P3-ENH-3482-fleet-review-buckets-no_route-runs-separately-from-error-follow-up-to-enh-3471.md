---
id: ENH-3482
type: ENH
title: fleet-review buckets no_route runs separately from error (follow-up to ENH-3471)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-15'
captured_at: '2026-09-15T23:36:00Z'
parent: ENH-3468
blocked_by:
- ENH-3471
---

# ENH-3482: fleet-review buckets no_route runs separately from error (follow-up to ENH-3471)

## Summary

ENH-3471 introduces `terminated_by="no_route"` for decision-step failures (no valid transition, `before_route` veto, evaluator/route raise) but deliberately leaves `ll-logs fleet-review` bucketing untouched. `cli/logs.py::_derive_loop_outcome()` (`:2058-2083`) buckets any `loop_complete` event carrying an `error` key as `"error"` *before* it reads `terminated_by`, and `_finish()` still passes `error=` for `no_route`, so fleet-review keeps lumping `no_route` runs into its `"error"` bucket. This issue splits that bucket so the Motivation payoff of ENH-3471 (loop-authoring bugs vs runtime failures have different owners) actually reaches the fleet-review report.

## Current Behavior

`_derive_loop_outcome()` checks `if "error" in event` first and returns `"error"`; `terminated_by` is only consulted afterwards. A `no_route` run therefore reports as `"error"` in `ll-logs fleet-review` output and in `docs/runbooks/FLEET_LOOP_REVIEW.md`'s vocabulary.

## Expected Behavior

- `_derive_loop_outcome()` reads `terminated_by` before the `error`-key fallback, and returns `"no_route"` for that value.
- `ll-logs fleet-review` output gains a `no_route` bucket; the `"error"` bucket's meaning ("the action crashed or an infra/host signal aborted the run") is unchanged for every other run.
- `docs/runbooks/FLEET_LOOP_REVIEW.md` documents the new bucket and what it implies (missing route declaration — a loop-authoring fix, not an environment fix).
- `scripts/tests/test_ll_logs.py` assertions on the `"error"` bucket still pass; a new case covers a `loop_complete` event with `terminated_by="no_route"` and an `error` key.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Scope Boundaries

- **In scope**: `_derive_loop_outcome()`, its tests, the fleet-review runbook, and any fleet-review summary table that enumerates outcome buckets.
- **Out of scope**: the executor, `ExecutionResult`, and every consumer ENH-3471 already widens. Do not start until ENH-3471 has landed — the value does not exist before then.

## Parent Issue

Decomposed from ENH-3468. Follow-up to ENH-3471, which explicitly defers this under its Scope Boundaries ("Deliberately deferred — fleet-review outcome bucketing").

## Status

**Open** | Created: 2026-09-15 | Priority: P3
