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
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
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

### The sub-loop has no budget of its own

`_execute_loop_state` clamps the child's timeout to the parent's **entire remaining** wall-clock budget (`executor.py:1016-1021`):

```python
remaining_s = max(1, int((self.fsm.timeout * 1000 - elapsed_ms) // 1000))
if child_fsm.timeout is None or child_fsm.timeout > remaining_s:
    child_fsm.timeout = remaining_s
```

`state.timeout` is **not** consulted for `loop:` states — it is only read when executing shell/slash actions (`executor.py:1825`, `1835`, `1866`, `2670`). So a loop author cannot give a sub-loop a budget smaller than the parent's remaining time.

This is load-bearing for this issue. In `deep-research.yaml` the parent is `timeout: 3600` and `oracles/research-coverage.yaml` is also `timeout: 3600`; the child is therefore clamped to the parent's remaining budget and times out *at* the parent's own deadline. Control returns to the parent's run loop, which checks the timeout at the top of the next iteration (`executor.py:546-568`) and immediately calls `_finish("timeout")`. **A state reached via `on_timeout` would never execute.** Adding the route alone leaves it unreachable in exactly the scenario that motivated this issue.

### `on_timeout` already parses today

`stateConfig` in `fsm-loop-schema.json` declares `patternProperties: {"^on_": ...}`, and `StateConfig.from_dict` (`scripts/little_loops/fsm/schema.py:835-852`) funnels any unrecognized `on_*` string key into `extra_routes`. So `on_timeout: salvage` in a loop YAML **today** already: passes JSON-schema validation, parses into `state.extra_routes["timeout"]`, has its target reference-checked (`schema.py:945`, `refs.update(self.extra_routes.values())`), and renders as a graph edge (`cli/loop/layout.py:460`). The only thing missing is an executor branch that consumes it for `loop:` states — where `extra_routes` is otherwise inert, because a `loop:` state has no evaluator to produce a verdict (`executor.py:2270-2272`).

## Expected Behavior

1. A parent state with `loop: ...` can declare an `on_timeout` route, distinct from `on_no`, that fires when the sub-loop's `terminated_by` is a **budget-exhaustion** reason — `timeout`, `max_steps`, or `max_iterations_reached` — the cases where the sub-loop was cut off mid-work rather than reaching a real conclusion. `terminated_by` has other values (`interrupted`, `user_stopped`, `system_signal`, `cycle_detected`, `stall_detected`, `host_pressure_abort`, `host_budget_exceeded`, `handoff`) that are semantically distinct from budget exhaustion (external interruption, detected pathology, host-level abort) and are out of scope for `on_timeout`; they keep falling through to the existing `on_no`/`on_error` handling unchanged.
2. After a `loop:` state completes, the sub-loop's termination reason is exposed to the parent as an interpolatable context value (e.g. `${context.sub_loop_outcome}` or similar), so a downstream action/prompt in the parent (e.g. a salvage/partial-synthesis state) can reference *why* the sub-loop ended without re-deriving it.
3. `on_timeout` is optional — states that don't declare it keep falling through to `on_no`, preserving backward compatibility with existing loop YAMLs.
4. A `loop:` state can bound its sub-loop below the parent's remaining budget by declaring `timeout:` on the state, leaving wall-clock headroom for the salvage state that `on_timeout` routes to. Without this, `on_timeout` is unreachable whenever the child's budget is clamped to the parent's deadline (see Current Behavior). The child's effective cap becomes `min(state.timeout, parent_remaining)`; when `state.timeout` is unset, behavior is unchanged from today.

**Scope note**: the budget-exhaustion set is read off the *child's* `ExecutionResult.terminated_by` only. A parent-level cap firing (parent `max_steps`, parent `timeout` at the top of the run loop) terminates the parent directly and never reaches this routing code. `terminated_by == "handoff"` is likewise out of scope here — a sub-loop handoff routing to `on_no` is the same class of gap but is tracked separately, not fixed by this issue.

## Motivation

Without this, any loop with a `loop:` sub-state and a bounded parent `timeout:` will treat transient budget exhaustion identically to genuine failure, discarding partial/recoverable work behind a `failed` terminal. This is a structural gap in the sub-loop feature ([[FEAT-659]]), not specific to the `deep-research` loop — any future loop composing sub-loops under a timeout hits the same trap.

## Proposed Solution

Three changes, all in `FSMExecutor._execute_loop_state` (`scripts/little_loops/fsm/executor.py`):

