---
id: ENH-2166
type: ENH
priority: P3
status: open
discovered_date: 2026-06-15
discovered_by: capture-issue
captured_at: '2026-06-15T05:55:00Z'
parent: EPIC-2167
depends_on:
- ENH-2165
- ENH-2164
blocked_by:
- ENH-2165
- ENH-2164
relates_to:
- ENH-2165
- ENH-2164
---

# ENH-2166: Migrate rn-remediate Routing Cascades to `classify` + decision-router

## Summary

Replace `rn-remediate.yaml`'s two hand-rolled `output_contains` routing cascades —
`diagnose → route_d_implement → route_d_decide → route_d_wire → route_d_refine` and
`check_convergence → route_conv_pass → route_conv_improved → route_conv_manual_review`
— with single `classify` states (ENH-2165) driven by a declarative decision table
(ENH-2164). This is the real-world adopter that validates the L0+L1 stack against a
shipping, battle-tested router and retires ~7 routing states of boilerplate.

## Current Behavior

`rn-remediate.yaml` implements multi-axis routing as priority-ordered shell
`if/elif` blocks whose emitted token is then dispatched by a **chain of
single-pattern `output_contains` states**, each `on_no` falling through to the next:

- `diagnose` (rn-remediate.yaml:205) emits one of
  `IMPLEMENT | DECIDE | WIRE | REFINE | DECOMPOSE`, then `route_d_implement` →
  `route_d_decide` → `route_d_wire` → `route_d_refine` fan it out (4 states).
- `check_convergence` (rn-remediate.yaml:458) emits one of
  `CONVERGED_PASS | CONVERGED_IMPROVED | NEEDS_MANUAL_REVIEW | CONVERGED_STALLED`,
  then `route_conv_pass` → `route_conv_improved` → `route_conv_manual_review` fan it
  out (3 states).

This is verbose, order-fragile (substring collisions — `STALLED_NEEDS_DECOMPOSE`
deliberately superstrings `NEEDS_DECOMPOSE`, and the cascade order encodes the
disambiguation), and the routing layer is untestable as a unit.

## Motivation

The decision-list pattern these cascades implement is exactly what ENH-2165
(`classify` evaluator) + ENH-2164 (decision-table engine) abstract. `rn-remediate`
is the **existing, shipping instance** that motivated the abstraction, so migrating
it:
- validates the L0/L1 primitives against a real router (not the hypothetical
  examples in ENH-2164),
- removes ~7 routing states and the substring-collision fragility,
- makes the routing rules a declarative, diffable, unit-testable table instead of
  buried shell `if/elif`,
- proves the **conjunctive** (`confidence>=85 & outcome>=75`) and
  **deterministic-score-source** (`ll-issues show --json`, not LLM `AGGREGATE`)
  requirements that ENH-2164 took on for v1.

## Expected Behavior

`diagnose` collapses to a single classifier + `route:` table:

```yaml
diagnose:
  action_type: shell
  action: |
    # ... existing score fetch + priority-ordered rules, printing one token ...
    echo "WIRE"
  evaluate:
    type: classify
  route:
    IMPLEMENT: gate_implement
    DECIDE:    decide
    WIRE:      wire
    REFINE:    refine
    DECOMPOSE: emit_needs_decompose
    default:   emit_implement_failed
```

`check_convergence` collapses the same way (`CONVERGED_PASS → gate_implement`,
`CONVERGED_IMPROVED → check_remediation_budget`, `NEEDS_MANUAL_REVIEW →
emit_needs_manual_review`, `CONVERGED_STALLED → check_remediation_budget`,
`default → emit_implement_failed`). The `route_d_*` and `route_conv_*` states are
deleted.

Optionally, the priority-ordered `if/elif` rule bodies are themselves expressed as
an ENH-2164 decision table (`policy_rules` / `router_rules`) so the routing logic is
fully declarative; the score-fetch shell remains as the source that writes the
per-dimension files the engine reads. Decide during refinement whether to go
fully-declarative or keep the shell scorer + `classify` (the minimal, lower-risk
step).

## Acceptance Criteria

- [ ] `diagnose`'s `route_d_implement`/`route_d_decide`/`route_d_wire`/`route_d_refine`
      states are removed; `diagnose` routes via `classify` + a `route:` table with a
      `default:` arm.
- [ ] `check_convergence`'s `route_conv_pass`/`route_conv_improved`/`route_conv_manual_review`
      states are removed; `check_convergence` routes via `classify` + a `route:` table
      with a `default:` arm.
- [ ] The `STALLED_NEEDS_DECOMPOSE` vs `NEEDS_DECOMPOSE` disambiguation (BUG-2006) is
      preserved — verify the `classify` token vocabulary keeps them distinct (exact
      tokens, no substring reliance) and the parent `rn-implement`'s
      `route_dec_stalled_origin` still works against the retained `rem_outcome`.
