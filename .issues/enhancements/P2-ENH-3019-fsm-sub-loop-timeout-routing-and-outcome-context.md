---
id: ENH-3019
title: FSM sub-loop states can't distinguish timeout from normal on_no, and expose
  no outcome context
type: enhancement
status: open
captured_at: '2026-08-02T00:00:00Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
parent: EPIC-3022
confidence_score: 100
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
---

# FSM sub-loop states can't distinguish timeout from normal on_no, and expose no outcome context

## Summary

A parent FSM state that invokes a sub-loop (`loop: ...`) routes the sub-loop's result using only `on_yes`/`on_no`/`on_error`. A sub-loop that times out (or hits `max_iterations`, or is interrupted by a signal) is routed identically to a sub-loop that completed normally and evaluated to a real "no" — there is no `on_timeout` route, and no context variable is exposed that tells the parent *how* the sub-loop terminated. A loop author cannot write a parent state that reacts differently to "the sub-loop ran out of budget while still producing useful partial work" versus "the sub-loop finished and genuinely failed its convergence check."

## Context

Surfaced by `/ll:debug-loop-run` analysis of a `deep-research` run (`deep-research-loop-analysis-2026-08-03.md`, Finding 2 / Recommendation B). The `research-coverage` sub-loop timed out mid-iteration with substantial research artifacts already on disk (`knowledge-base.md`, 418 lines). Because the parent's `run_research` state only has `on_yes: done` / `on_no: failed` / `on_error: failed`, the timeout was routed to `failed`, discarding a recoverable run behind a permanent failure terminal. The loop author cannot fix this today by editing YAML — the routing distinction and the context field it would need don't exist in the framework.

Related: [[FEAT-659]] (Hierarchical FSM Loops) introduced sub-loop states but did not include timeout-outcome routing.

## Current Behavior

`FSMExecutor._execute_loop_state` (`scripts/little_loops/fsm/executor.py:1038-1051`) branches only on:
- `terminated_by == "terminal"` → `on_yes`/`on_no` (by `failure_terminal`)
- `terminated_by == "error"` → `on_error`
- everything else (`timeout`, `max_iterations`, `signal`, ...) falls through to the `on_no` branch

The state schema (`scripts/little_loops/fsm/fsm-loop-schema.json`) has no per-state `on_timeout` key — only `on_yes/on_success/on_no/on_failure/on_error/on_maintain/on_partial/on_blocked/on_retry_exhausted/on_rate_limit_exhausted/on_throttle_hard` plus top-level `on_max_steps/on_max_iterations/on_handoff`.

`terminated_by` and `failure_terminal` exist on the internal `ExecutionResult` (`scripts/little_loops/fsm/types.py:35-60`) and are consumed inline by the executor for routing, but are never written into `context`/`captured` after the loop state completes. Only `state.capture`/`context_passthrough` merges the child's *captured action output* — not its termination metadata.

## Expected Behavior

1. A parent state with `loop: ...` can declare an `on_timeout` route, distinct from `on_no`, that fires when the sub-loop's `terminated_by` is a **budget-exhaustion** reason — `timeout`, `max_steps`, or `max_iterations_reached` — the cases where the sub-loop was cut off mid-work rather than reaching a real conclusion. `terminated_by` has other values (`interrupted`, `user_stopped`, `system_signal`, `cycle_detected`, `stall_detected`, `host_pressure_abort`, `host_budget_exceeded`, `handoff`) that are semantically distinct from budget exhaustion (external interruption, detected pathology, host-level abort) and are out of scope for `on_timeout`; they keep falling through to the existing `on_no`/`on_error` handling unchanged.
2. After a `loop:` state completes, the sub-loop's termination reason is exposed to the parent as an interpolatable context value (e.g. `${context.sub_loop_outcome}` or similar), so a downstream action/prompt in the parent (e.g. a salvage/partial-synthesis state) can reference *why* the sub-loop ended without re-deriving it.
3. `on_timeout` is optional — states that don't declare it keep falling through to `on_no`, preserving backward compatibility with existing loop YAMLs.

## Motivation

Without this, any loop with a `loop:` sub-state and a bounded parent `timeout:` will treat transient budget exhaustion identically to genuine failure, discarding partial/recoverable work behind a `failed` terminal. This is a structural gap in the sub-loop feature ([[FEAT-659]]), not specific to the `deep-research` loop — any future loop composing sub-loops under a timeout hits the same trap.