- **Consume `on_timeout` via the existing `extra_routes` mechanism, not a new first-class field.** Branch on `child_result.terminated_by in ("timeout", "max_steps", "max_iterations_reached")` → `state.extra_routes.get("timeout")`, falling back to `on_no` when unset, placed before the generic catch-all. All other non-`terminal`/`error` values (`interrupted`, `user_stopped`, `system_signal`, `cycle_detected`, `stall_detected`, `host_pressure_abort`, `host_budget_exceeded`, `handoff`) keep falling through to `on_no` exactly as today — this issue only carves budget-exhaustion reasons out of that catch-all, it does not add routing for the others.

  **Do not** promote `on_timeout` to a first-class `StateConfig` field. `extra_routes` already gives it schema acceptance, target-reference validation, and graph edges (see Current Behavior). Promoting it means adding the key to `_known_on_keys`, `to_dict`, `from_dict`, `referenced_states()` (`schema.py:920-945`), `topology.py:_SHORTHAND_KINDS`, and `layout.py` edge extraction — and **omitting any of the last three is a silent regression** versus today's behavior: the route's target would stop being reference-checked and would vanish from rendered diagrams. If a future issue does promote it, all six sites must move together.

- **Honor `state.timeout` as the sub-loop's cap.** In the existing clamp block (`executor.py:1016-1021`), take the child's budget as `min(state.timeout, parent_remaining)` when `state.timeout` is set, instead of always widening to `parent_remaining`. This is what makes an `on_timeout` target reachable; without it the parent's own deadline fires first (see Current Behavior).

- **Write the child's termination metadata into `captured`** so a downstream state can interpolate it. This covers all `terminated_by` values, not just the budget-exhaustion set, so a salvage state can still distinguish e.g. `interrupted` from `on_no`'s other causes without a dedicated route.

Follow-up (not required for this issue to land): `deep-research.yaml`'s `run_research` state should gain a `timeout:` below the parent's 3600 plus an `on_timeout:` salvage state, since that loop is the motivating case and would otherwise still discard partial research.

## Program Design

### Types

- **No new types, no new dataclass fields, no schema change.** `on_timeout: <state>` is already accepted by `fsm-loop-schema.json` (`stateConfig.patternProperties["^on_"]`) and already parsed into the existing `StateConfig.extra_routes: dict[str, str]` as key `"timeout"` (`scripts/little_loops/fsm/schema.py:835-852`). Note `StateConfig` lives in `fsm/schema.py:571` — `fsm/types.py` holds `ExecutionResult`, not `StateConfig`.
- `StateConfig.timeout: int | None` already exists (`schema.py`); this issue extends its meaning to cover `loop:` states, which currently ignore it.

### Signatures

- `_execute_loop_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None` — existing method (`scripts/little_loops/fsm/executor.py:~940-1057`). Signature unchanged; gains (a) a `state.timeout` term in the child-budget clamp, (b) a `captured` write for termination metadata, (c) a budget-exhaustion branch before the generic catch-all.

### Call Path

**(a) Child budget clamp** — `executor.py:1016-1021`, replacing the unconditional widen:

```python
if self.fsm.timeout:
    elapsed_ms = _now_ms() - self.start_time_ms + self.elapsed_offset_ms
    remaining_s = max(1, int((self.fsm.timeout * 1000 - elapsed_ms) // 1000))
    cap = min(state.timeout, remaining_s) if state.timeout else remaining_s
    if child_fsm.timeout is None or child_fsm.timeout > cap:
        child_fsm.timeout = cap
```

When `self.fsm.timeout` is unset but `state.timeout` is set, the child must still be capped at `state.timeout` — handle that as a separate branch rather than leaving it inside the `if self.fsm.timeout:` guard.

**(b) Termination metadata** — written **after** the existing `context_passthrough`/`with_` merge, never before. That merge does a whole-dict overwrite:

```python
if (state.context_passthrough or state.with_) and child_executor.captured:
    self.captured[self.current_state] = child_executor.captured   # clobbers prior writes
```

so a `setdefault` placed ahead of it is silently discarded whenever `with:` is set — which is the `deep-research` configuration. Correct placement is immediately after that block and before the `terminated_by == "terminal"` check:

```python
self.captured.setdefault(self.current_state, {})["terminated_by"] = child_result.terminated_by
if child_result.failure_terminal:
    self.captured[self.current_state]["failure_terminal"] = child_result.failure_terminal
```

Sibling entries under this key are `{"output":..., "exit_code":...}` dicts, so a bare string value is heterogeneous — this matches the precedent already set by the `on_error` branch (`executor.py:1051`, `...["error"] = child_result.error`).

**(c) Routing** — `_execute_loop_state()` checks `child_result.terminated_by in ("timeout", "max_steps", "max_iterations_reached")`; if true and `state.extra_routes.get("timeout")` is set, `interpolate(...)` that target; if true and unset, fall back to `interpolate(state.on_no, ctx)` (existing behavior, unchanged).