- [ ] All existing `rn-remediate` routing behavior is preserved: every prior
      cascade target is reachable for the same token, and the `on_error` paths
      (previously `emit_implement_failed`) map to the `route:` `error:`/`default:` arm.
- [ ] `ll-loop validate rn-remediate` passes (no MR-4 dead-end warnings — `default:`
      coverage closes the partial-route gap the cascades' `on_no` fall-through used to).
- [ ] `scripts/tests/test_builtin_loops.py` and any `rn-remediate`-specific routing
      tests pass; add/adjust tests asserting token→state dispatch for every token
      including the `default` case.
- [ ] `ll-loop diagnose-evaluators rn-remediate` shows the migrated `classify` states
      are not toothless (verdict varies across the token set).

## Implementation Steps

1. **Land dependencies first** — ENH-2165 (`classify`) and ENH-2164 (decision-table
   engine) must be merged. This issue is `blocked_by` both.
2. **Migrate `diagnose`** — keep the score-fetch shell as-is (it already prints a
   single token on the final line); replace its `next: route_d_implement` +
   `capture: diagnosis` with `evaluate: {type: classify}` and a `route:` table;
   delete the four `route_d_*` states.
3. **Migrate `check_convergence`** — same transform; delete the three `route_conv_*`
   states. Confirm the `on_error: route_conv_pass` fallback becomes a `route:`
   `error:` arm with equivalent behavior.
4. **Preserve token distinctness** — audit for any place that relied on substring
   matching (`route_rem_decompose` in the parent matches `NEEDS_DECOMPOSE` as a
   substring of `STALLED_NEEDS_DECOMPOSE`); the parent `rn-implement` is unchanged,
   but verify the child still emits the superstring token so the parent's substring
   logic continues to hold. Document the cross-loop coupling.
5. **(Optional) Fully-declarative rules** — lift the `if/elif` rule bodies into an
   ENH-2164 `router_rules` table. Gate this on whether the conjunctive grammar
   cleanly expresses all `diagnose`/`check_convergence` rules; otherwise keep the
   shell scorer and only migrate the routing.
6. **Test + validate** — `ll-loop validate`, `ll-loop diagnose-evaluators`, and the
   pytest suite; add token→state dispatch tests.

## Scope Boundaries

- **In scope**: migrating `rn-remediate`'s `diagnose` and `check_convergence`
  routing cascades to `classify` + `route:`; preserving all current routing
  semantics and cross-loop token coupling; tests for the migrated dispatch.
- **Out of scope**: building `classify` (ENH-2165) or the decision-table engine
  (ENH-2164); changing `rn-implement`'s parent-side `route_rem_*`/`route_dec_*`
  cascades (a separate follow-on if desired); altering the routing *logic* /
  thresholds (this is a mechanical refactor, not a behavior change); migrating
  `rn-decompose` (its single branch is not a cascade).

## Impact

- **Priority**: P3 — validates the new primitives and removes boilerplate; no
  user-facing behavior change.
- **Effort**: Small–Medium — mechanical once ENH-2165/ENH-2164 land; the care is in
  preserving the BUG-2006 token disambiguation and the parent coupling.
- **Risk**: Medium — `rn-remediate` is a load-bearing autonomous loop; a routing
  regression silently mis-routes issues. Mitigated by the "preserve all targets"
  AC, `diagnose-evaluators`, and dispatch tests.
- **Breaking Change**: No — internal routing refactor; outcome tokens and parent
  contract unchanged.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` (collapse `route_d_*` and `route_conv_*`)
- `scripts/tests/test_builtin_loops.py` / `scripts/tests/test_rn_remediate.py` (dispatch tests)

### Dependencies
- ENH-2165 (`classify` evaluator) — `blocked_by`
- ENH-2164 (`lib/policy-router` decision-table engine) — `blocked_by`

### Similar Patterns
- `scripts/little_loops/loops/harness-optimize.yaml` — existing `route:` table + multi-verdict evaluator
- `scripts/little_loops/loops/rn-implement.yaml` — parent's `route_rem_*`/`route_dec_*` cascades (the same pattern at the orchestrator level; candidate for a later, separate migration)

### Tests
- `scripts/tests/test_rn_remediate.py` — assert token→state dispatch for every `diagnose`/`check_convergence` token + `default`; assert BUG-2006 disambiguation preserved
- `scripts/tests/test_builtin_loops.py` — `rn-remediate` still passes the universal validation fixture

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — once migrated, `rn-remediate` becomes the reference example for the decision-router pattern in a real loop

## Related Key Documentation

- [`scripts/little_loops/loops/rn-remediate.yaml`](../../scripts/little_loops/loops/rn-remediate.yaml) — the loop being migrated
- ENH-2165 — `classify` evaluator (dependency)
- ENH-2164 — decision-table engine (dependency)
- BUG-2006 — the `STALLED_NEEDS_DECOMPOSE` vs `NEEDS_DECOMPOSE` disambiguation that must be preserved

## Labels

`enh`, `loops`, `fsm`, `refactor`, `rn-remediate`

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-15T05:55:00Z - manual
