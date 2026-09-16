---
id: ENH-3482
type: ENH
title: fleet-review buckets no_route runs separately from error (follow-up to ENH-3471)
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-15'
captured_at: '2026-09-15T23:36:00Z'
completed_at: '2026-09-16T01:37:14Z'
parent: ENH-3468
blocked_by:
- ENH-3471
decision_needed: false
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 92
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 20
---

# ENH-3482: fleet-review buckets no_route runs separately from error (follow-up to ENH-3471)

## Summary

ENH-3471 introduces `terminated_by="no_route"` for decision-step failures (no valid transition, `before_route` veto, evaluator/route raise) but deliberately leaves `ll-logs fleet-review` bucketing untouched. `cli/logs.py::_derive_loop_outcome()` (`:2058-2083`) buckets any `loop_complete` event carrying an `error` key as `"error"` *before* it reads `terminated_by`, and `_finish()` still passes `error=` for `no_route`, so fleet-review keeps lumping `no_route` runs into its `"error"` bucket. This issue splits that bucket so the Motivation payoff of ENH-3471 (loop-authoring bugs vs runtime failures have different owners) actually reaches the fleet-review report.

## Current Behavior

`_derive_loop_outcome()` checks `if "error" in event` first and returns `"error"`; `terminated_by` is only consulted afterwards. A `no_route` run therefore reports as `"error"` in `ll-logs fleet-review` output and in `docs/runbooks/FLEET_LOOP_REVIEW.md`'s vocabulary.

## Expected Behavior

- `_derive_loop_outcome()` reads `terminated_by` before the `error`-key fallback, and returns `"no_route"` for that value.
- The bucket label is the underscore form `"no_route"`, **not** `"no-route"`. Labels are allowed to diverge from wire tokens (`max_steps` → `max-steps`), but here the label deliberately matches `terminated_by`, `EXIT_CODES` (`cli/loop/runner.py:57`), and `fsm/types.py:40` so a single grep finds every site.
- `ll-logs fleet-review` output gains a `no_route` bucket; the `"error"` bucket's meaning ("the action crashed or an infra/host signal aborted the run") is unchanged for every other run.
- `"no_route"` is added to `_FLAG_OUTCOMES`, so `is_flagged()` treats it as a flagging failure and the "Delta vs baseline" table gains a `Δno_route` column (decided — see `## Proposed Solution` → `### Decision Rationale`).
- `docs/runbooks/FLEET_LOOP_REVIEW.md` documents the new bucket and what it implies (missing route declaration — a loop-authoring fix, not an environment fix). The prose count "one of the four failure outcomes" (`:90`) becomes five.
- `scripts/tests/test_ll_logs.py` assertions on the `"error"` bucket still pass; two new cases cover a `loop_complete` event with `terminated_by="no_route"` — one with an `error` key (the normal case, `_finish()` always passes `error=`) and one without (belt-and-suspenders, mirroring the `workdir_vanished` pair).
- `"no_route"` is added to the `TestIsFlaggedParity` `top_outcome` parametrize list (`test_ll_logs.py:6660`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- The `_derive_loop_outcome()` test bullets above map to `test_derive_outcome_*` cases in `test_ll_logs.py` (`TestLoopFleet`, `:5136-5181`). There is a second, separate hardcoded outcome-vocabulary enumeration site: `TestIsFlaggedParity`'s `top_outcome` parametrize list (`test_ll_logs.py:6660`), which does not yet include `"no_route"`. With Option A decided, `"no_route"` **must** be added to that list so parity between `is_flagged()` and `_flag_loops()` is exercised for the new flagging outcome.

## Impact

- **Priority**: P3 - Reporting-only follow-up; no runtime behavior changes, so it doesn't block other work, but the ENH-3471 payoff (surfacing loop-authoring bugs separately from runtime failures) stays invisible in fleet-review until this lands.
- **Effort**: Small - One reordered branch in `_derive_loop_outcome()`, one new bucket label threaded through the report renderer, one runbook paragraph, one new test case.
- **Risk**: Low - Pure bucketing/labeling change with no effect on loop execution, `ExecutionResult`, or the executor; existing `"error"` bucket assertions are preserved per Expected Behavior.
- **Breaking Change**: No - Additive: fleet-review gains a bucket label; no field, schema, or CLI flag is removed.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

**Option A**: Add `"no_route"` to `_FLAG_OUTCOMES` (`scripts/little_loops/cli/logs.py:1188`), alongside `error`/`max-steps`/`stalled`/`failed`. A loop whose `top_outcome` is `no_route` is then treated as unhealthy by `is_flagged()` (`:1191-1210`), the same as any other loop-logic failure bucket, and the "Delta vs baseline" table gains its own `Δno_route` column (`outcome_keys = sorted(_FLAG_OUTCOMES)`, `:2570`).

> **Selected:** Option A — matches the codebase's own loop-logic-vs-operator/infra taxonomy (FEAT-2379, `is_flagged()`'s docstring, and `EXIT_CODES` in `runner.py` all place `no_route` on the loop-logic side), fans out to every consumer with zero further code changes, and avoids reproducing the exact visibility gap this issue exists to close.