**Read-back** — a downstream state reads it via `_get_nested()` on the existing `captured` namespace (`interpolation.py`, reused, not reimplemented) as `${captured.<state_name>.terminated_by}`. Keyed per-state, so multiple `loop:` states in the same FSM don't collide, unlike a shared `context.sub_loop.*` key would.

### Test Anchors

- `scripts/tests/test_fsm_executor.py` — the three routing cases (`on_timeout` set → fires; unset → falls back to `on_no`; `interrupted`/`handoff` → still `on_no`), the `min(state.timeout, remaining)` clamp, and the `captured` write surviving a `with:`-triggered passthrough overwrite.
- `scripts/tests/test_fsm_schema.py` — assert `on_timeout` still lands in `extra_routes` (guards against a future promotion silently dropping it).
- `scripts/tests/test_builtin_loops.py` — only if `deep-research.yaml` gains the salvage state in the follow-up.

## Impact

- **Priority**: P2 — not user-facing broken behavior, but a structural gap that silently discards recoverable work in any loop composing a sub-loop under a timeout; will recur for future sub-loop-based loops.
- **Effort**: Small — no schema or dataclass change (`on_timeout` already parses into `extra_routes`); three edits confined to `_execute_loop_state`: a `min()` in the budget clamp, a `captured` write, and one routing branch. Needs unit coverage per Test Anchors.
- **Risk**: **Medium**, concentrated entirely in the `state.timeout` change. The routing branch and the `captured` write are genuinely inert unless a state opts in (`extra_routes["timeout"]` is currently unread for `loop:` states since no evaluator produces verdicts there). But honoring `state.timeout` is a live behavior change — see Migration below.
- **Breaking Change**: No for the routing/context work; **yes in effect** for sub-loop budgets in the seven built-in states listed under Migration, unless their declarations are adjusted in the same change.

### Migration: `state.timeout` on existing `loop:` states

Seven built-in loop states already declare `timeout:` on a `loop:` state, where it is currently ignored. Making it authoritative newly caps those children:

| Loop | State | parent `timeout` | state `timeout` | effect |
|---|---|---|---|---|
| `rn-build` | `cluster_execute` | 86400 | 345600 | none (cap above parent remaining) |
| `rn-build` | `eval_gate` | 86400 | 7200 | **child capped 86400 → 7200** |
| `outer-loop-eval` | `run_sub_loop` | 14400 | 3600 | **child capped 14400 → 3600** |
| `loop-composer` | `dispatch_step` | 345600 | 3600 | **child capped 345600 → 3600** |
| `loop-composer-adaptive` | `dispatch_step` | 345600 | 3600 | **child capped 345600 → 3600** |
| `loop-router` | `dispatch` | 345600 | 3600 | **child capped 345600 → 3600** |
| `goal-cluster` | `dispatch_cluster` | 345600 | 3600 | **child capped 345600 → 3600** |

Six of seven would see their sub-loop budget drop by one to two orders of magnitude. A dispatched sub-loop that legitimately runs longer than an hour would begin terminating with `terminated_by="timeout"` and routing to `on_no` — a silent regression in the composer/router family, which is precisely the long-running-composition use case.

The declarations themselves suggest their authors *believed* `timeout:` was doing something, so honoring it is arguably fixing a latent bug rather than introducing one. Either way this issue must not land the clamp change without resolving it. Two options were considered:

1. **Honor `state.timeout` and audit all seven** — raise or delete each declaration to match its real intended budget. Correct semantics, one-time review cost, and it removes seven misleading no-op lines from the built-ins.
2. **Add a distinct opt-in key** (e.g. `sub_loop_timeout:`) and leave `state.timeout` ignored for `loop:` states. Zero migration risk, but leaves the existing seven declarations silently inert and adds a near-duplicate schema key.

#### Decision (2026-08-03): option 1, audited in this issue's diff — outcome "delete 6, raise 1"

Resolved. Option 1, with the audit landing in the **same diff** as the clamp, not
deferred. The audit's outcome is to *remove* the six risky declarations rather
than re-tune them, which eliminates the breaking change instead of accepting it:
the clamp ships as a new opt-in capability and no existing loop's effective
sub-loop budget moves.

Rationale for deletion over re-tuning: six of the seven declarations sit on
**dynamic dispatch** states — the sub-loop is selected at runtime
(`loop: "${captured.next_step_loop.output}"`, `"${captured.chosen.output}"`,
`"${context.input}"`, …). A hard-coded 3600 cannot be a considered budget for an
arbitrary dispatched loop; it is a placeholder written while the field was inert.
This is [[BUG-3032]]'s argument one level up — duration is not evidence of ill
health for agent work, and less so when the callee is unknown at authoring time.

