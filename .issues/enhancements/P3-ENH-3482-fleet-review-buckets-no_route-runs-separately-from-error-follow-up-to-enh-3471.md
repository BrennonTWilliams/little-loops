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
decision_needed: true
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- The test bullet above covers `_derive_loop_outcome()`'s own `test_derive_outcome_*` cases in `test_ll_logs.py` (`TestLoopFleet`, `:5136-5181`), but there is a second, separate hardcoded outcome-vocabulary enumeration site: `TestIsFlaggedParity`'s `top_outcome` parametrize list (`test_ll_logs.py:6660`), which does not yet include `"no_route"`. Whether it should is downstream of the `_FLAG_OUTCOMES` decision — see `## Proposed Solution` and `## Program Design` → Decision Rules.

## Impact

- **Priority**: P3 - Reporting-only follow-up; no runtime behavior changes, so it doesn't block other work, but the ENH-3471 payoff (surfacing loop-authoring bugs separately from runtime failures) stays invisible in fleet-review until this lands.
- **Effort**: Small - One reordered branch in `_derive_loop_outcome()`, one new bucket label threaded through the report renderer, one runbook paragraph, one new test case.
- **Risk**: Low - Pure bucketing/labeling change with no effect on loop execution, `ExecutionResult`, or the executor; existing `"error"` bucket assertions are preserved per Expected Behavior.
- **Breaking Change**: No - Additive: fleet-review gains a bucket label; no field, schema, or CLI flag is removed.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

**Option A**: Add `"no_route"` to `_FLAG_OUTCOMES` (`scripts/little_loops/cli/logs.py:1188`), alongside `error`/`max-steps`/`stalled`/`failed`. A loop whose `top_outcome` is `no_route` is then treated as unhealthy by `is_flagged()` (`:1191-1210`), the same as any other loop-logic failure bucket, and the "Delta vs baseline" table gains its own `Δno_route` column (`outcome_keys = sorted(_FLAG_OUTCOMES)`, `:2570`).

**Option B**: Leave `no_route` out of `_FLAG_OUTCOMES`, following the precedent already set for `interrupted`/`signal` (`:1197-1200`, "operator/infra exits... not loop-logic failures... deliberately excluded"). `no_route` still appears automatically in the per-loop "Outcomes" cell (`:2534`) and the JSON sidecar (`_build_fleet_sidecar()`, `:2356-2394`) with zero further code changes, and still lowers `success_pct`, but does not by itself trigger flagging and gets no dedicated `Δ` column.

