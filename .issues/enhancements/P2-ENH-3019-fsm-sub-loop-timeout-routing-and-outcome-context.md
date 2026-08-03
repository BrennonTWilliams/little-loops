---
id: ENH-3019
title: FSM sub-loop states can't distinguish timeout from normal on_no, and expose no outcome context
type: enhancement
status: open
captured_at: "2026-08-02T00:00:00Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
parent: EPIC-3022
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

1. A parent state with `loop: ...` can declare an `on_timeout` route, distinct from `on_no`, that fires when the sub-loop's `terminated_by` is `timeout` (and reasonably, `max_iterations`/`signal` too, or a separate route per reason if that's cleaner).
2. After a `loop:` state completes, the sub-loop's termination reason is exposed to the parent as an interpolatable context value (e.g. `${context.sub_loop_outcome}` or similar), so a downstream action/prompt in the parent (e.g. a salvage/partial-synthesis state) can reference *why* the sub-loop ended without re-deriving it.
3. `on_timeout` is optional — states that don't declare it keep falling through to `on_no`, preserving backward compatibility with existing loop YAMLs.

## Motivation

Without this, any loop with a `loop:` sub-state and a bounded parent `timeout:` will treat transient budget exhaustion identically to genuine failure, discarding partial/recoverable work behind a `failed` terminal. This is a structural gap in the sub-loop feature ([[FEAT-659]]), not specific to the `deep-research` loop — any future loop composing sub-loops under a timeout hits the same trap.

## Proposed Solution

- Add `on_timeout` to the per-state schema in `fsm-loop-schema.json` alongside the existing `on_*` routes.
- In `FSMExecutor._execute_loop_state`, branch on `terminated_by == "timeout"` → `on_timeout` (falling back to `on_no` if unset), before the generic catch-all.
- Write `terminated_by` (and possibly `failure_terminal`) from the child `ExecutionResult` into the parent's `context` (or a dedicated namespace, e.g. `context.sub_loop.terminated_by`) immediately after a `loop:` state resolves, so it's available for interpolation in the state that `on_timeout`/`on_no` routes to next.
- Reuse the existing `context_passthrough`/`capture` merge point in the same function as the insertion site.

## Impact

- **Priority**: P2 — not user-facing broken behavior, but a structural gap that silently discards recoverable work in any loop composing a sub-loop under a timeout; will recur for future sub-loop-based loops.
- **Effort**: Medium — schema addition, one new executor branch, one new context-write; needs unit test coverage for the new routing path and a regression test loop fixture.
- **Risk**: Low — additive/optional field, falls back to existing `on_no` behavior when unset.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-08-03T04:47:07 - `5a7d81b1-25c9-41ad-aa83-d576490531fd.jsonl`

---

## Status

**Open** | Created: 2026-08-02 | Priority: P2