**Option B**: Leave `no_route` out of `_FLAG_OUTCOMES`, following the precedent already set for `interrupted`/`signal` (`:1197-1200`, "operator/infra exits... not loop-logic failures... deliberately excluded"). `no_route` still appears automatically in the per-loop "Outcomes" cell (`:2534`) and the JSON sidecar (`_build_fleet_sidecar()`, `:2356-2394`) with zero further code changes, and still lowers `success_pct`, but does not by itself trigger flagging and gets no dedicated `Δ` column.

**Recommended**: Option A — `no_route` is explicitly a loop-authoring bug (missing route declaration), which this issue's own Motivation groups with "loop-logic failures" (the same category as `failed`/`error`/`stalled`), not with the "operator/infra exits" (`interrupted`/`signal`) that `is_flagged()`'s docstring names as the reason for exclusion. Excluding `no_route` from `_FLAG_OUTCOMES` would mean a fleet of loops silently failing on missing routes never gets automatically flagged as unhealthy — the exact visibility gap this issue exists to close.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-15.

**Selected**: Option A — add `"no_route"` to `_FLAG_OUTCOMES`

**Reasoning**: Both codebase-pattern-finder agents converged on the same read: the `interrupted`/`signal` exclusion precedent Option B invokes was designed for operator/infra exits, not loop-authoring bugs, and `no_route`'s own definition (`fsm/types.py:40-42`) plus the independent `EXIT_CODES` taxonomy in `cli/loop/runner.py:55-57` both place it on the loop-logic-failure side that `_FLAG_OUTCOMES` already covers. Option A also fans out to every consumer (`is_flagged()`, `_flag_loops()`, `fleet_improve.py::flagged_loops()`, the Delta-table's `outcome_keys`) with zero further code changes and a self-extending parametrized test, while Option B would leave loops whose `no_route` share never dominates `top_outcome` silently unflagged — reproducing the exact visibility gap this issue exists to close.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 1/3 | 3/3 | 1/3 | 1/3 | 6/12 |

**Key evidence**:
- For Option A, FEAT-2379's original taxonomy and `is_flagged()`'s docstring both draw the `_FLAG_OUTCOMES` line at "loop-logic failure" vs. "operator/infra exit"; `no_route` (`fsm/types.py:40-42`) and `EXIT_CODES` (`runner.py:55-57`) both place it on the loop-logic side; membership fans out to every consumer for free.
- For Option B, it reuses the `interrupted`/`signal` exclusion mechanically, but that precedent's stated rationale doesn't transfer to `no_route` per ENH-3471's own Motivation text, and `workdir_vanished` (an infra-loss case still bucketed as flagging `"error"`) undercuts the "infra-like therefore excluded" analogy it relies on.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/logs.py` — `_derive_loop_outcome()` (`:2058-2083`): reorder the `terminated_by` check ahead of the `"error" in event` fallback for the `no_route` case only, per Expected Behavior.
- `scripts/little_loops/cli/logs.py` — `_FLAG_OUTCOMES` (`:1188`, `frozenset({"error", "max-steps", "stalled", "failed"})`): add `"no_route"` to this frozenset (decided — Option A, see `### Decision Rules` below and `## Proposed Solution` → `### Decision Rationale`). This frozenset is also the flagging-failure set consumed by `is_flagged()` (`:1191-1210`) and the "Delta vs baseline" table's column set (`outcome_keys = sorted(_FLAG_OUTCOMES)`, `:2570`), so the change has effects beyond bucket labeling.
- `docs/runbooks/FLEET_LOOP_REVIEW.md` — outcome-vocabulary block (`:93-97`, the `` converged | failed | error | max-steps | stalled | interrupted | signal `` fenced line) and the flagging-rule bullets (`:90-104`) per Expected Behavior. The prose at `:90-91` ("one of the four failure outcomes: `error`, `max-steps`, `stalled`, `failed`") and `:99` ("Only `error`, `max-steps`, `stalled`, and `failed` count as flagging failures") both need `no_route` added and the count word updated to five. This is the only place in `docs/` this vocabulary is enumerated (confirmed by a repo-wide search).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py:1112` — `_LoopRunRecord.outcome` dataclass field carries an inline comment enumerating the vocabulary verbatim (`# converged / failed / error / max-steps / stalled / interrupted / signal`); not consumed programmatically, but reads as incomplete once `no_route` is a live bucket. Add `no_route` to the comment.

