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

- **Priority**: P3 - Reporting-only follow-up; no runtime behavior changes, so it doesn't block other work, but the ENH-3471 payoff (surfacing loop-authoring bugs separately from runtime failures) stays invisible in fleet-review until this lands.
- **Effort**: Small - One reordered branch in `_derive_loop_outcome()`, one new bucket label threaded through the report renderer, one runbook paragraph, one new test case.
- **Risk**: Low - Pure bucketing/labeling change with no effect on loop execution, `ExecutionResult`, or the executor; existing `"error"` bucket assertions are preserved per Expected Behavior.
- **Breaking Change**: No - Additive: fleet-review gains a bucket label; no field, schema, or CLI flag is removed.

## Program Design

### Types

- No new types — reuses the existing `str` outcome-bucket return type of `_derive_loop_outcome()`.

### Signatures

- `_derive_loop_outcome(event: dict) -> str` — check `event.get("terminated_by") == "no_route"` and return `"no_route"` before the existing `if "error" in event: return "error"` fallback (`scripts/little_loops/cli/logs.py:2058-2083`).

### Call Path

`_cmd_fleet_review()` -> `_derive_loop_outcome()` -> `_render_fleet_review_report()` (bucket aggregation/labeling at `scripts/little_loops/cli/logs.py:2478`)

## Scope Boundaries

- **In scope**: `_derive_loop_outcome()`, its tests, the fleet-review runbook, and any fleet-review summary table that enumerates outcome buckets.
- **Out of scope**: the executor, `ExecutionResult`, and every consumer ENH-3471 already widens. Do not start until ENH-3471 has landed — the value does not exist before then.

## Parent Issue

Decomposed from ENH-3468. Follow-up to ENH-3471, which explicitly defers this under its Scope Boundaries ("Deliberately deferred — fleet-review outcome bucketing").

## Status

**Open** | Created: 2026-09-15 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-15T23:38:43 - `40022929-8f22-431e-874e-951b8ed315e8.jsonl`