## Proposed Solution

- Add `on_timeout` to the per-state schema in `fsm-loop-schema.json` alongside the existing `on_*` routes.
- In `FSMExecutor._execute_loop_state`, branch on `terminated_by in ("timeout", "max_steps", "max_iterations_reached")` → `on_timeout` (falling back to `on_no` if unset), before the generic catch-all. All other non-`terminal`/`error` values (`interrupted`, `user_stopped`, `system_signal`, `cycle_detected`, `stall_detected`, `host_pressure_abort`, `host_budget_exceeded`, `handoff`) keep falling through to `on_no` exactly as today — this issue only carves budget-exhaustion reasons out of that catch-all, it does not add routing for the others.
- Write `terminated_by` (and possibly `failure_terminal`) from the child `ExecutionResult` into the parent's `context` (or a dedicated namespace, e.g. `context.sub_loop.terminated_by`) immediately after a `loop:` state resolves, so it's available for interpolation in the state that `on_timeout`/`on_no` routes to next — this covers all `terminated_by` values, not just the budget-exhaustion set, so a downstream state can still distinguish e.g. `interrupted` from `on_no`'s other causes via context even without a dedicated route.
- Reuse the existing `context_passthrough`/`capture` merge point in the same function as the insertion site.

## Program Design

### Types

- `on_timeout: str | None` — new optional field on `StateConfig` (`scripts/little_loops/fsm/types.py`), alongside the existing `on_yes`/`on_no`/`on_error` routes; mirrored as a new `"on_timeout"` property in `fsm-loop-schema.json`, same shape as `"on_no"`.

### Signatures

- `_execute_loop_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None` — existing method (`scripts/little_loops/fsm/executor.py:1038-1056`); gains a branch for budget-exhaustion `terminated_by` values before the generic catch-all, and an unconditional `captured` merge for termination metadata.

### Call Path

- `_execute_loop_state()` -> checks `child_result.terminated_by in ("timeout", "max_steps", "max_iterations_reached")` -> if true and `state.on_timeout` set: `interpolate(state.on_timeout, ctx)`; if true and unset: falls back to `interpolate(state.on_no, ctx)` (existing behavior, unchanged).
- `_execute_loop_state()` -> immediately after resolving `child_result` (before the existing `terminated_by == "terminal"` check), merge termination metadata into `self.captured`, independent of the existing `context_passthrough`/`with_` conditional:
  ```python
  self.captured.setdefault(self.current_state, {})["terminated_by"] = child_result.terminated_by
  if child_result.failure_terminal:
      self.captured[self.current_state]["failure_terminal"] = child_result.failure_terminal
  ```
- Downstream state reads it back via `_get_nested()` — the existing `captured` namespace (`interpolation.py`, reused, not reimplemented) — as `${captured.<state_name>.terminated_by}`. Keyed per-state, so multiple `loop:` states in the same FSM don't collide, unlike a shared `context.sub_loop.*` key would.

## Impact

- **Priority**: P2 — not user-facing broken behavior, but a structural gap that silently discards recoverable work in any loop composing a sub-loop under a timeout; will recur for future sub-loop-based loops.
- **Effort**: Medium — schema addition, one new executor branch, one new context-write; needs unit test coverage for the new routing path and a regression test loop fixture.
- **Risk**: Low — additive/optional field, falls back to existing `on_no` behavior when unset.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-08-03_

**Readiness Score**: 100/100 → GO
**Outcome Confidence**: 84/100 → HIGH

Prior gaps resolved: the `## Program Design` section now populates concrete types/signatures/call path and the gate (`ll-issues check-design`) passes; the context-field naming decision is settled (`captured.<state_name>.terminated_by`, reusing the existing `captured` namespace). No open gaps or outcome risk factors remain.

## Session Log
- `/ll:confidence-check` - 2026-08-04T03:59:35 - `d555d105-f29e-4b14-98af-4d8c64f9a264.jsonl`
- `/ll:confidence-check` - 2026-08-04T03:28:40 - `9c548141-be99-455c-88a5-bcdf93e70312.jsonl`
- `/ll:capture-issue` - 2026-08-03T04:47:07 - `5a7d81b1-25c9-41ad-aa83-d576490531fd.jsonl`

---

## Status

**Open** | Created: 2026-08-02 | Priority: P2
