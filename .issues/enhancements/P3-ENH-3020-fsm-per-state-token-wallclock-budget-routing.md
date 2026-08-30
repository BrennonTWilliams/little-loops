---
id: ENH-3020
title: No per-state/iteration token or wall-clock budget routing primitive in FSM loops
type: enhancement
status: cancelled
captured_at: "2026-08-02T00:00:00Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
parent: EPIC-3022
verify_verdict: NON_VALID
priority: P3
relates_to:
- BUG-3360
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

## Cancellation Rationale (2026-08-29)

Cancelled deliberately: **both halves of this ask already exist**, and the one
genuinely broken thing underneath is a dead-knob defect, not a new primitive.
Re-filed as **BUG-3360**.

### The wall-clock half is shipped

`max_seconds_per_state` is a rename of `StateConfig.timeout`, which has existed
alongside `idle_timeout`, and the loop-level `default_timeout` /
`default_idle_timeout` (`fsm/schema.py:708-709,1395-1397`). The routing this
issue asks for landed with **ENH-3019** (done, 2026-08-04):

- `fsm/executor.py:1089-1099` — a sub-loop's timeout is clamped to the parent's
  *remaining* wall-clock budget, with the code comment stating the intent
  verbatim: "leaving wall-clock headroom for an `on_timeout` salvage state."
- `fsm/executor.py:1162-1174` — `on_timeout` route fires on
  timeout / `max_steps` / `max_iterations_reached`.
- `${prev.timeout_kind}` (`"idle"` / `"wall"`, `fsm/interpolation.py:119-124`)
  is interpolation-accessible, so non-sub-loop states can guard-route on
  *why* they were killed.

That is the "route to salvage before the global timeout forces a hard stop"
scenario in the Motivation, already available to authors.

### The token half is declared but inert

**ENH-2477** (done, 2026-07-07) already added `StateConfig.cost_ceiling` —
`cost_ceiling_per_state` (USD) and `cost_warn_at` — with full
`to_dict`/`from_dict` (`fsm/schema.py:397-434,735,846-847,888-890,960`) and
validation (`fsm/validation/structural_rules.py:755-831`). But it has **no
runtime consumer**: `grep -n "cost_ceiling" fsm/executor.py` returns nothing,
and the only other references anywhere are validation tests. Its documented
companion, FEAT-2476's global `--max-cost`, was cancelled.

So the schema already carries a per-state spend cap that `ll-loop validate`
accepts and the executor ignores. Building `max_tokens_per_iteration` on top
would add a *second* declarative spend cap beside an inert first one.

### Proliferation

Time-based knobs already in this layer: loop `timeout`, `default_timeout`,
`default_idle_timeout`, state `timeout`, state `idle_timeout`, advisor
`timeout`, llm `timeout`, `rate_limit_max_wait_seconds`,
`rate_limit_backoff_base_seconds`, `rate_limit_long_wait_ladder` — plus
`stall_detector`, `rate_limit_circuit`, and `host_guard`'s memory budget.
`max_seconds_per_state` would be the eleventh and a synonym for the fourth.
Same reasoning that cancelled ENH-3129.

### Supporting facts

- The originating evidence is a single `deep-research` run
  (`deep-research-loop-analysis-2026-08-03.md`), whose specific failure — a
  sub-loop consuming the global budget — is exactly what ENH-3019's clamp
  fixed.
- The Scope Boundary note on EPIC-3022 (added by `/ll:audit-issue-conflicts`)
  flagged an unresolved collision with EPIC-3041's FEAT-3038/FEAT-3039, which
  independently add a second "route on running out of X" shape to the same
  layer. That question was never answered and is now carried on BUG-3360.
- No dependency edges: nothing declares `blocked_by`/`depends_on` against this.

**Revisit trigger:** a real run where a state burns a material amount of spend
*inside* its wall-clock timeout (e.g. parallel subagents) and BUG-3360's
resolution proves insufficient. Absent that, per-state cost stays observable
after the fact via `fsm/cost_graph.py` and `/ll:debug-loop-run`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:04:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:capture-issue` - 2026-08-03T04:47:42 - `fc4018c9-c28b-4e18-b285-18cc2e719c73.jsonl`

---

## Status

**Cancelled** | Created: 2026-08-02 | Cancelled: 2026-08-29 | Priority: P3

Superseded in substance by ENH-3019 (wall-clock half, done) and BUG-3360
(token/cost half, re-filed as a dead-knob defect).