**Recommended**: Option A — `no_route` is explicitly a loop-authoring bug (missing route declaration), which this issue's own Motivation groups with "loop-logic failures" (the same category as `failed`/`error`/`stalled`), not with the "operator/infra exits" (`interrupted`/`signal`) that `is_flagged()`'s docstring names as the reason for exclusion. Excluding `no_route` from `_FLAG_OUTCOMES` would mean a fleet of loops silently failing on missing routes never gets automatically flagged as unhealthy — the exact visibility gap this issue exists to close.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/logs.py` — `_derive_loop_outcome()` (`:2058-2083`): reorder the `terminated_by` check ahead of the `"error" in event` fallback for the `no_route` case only, per Expected Behavior.
- `scripts/little_loops/cli/logs.py` — `_FLAG_OUTCOMES` (`:1188`, `frozenset({"error", "max-steps", "stalled", "failed"})`): whether `no_route` is added here is an open decision — see `### Decision Rules` below and the option block under `## Proposed Solution`. This frozenset is also the flagging-failure set consumed by `is_flagged()` (`:1191-1210`) and the "Delta vs baseline" table's column set (`outcome_keys = sorted(_FLAG_OUTCOMES)`, `:2570`), so the decision has effects beyond bucket labeling.
- `docs/runbooks/FLEET_LOOP_REVIEW.md` — outcome-vocabulary block (`:93-97`, the `` converged | failed | error | max-steps | stalled | interrupted | signal `` fenced line) and the flagging-rule bullets (`:90-104`) per Expected Behavior. This is the only place in `docs/` this vocabulary is enumerated (confirmed by a repo-wide search).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/logs.py:2188`, `:2219` — the two `_collect_loop_runs()` call sites of `_derive_loop_outcome()`; no changes needed here, they consume whatever string is returned.
- `scripts/tests/test_ll_logs.py:17` — imports `_FLAG_OUTCOMES` directly; a change to that frozenset is visible to this import.
- `scripts/little_loops/fleet_improve.py` — consumes `_derive_loop_outcome()`/`_FLAG_OUTCOMES`/`is_flagged()` indirectly via the fleet sidecar but reads `converged`/`runs` counts rather than re-enumerating outcome-bucket string labels itself; confirmed no change needed there.
- `scripts/little_loops/cli/__init__.py:75`, `scripts/little_loops/cli/ctx_stats.py:20` — generic module-level importers of `logs.py`, unrelated to outcome-bucket vocabulary; listed to bound scope, not to modify.

### Conventions in Force

- New `terminated_by`-derived buckets are added as one `if` branch inside `_derive_loop_outcome()`, each carrying an inline `# ENH-NNNN:`/`# BUG-NNNN:` comment explaining the bucketing rationale — evidence: the `user_stopped`/`system_signal` branches (ENH-2522) and the `workdir_vanished` branch (BUG-3375), all in `logs.py:2058-2083`.
- Bucket return values are hyphenated string literals distinct from the raw `terminated_by` token (e.g. `terminated_by == "max_steps"` returns `"max-steps"`) — the wire value and the report-facing label are allowed to diverge; evidence: `logs.py:2063-2064`.
- ENH-2522 is direct precedent for this exact class of change (splitting a new named bucket out of the taxonomy): its Resolution required only the one-line `_derive_loop_outcome()` branch — no other `logs.py` changes were needed for the new buckets to reach the fleet-review report or JSON sidecar, because two of the three surfaces render buckets dynamically (see next point).
- The report's bucket surfaces are **not** uniformly canonical-list-driven — this is a contested/mixed convention, not a single rule: the per-loop "Outcomes" cell (`outcomes_str` at `logs.py:2534`) and the JSON sidecar (`_build_fleet_sidecar()`, `:2356-2394`) render any `dict[str, int]` Counter dynamically, needing zero code changes for a new bucket to appear; the "Delta vs baseline" table (`:2570-2599`) instead iterates the fixed `_FLAG_OUTCOMES` frozenset and gains a `Δ<bucket>` column only for buckets in it.
- `is_flagged()`'s docstring (`logs.py:1197-1200`) documents that `interrupted`/`signal` are *deliberately* excluded from `_FLAG_OUTCOMES` as "operator/infra exits... not loop-logic failures" — exclusion from that frozenset is an established, load-bearing pattern already used to keep one bucket out of the flagging rule, not an oversight to fix.

### Tests