_Review pass — 2026-09-15:_
- `scripts/little_loops/cli/logs.py:1191-1210` — `is_flagged()` docstring explains the `_FLAG_OUTCOMES` boundary (which buckets are operator/infra exits and therefore excluded). Once `no_route` joins the frozenset, add one sentence stating that `no_route` is *included* as a loop-authoring failure (ENH-3471/ENH-3482), so the docstring and the runbook's `:99-104` paragraph tell the same story. This is a public function consumed by `fleet_improve.py`, so its docstring is the canonical rule text.

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
- `scripts/tests/test_ll_logs.py`, class `TestLoopFleet` — add `test_derive_outcome_no_route_with_error` (event carries `terminated_by="no_route"` plus an `error` key; asserts `"no_route"`, proving the new branch wins over the `"error" in event` fallback) and `test_derive_outcome_no_route_without_error` (same `terminated_by`, no `error` key; asserts `"no_route"`). Mirrors the `workdir_vanished` pair at `:5175`/`:5181`.
- `scripts/tests/test_ll_logs.py`, class `TestIsFlaggedParity` (`:6651`) — its `top_outcome` parametrize list at `:6660` (`["converged", "failed", "error", "max-steps", "stalled", "interrupted", "signal"]`) is a second, separate hardcoded outcome-vocabulary enumeration site. Add `"no_route"` to it (decided — Option A).
- Delta-table safety: no existing test asserts on the "Delta vs baseline" header row (repo-wide search for `Δ`/`Delta vs baseline` in `test_ll_logs.py` finds nothing), so the new `Δno_route` column cannot break a snapshot assertion.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py:5927` — `test_flag_loops_each_flag_outcome_flags_via_outcome_clause`, parametrized over `sorted(_FLAG_OUTCOMES)`. This is the "self-extending parametrized test" the Decision Rationale (`## Proposed Solution` → `### Decision Rationale`) credits for Option A but does not cite by location — once `"no_route"` is added to `_FLAG_OUTCOMES`, this test automatically gains a `no_route` case with no edit required. No action needed beyond the `_FLAG_OUTCOMES` change itself; listed for verification.

### Documentation

