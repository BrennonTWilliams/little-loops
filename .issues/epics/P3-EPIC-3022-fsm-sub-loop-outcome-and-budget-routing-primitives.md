---
id: EPIC-3022
title: FSM sub-loop outcome and budget routing primitives
type: EPIC
priority: P3
status: done
verify_verdict: VALID
discovered_by: capture-issue
discovered_date: 2026-08-02
testable: true
labels:
- epic
- fsm
- loops
---

# EPIC-3022: FSM sub-loop outcome and budget routing primitives

## Summary

Two gaps surfaced by the same `/ll:debug-loop-run` analysis of a `deep-research`
run (`deep-research-loop-analysis-2026-08-03.md`, Findings 2 and 5): a parent
FSM state that invokes a `loop:` sub-state has no way to route differently when
the sub-loop times out versus genuinely fails (**ENH-3019**), and no FSM loop
has a per-state/iteration token or wall-clock budget hook analogous to
`host_guard.py`'s memory-pressure `on_budget_exceeded` (**ENH-3020**). Both are
additive, backward-compatible routing primitives at different granularities of
the same underlying problem: a loop author cannot react to "we're running out
of budget" before the blunt global `timeout:` forces a hard stop, discarding
recoverable partial work.

## Motivation

Today the only backstop against runaway sub-loop or per-state cost is the
loop-global `timeout:`, which fires blind to which state or sub-loop consumed
the budget and routes to whatever `on_no`/`on_error` terminal the parent
happens to be in — not a state the author chose based on *why* the loop ran
out of time. Both children fix a different layer of this: ENH-3019 at the
whole-sub-loop-termination-reason granularity, ENH-3020 at the
per-state/iteration token-and-duration granularity. Neither blocks the other;
together they let a loop degrade gracefully (route to salvage/synthesis)
instead of losing partial work behind a hard failure terminal.

## Children

- **ENH-3019** (P2) — **done** (2026-08-04). `on_timeout` route +
  `terminated_by` context exposure for `loop:` sub-states, distinguishing
  timeout/max_iterations/signal from a genuine `on_no`. Also clamps a child
  sub-loop's timeout to the parent's remaining wall-clock budget
  (`fsm/executor.py:1089-1099`) so an `on_timeout` salvage state has headroom
  to run.
- **ENH-3020** (P3) — **cancelled** (2026-08-29). Both halves of the ask
  already existed: the wall-clock half is `StateConfig.timeout`/`idle_timeout`
  plus ENH-3019's routing, and the token half is `StateConfig.cost_ceiling`
  (ENH-2477) — which turned out to be schema-validated but never enforced at
  runtime. That defect is re-filed as **BUG-3360**; see ENH-3020's
  Cancellation Rationale for the full evidence.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop` (renamed from
  `_execute_loop_state`, now at `fsm/executor.py:831`) (ENH-3019);
  new per-state/iteration accounting check (ENH-3020)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `on_timeout` route
  (ENH-3019); `max_tokens_per_iteration`/`max_seconds_per_state` config keys
  (ENH-3020)
- `scripts/little_loops/fsm/types.py` — `ExecutionResult.terminated_by`
  consumption (ENH-3019, already exists, needs exposure to `context`)
- `scripts/little_loops/fsm/host_guard.py` — reference shape for the
  `on_budget_exceeded`-style routing hook (ENH-3020)

### Tests
- `scripts/tests/` — new fixture loop YAMLs + unit coverage per child for the
  new routing branch and context write.

## Goal

A loop author composing sub-loops or long-running states under a global
`timeout:` has in-run signals to route to a salvage/synthesis path before the
timeout forces a hard stop mid-state, without changing behavior for any
existing loop that doesn't opt in.

## Scope

In scope: the two children above — schema additions, executor routing
branches, and the context/counter plumbing each needs. Out of scope: changing
`host_guard.py`'s existing memory-budget mechanism, changing the loop-global
`timeout:` semantics, and any UI/reporting change to `/ll:debug-loop-run`
(consumes the resulting context values but isn't itself in scope).

## Impact

- **Priority**: P3 — improves graceful degradation and debuggability; the
  global `timeout:` is a working, if blunt, backstop today, so neither child
  is blocking.
- **Effort**: Medium — two children, each Medium (schema addition + one new
  executor branch + one new context/counter write + test coverage).
- **Risk**: Low — both children are additive/optional; loops that don't
  declare the new config/routes behave exactly as today.

## Status

**Done** | Created: 2026-08-03 | Closed: 2026-08-29 | Priority: P3

Closed with ENH-3019 done and ENH-3020 cancelled. The remaining work the epic
would have covered is a defect, not a primitive, and is tracked on BUG-3360.

## Success Criteria

- [x] `on_timeout` is a valid per-state route in the FSM schema, falls back to
      `on_no` when unset, and `terminated_by` is exposed on parent `context`
      after a `loop:` state resolves (ENH-3019)
- [x] An optional per-state/iteration token/wall-clock budget can be
      configured and routed on, with no behavior change for loops that don't
      configure it — **withdrawn**: the wall-clock half already existed as
      `StateConfig.timeout`/`idle_timeout` + ENH-3019's routing, and the cost
      half already existed as declarative schema (`StateConfig.cost_ceiling`,
      ENH-2477). Its missing enforcement is BUG-3360.
- [x] `python -m pytest scripts/tests/` covers the ENH-3019 routing paths

## Related Key Documentation

- `.claude/CLAUDE.md` § Loop Authoring — the FSM design-rule table (`ll-loop
  validate` MR-1..MR-14) both children's schema additions must stay
  compatible with.
- `scripts/little_loops/fsm/host_guard.py` — the reference shape ENH-3020's
  routing hook follows.

## Verification Notes

2026-08-10 (`/ll:verify-issues`): Verified 2026-08-10: body previously listed ENH-3019 as an open child — it is actually status: done. Only ENH-3020 remains open. Epic correctly stays open; update any body prose that still lists ENH-3019 as pending.

- 2026-08-16: ENH-3019 done, ENH-3020 open (statuses correct), but the Integration Map's citation `executor.py — _execute_loop_state` was stale — that function was renamed to `_execute_sub_loop` (now at `fsm/executor.py:831`); corrected above. Verdict: NEEDS_UPDATE.

## Session Log
- `/ll:verify-issues` - 2026-08-16T16:40:25 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:07:48 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:52:53 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:52 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This epic's ENH-3020 adds a per-state/iteration token/wall-clock budget config and routing hook (analogous to `host_guard.py`'s `on_budget_exceeded`) directly in `fsm/executor.py` and `fsm-loop-schema.json`. EPIC-3041's FEAT-3039 (advisor FSM stall escalation with routable verdicts) and FEAT-3038 (per-task budget, `max_consults_per_task`) independently add a second, differently-shaped budget/stall-triggered routing primitive to the same FSM layer. Before implementing, confirm whether FEAT-3039's stall-escalation route reuses ENH-3020's budget-hook mechanism/route naming convention or is a genuinely separate FSM extension point, so `fsm-loop-schema.json` doesn't end up with two divergent "route on running out of X" schemas.