- `scripts/tests/test_ll_logs.py`, class `TestLoopFleet` (`:5058` on) — `test_derive_outcome_*` cases at `:5136-5181` cover `_derive_loop_outcome()` directly; convention is `test_derive_outcome_<label>` naming, a one-line `"<condition> → <bucket>"` docstring, a minimal inline event dict (not the class's `_loop_complete()` builder), and a direct `assert _derive_loop_outcome(event) == "<bucket>"`. The `workdir_vanished`-with-vs-without-`error` pair (`:5175`, `:5181`) is precedent for exercising both paths to the same bucket when a new `terminated_by` value could also be caught by an earlier branch.
- `scripts/tests/test_ll_logs.py`, class `TestIsFlaggedParity` (`:6651`) — its `top_outcome` parametrize list at `:6660` (`["converged", "failed", "error", "max-steps", "stalled", "interrupted", "signal"]`) is a second, separate hardcoded outcome-vocabulary enumeration site that does not yet include `"no_route"`. Expected Behavior's test bullet only names `test_ll_logs.py`'s `"error"` bucket assertions and a new `no_route` case for `_derive_loop_outcome()`; it does not mention this second site, whose correct membership depends on the `_FLAG_OUTCOMES` decision above.

### Documentation

- `docs/runbooks/FLEET_LOOP_REVIEW.md:82-104` — the vocabulary section's established shape: (1) the flagging-rule bullets name the four failure outcomes inline as prose, (2) a fenced code block lists the *complete* vocabulary as one `|`-delimited line in the same left-to-right order as the branches in `_derive_loop_outcome()`, (3) a following paragraph names the excluded subset and states why. A `no_route` addition should follow this same three-part shape rather than freeform prose.
- `docs/reference/CLI.md` — confirmed no outcome-vocabulary text present (flag/usage documentation only); no change needed there.

### Configuration

None found — no config file references `_derive_loop_outcome`, `no_route`, or the fleet-review bucket vocabulary.

## Program Design

### Types

- No new types — reuses the existing `str` outcome-bucket return type of `_derive_loop_outcome()`.

### Signatures

- `_derive_loop_outcome(event: dict) -> str` — check `event.get("terminated_by") == "no_route"` and return `"no_route"` before the existing `if "error" in event: return "error"` fallback (`scripts/little_loops/cli/logs.py:2058-2083`).

### Call Path

`_cmd_fleet_review()` -> `_derive_loop_outcome()` -> `_render_fleet_review_report()` (bucket aggregation/labeling at `scripts/little_loops/cli/logs.py:2478`)

If `no_route` is added to `_FLAG_OUTCOMES` (see Decision Rules below), the bucket also flows: `_aggregate_fleet_runs()` (`logs.py:1137`, builds `top_outcome`/`outcomes` Counter) -> `is_flagged()` (`:1191-1210`) -> `_flag_loops()` (`:1213-1222`) for the flagging rule, and separately into the `outcome_keys = sorted(_FLAG_OUTCOMES)` column set of the "Delta vs baseline" table (`:2570-2599`).

### Decision Rules

- **Gap**: whether `terminated_by="no_route"` counts as a fleet-review *flagging* failure (membership in `_FLAG_OUTCOMES`, `logs.py:1188`), or is reported but excluded from flagging (like `interrupted`/`signal`, per `is_flagged()`'s documented rationale at `:1197-1200`).
- **Inputs**: the `_FLAG_OUTCOMES` frozenset (`logs.py:1188`); membership is binary (add `"no_route"` or don't).
- **Effect if added**: `is_flagged()` treats a loop whose `top_outcome` is `no_route` as unhealthy, and the "Delta vs baseline" table gains a dedicated `Δno_route` column.
- **Effect if omitted**: `no_route` still surfaces automatically in the per-loop "Outcomes" cell (`outcomes_str`, `:2534`) and the JSON sidecar (`_build_fleet_sidecar()`, `:2356-2394`) with zero further code changes, and still lowers `success_pct` — but never triggers `is_flagged()` and gets no dedicated `Δ` column.
- **No escape hatch needed**: this is a genuine binary decision, not a threshold/keyword list to pin down. See the option block under `## Proposed Solution` for the two named alternatives and a recommendation.

## Scope Boundaries

- **In scope**: `_derive_loop_outcome()`, its tests, the fleet-review runbook, and any fleet-review summary table that enumerates outcome buckets.
- **Out of scope**: the executor, `ExecutionResult`, and every consumer ENH-3471 already widens. Do not start until ENH-3471 has landed — the value does not exist before then.

## Parent Issue

Decomposed from ENH-3468. Follow-up to ENH-3471, which explicitly defers this under its Scope Boundaries ("Deliberately deferred — fleet-review outcome bucketing").

## Status

**Open** | Created: 2026-09-15 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-15T23:47:51 - `00985229-ae90-46cd-ac9a-bd0275ccc50b.jsonl`
- `/ll:format-issue` - 2026-09-15T23:38:43 - `40022929-8f22-431e-874e-951b8ed315e8.jsonl`