| Loop | State | Now | Disposition | Effect vs. today |
|---|---|---|---|---|
| `loop-composer` | `dispatch_step` | 3600 | delete | none |
| `loop-composer-adaptive` | `dispatch_step` | 3600 | delete | none |
| `loop-router` | `dispatch` | 3600 | delete | none |
| `goal-cluster` | `dispatch_cluster` | 3600 | delete | none |
| `outer-loop-eval` | `run_sub_loop` | 3600 | delete | none |
| `rn-build` | `cluster_execute` | 345600 | delete | none — already a no-op above the parent; the value *is* "don't cap further" |
| `rn-build` | `eval_gate` | 7200 | raise to 14400 | none in practice (see below) |

`eval_gate` is the one retained cap. It dispatches a *generated* harness loop
modeled on the built-in `harness-*` templates, which declare 3600
(`harness-single-shot`), 7200 (`harness-optimize`,
`harness-plan-research-implement-report`), and 14400 (`harness-multi-item`). At
7200 a multi-item-shaped generated harness would be genuinely clipped; 14400
matches the widest template, so nothing regresses. Deleting it is also
defensible if the reviewer prefers zero retained caps.

**Objection considered — "deletion discards the authors' intent to bound
dispatch."** If bounding a dispatched sub-loop is genuinely wanted, it needs a
deliberate budget *plus* an `on_timeout` salvage route. A bare cap falling
through to `on_no` is exactly the work-discarding failure this issue exists to
fix, so re-arming six of them in this diff would be self-defeating. Bounding
belongs in the same follow-up that gives `deep-research.run_research` its
`timeout:` + `on_timeout:` pair.

#### Acceptance criteria (so the audit cannot be deferred)

- The seven YAML edits above land in the **same diff** as the
  `min(state.timeout, parent_remaining)` clamp in `_execute_loop_state`.
- `scripts/tests/test_builtin_loops.py` pins the post-audit set: no `loop:` state
  under `scripts/little_loops/loops/**` declares `timeout:` except
  `rn-build.eval_gate`. A future loop adding one without a matching `on_timeout`
  route fails the suite loudly rather than silently acquiring a work-discarding
  cap.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-08-03_

**Readiness Score**: 100/100 → GO
**Outcome Confidence**: 84/100 → HIGH

Prior gaps resolved: the `## Program Design` section now populates concrete types/signatures/call path and the gate (`ll-issues check-design`) passes; the context-field naming decision is settled (`captured.<state_name>.terminated_by`, reusing the existing `captured` namespace).

**Superseded by review on 2026-08-03** — scores above are stale; re-run `/ll:confidence-check` before implementing. Review findings folded into this issue:

1. **Feature was inert for its own motivating case.** The child's timeout is clamped to the parent's *entire* remaining budget (`executor.py:1016-1021`), so in `deep-research` the sub-loop times out at the parent's own deadline and the parent `_finish("timeout")`s before any `on_timeout` target can run. Fixed by adding the `state.timeout` clamp as a required part of this issue.
2. **`on_timeout` already parses today** via `stateConfig.patternProperties["^on_"]` + `StateConfig.extra_routes`. The proposed schema/dataclass addition was unnecessary and carried a silent-regression risk (dropping target validation and graph edges unless six enumeration sites moved together). Proposed Solution rewritten around `extra_routes`.
3. **Wrong file for `StateConfig`** — it lives in `fsm/schema.py:571`, not `fsm/types.py`. Corrected.
4. **`captured` write had an ordering hazard** — the proposed insertion point sat before the `context_passthrough`/`with_` whole-dict overwrite, which would have discarded it in exactly the `deep-research` configuration. Corrected to after.
5. **New open decision (blocking):** honoring `state.timeout` changes sub-loop budgets in seven existing built-in states, six of them by 1–2 orders of magnitude — see `## Impact` → Migration. Pick option 1 or 2 there before implementing.

Effort revised Medium → Small for the core change; risk revised Low → Medium on account of the migration.

## Session Log
- `/ll:confidence-check` - 2026-08-04T04:29:32 - `11dff0fa-9ec2-44f3-81e8-319ef1fb9543.jsonl`
- `/ll:confidence-check` - 2026-08-04T04:21:52 - `a8c8283a-aacf-4897-9443-5051bca3af37.jsonl`
- `/ll:confidence-check` - 2026-08-04T03:59:35 - `d555d105-f29e-4b14-98af-4d8c64f9a264.jsonl`
- `/ll:confidence-check` - 2026-08-04T03:28:40 - `9c548141-be99-455c-88a5-bcdf93e70312.jsonl`
- `/ll:capture-issue` - 2026-08-03T04:47:07 - `5a7d81b1-25c9-41ad-aa83-d576490531fd.jsonl`

---

## Status

**Open** | Created: 2026-08-02 | Priority: P2