- `docs/runbooks/FLEET_LOOP_REVIEW.md:82-104` — the vocabulary section's established shape: (1) the flagging-rule bullets name the four failure outcomes inline as prose, (2) a fenced code block lists the *complete* vocabulary as one `|`-delimited line in the same left-to-right order as the branches in `_derive_loop_outcome()`, (3) a following paragraph names the excluded subset and states why. A `no_route` addition should follow this same three-part shape rather than freeform prose.
- `docs/reference/CLI.md` — confirmed no outcome-vocabulary text present (flag/usage documentation only); no change needed there.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:5039` — the `loop-fleet` CLI reference entry states "derives outcome (`converged`/`failed`/`max-steps`/`stalled`/`interrupted`/`error`)" — a second outcome-vocabulary enumeration site (independent of `docs/runbooks/FLEET_LOOP_REVIEW.md`) tied to the same `_derive_loop_outcome()` function, missing `no_route`. Add `no_route` to this list.

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

- **Decided** (`/ll:decide-issue`, 2026-09-15): `terminated_by="no_route"` counts as a fleet-review *flagging* failure — `"no_route"` is added to `_FLAG_OUTCOMES` (`logs.py:1188`), Option A. See `## Proposed Solution` → `### Decision Rationale` for scoring and evidence.
- **Inputs**: the `_FLAG_OUTCOMES` frozenset (`logs.py:1188`); membership is binary (add `"no_route"` or don't).
- **Effect**: `is_flagged()` treats a loop whose `top_outcome` is `no_route` as unhealthy, and the "Delta vs baseline" table gains a dedicated `Δno_route` column.
- **Decided** (review pass, 2026-09-15): bucket label is `"no_route"` (underscore), not `"no-route"`. The `max_steps` → `max-steps` divergence is permitted, not required; matching the wire token here keeps `terminated_by`, `EXIT_CODES`, `fsm/types.py`, the runbook, and the Δ column greppable by one string. Do not normalize to the hyphen form during implementation.

## Scope Boundaries

- **In scope**: `_derive_loop_outcome()`, its tests, the fleet-review runbook, and any fleet-review summary table that enumerates outcome buckets.
- **Out of scope**: the executor, `ExecutionResult`, and every consumer ENH-3471 already widens. Do not start until ENH-3471 has landed — the value does not exist before then. (Review pass 2026-09-15: ENH-3471 is `done`; this gate is satisfied.)
- **Out of scope**: other `terminated_by` values that `_derive_loop_outcome()` still folds into `converged`/`failed` by `final_state` heuristics (`stall_detected`, `host_pressure_abort`, `host_budget_exceeded`, `cost_ceiling_exceeded`). Noted for a possible follow-up; not part of this change.

## Parent Issue

Decomposed from ENH-3468. Follow-up to ENH-3471, which explicitly defers this under its Scope Boundaries ("Deliberately deferred — fleet-review outcome bucketing").

## Resolution

Implemented Option A exactly as decided:

- `_derive_loop_outcome()` (`scripts/little_loops/cli/logs.py`) now checks `terminated_by == "no_route"` before the `"error" in event` fallback and returns `"no_route"`.
- `"no_route"` added to `_FLAG_OUTCOMES`, so `is_flagged()` and the Delta-vs-baseline table's `outcome_keys` pick it up automatically; `is_flagged()`'s docstring updated to state `no_route` is included as a loop-authoring failure.
- `_LoopRunRecord.outcome`'s inline vocabulary comment updated to include `no_route`.
- `docs/runbooks/FLEET_LOOP_REVIEW.md` updated: "four failure outcomes" → "five", the fenced vocabulary line, and a new paragraph explaining `no_route`.
- `docs/reference/API.md`'s `loop-fleet` outcome-vocabulary enumeration updated to include `no_route`.
- Added `test_derive_outcome_no_route_with_error` / `test_derive_outcome_no_route_without_error` to `TestLoopFleet`, mirroring the `workdir_vanished` pair. Added `"no_route"` to `TestIsFlaggedParity`'s `top_outcome` parametrize list.

Verification: `python -m pytest scripts/tests/test_ll_logs.py` (447 passed), `ruff check` and `mypy` clean on changed files, full suite `python -m pytest scripts/tests/` (24526 passed, 51 skipped, 1 pre-existing unrelated failure — `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo`, confirmed failing on main before this change via `git stash`).

No `## Program Design` deviations — implementation matches the documented Types/Signatures/Call Path exactly.

## Status

**Open** | Created: 2026-09-15 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-09-16T01:37:06 - `5a0f58ef-de60-48a1-82e6-e3b78dff2c6b.jsonl`
- `/ll:confidence-check` - 2026-09-16T01:18:33 - `2f2bf031-3f5c-40d9-b9d6-836752f92654.jsonl`
- `/ll:verify-issues` - 2026-09-16T01:15:24 - `48e5fa4b-67af-4adc-99aa-ea7f31e90c78.jsonl`
- `/ll:wire-issue` - 2026-09-16T01:08:26 - `0b73baa1-755e-43aa-bf89-93ccf29c9752.jsonl`
- `/ll:decide-issue` - 2026-09-16T00:52:53 - `f3b728bf-d5f0-4c49-9606-35ed513fee07.jsonl`
- `/ll:refine-issue` - 2026-09-15T23:47:51 - `00985229-ae90-46cd-ac9a-bd0275ccc50b.jsonl`
- `/ll:format-issue` - 2026-09-15T23:38:43 - `40022929-8f22-431e-874e-951b8ed315e8.jsonl`
