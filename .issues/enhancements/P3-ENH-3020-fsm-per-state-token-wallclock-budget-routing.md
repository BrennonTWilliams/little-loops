---
id: ENH-3020
title: No per-state/iteration token or wall-clock budget routing primitive in FSM loops
type: enhancement
status: open
captured_at: "2026-08-02T00:00:00Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
---

# No per-state/iteration token or wall-clock budget routing primitive in FSM loops

## Summary

FSM loops can guard against subprocess memory pressure via `host_guard.py`'s `on_budget_exceeded`, but there is no equivalent routing hook for token spend or per-state wall-clock duration. Per-step token/duration numbers are already emitted into the event stream (observable after the fact via `/ll:debug-loop-run`), but a loop author cannot route on them *during* a run — the only backstop against runaway spend is the loop-global `timeout:`, which fires without regard to which state or iteration consumed the budget.

## Context

Surfaced by `/ll:debug-loop-run` analysis of a `deep-research` run (`deep-research-loop-analysis-2026-08-03.md`, Finding 5 / Recommendation D). The run spent ~640k input + ~95k output tokens across 18 sub-loop step-events before the global 3600s timeout fired; the most expensive single state (`search_web` iteration 5) alone cost 102k input tokens and 526s wall-clock. Because there's no per-state/iteration budget signal available to the FSM at routing time, the loop had no way to short-circuit ("this iteration is already over budget, salvage now") before the global timeout forced a hard stop mid-state.

## Current Behavior

`host_guard.py` tracks cumulative subprocess RSS memory and exposes `on_budget_exceeded`/`budget_state` for that signal only. Per-step token counts and durations are recorded in the event stream (used post-hoc by `/ll:debug-loop-run`'s token analysis) but are not accumulated into any context variable or compared against a configurable threshold during execution — there is no token/time analogue to `on_budget_exceeded`.

## Expected Behavior

A loop author can optionally configure a per-state or per-iteration token/wall-clock budget (e.g. `max_tokens_per_iteration`, `max_seconds_per_state`) and declare a route (e.g. `on_budget_exceeded` reused, or a new `on_iteration_budget_exceeded`) that fires when it's exceeded — allowing early, in-run routing to a salvage/synthesis path instead of relying solely on the global loop `timeout:`.

## Motivation

Without this, the only cost control is a single global timeout that fires blind to which state or iteration is responsible, forcing the loop into whatever `on_no`/`on_error` terminal state it happens to be in — not a state the author can choose based on cumulative spend. This is the same class of problem as [[ENH-3019]] (timeout routing) but at the per-state/iteration granularity rather than whole-sub-loop granularity, and would let a loop degrade gracefully (route to synthesis) before the outer timeout forces a hard stop mid-action.

## Proposed Solution

- Add optional per-state/loop-level config keys (e.g. `max_tokens_per_iteration`, `max_seconds_per_state`) to the FSM schema.
- Accumulate token/duration figures already present in the event stream into a context-accessible counter during execution (reusing the existing event-emission code path rather than adding new instrumentation).
- Add a routing hook analogous to `host_guard.py`'s `on_budget_exceeded` that the executor checks after each state/iteration completes.
- Keep this fully optional/backward-compatible — loops without the new config keys behave exactly as today.

## Impact

- **Priority**: P3 — improves debuggability and graceful degradation, but the global `timeout:` is a working (if blunt) backstop today; not blocking any current loop.
- **Effort**: Medium — needs schema additions, a new executor check reusing existing token/duration bookkeeping, and test coverage for the new routing path.
- **Risk**: Low — additive/optional, no change to existing loop behavior when unset.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-08-03T04:47:42 - `fc4018c9-c28b-4e18-b285-18cc2e719c73.jsonl`

---

## Status

**Open** | Created: 2026-08-02 | Priority: P3
