---
id: ENH-2166
type: ENH
priority: P3
status: done
discovered_date: 2026-06-15
discovered_by: capture-issue
captured_at: '2026-06-15T05:55:00Z'
completed_at: '2026-06-16T02:01:49Z'
parent: EPIC-2167
depends_on:
- ENH-2165
- ENH-2164
blocked_by: []
relates_to:
- ENH-2165
- ENH-2164
confidence_score: 98
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/guides/LOOPS_REFERENCE.md` (`### rn-remediate` section) — remove deleted states from Phase 2 and Phase 5 FSM flow diagrams; update state count from 23 → 16; update "Stall vs. too-large outcome tokens" anchor from `route_d_refine.on_no` to the `route:` table `DECOMPOSE:` key
8. Update `docs/guides/LOOPS_GUIDE.md` (`#### classify` section) — revise code example to remove `source: "${captured.diagnosis.output}"` (or annotate it as optional), since post-migration `rn-remediate` no longer uses `source:` on its `classify` states
9. Fix four additional breaking test methods in `test_rn_remediate.py` not in the original plan: DELETE `test_diagnose_captures_output_as_diagnosis` (line 178); UPDATE `test_diagnose_on_error_routes_to_failed` (line 220); UPDATE the tail assertions in `test_mr1_non_llm_evaluators_present` (lines 832–837); REWRITE `test_decompose_token_distinguishes_stall_from_too_large` (line 972) as `test_bug2006_token_disambiguation_preserved`
10. Write 7 new tests in `test_rn_remediate.py`: `test_diagnose_has_classify_evaluator`, `test_diagnose_route_table_covers_all_five_tokens`, `test_check_convergence_has_classify_evaluator`, `test_check_convergence_route_table_covers_all_tokens`, `test_route_d_states_absent`, `test_route_conv_states_absent`, `test_bug2006_token_disambiguation_preserved`

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

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — parent orchestrator; reads `rem_outcome` token emitted by `rn-remediate`; the `route_rem_*`/`route_dec_*` states in the parent rely on the superstring token `STALLED_NEEDS_DECOMPOSE` continuing to be emitted (BUG-2006 coupling)

### Configuration
- N/A — no config files or settings affected

### Similar Patterns
- `scripts/little_loops/loops/harness-optimize.yaml` — existing `route:` table + multi-verdict evaluator
- `scripts/little_loops/loops/rn-implement.yaml` — parent's `route_rem_*`/`route_dec_*` cascades (the same pattern at the orchestrator level; candidate for a later, separate migration)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### YAML key syntax for `route:` table

`RouteConfig.from_dict()` in `scripts/little_loops/fsm/schema.py` maps `_` → `default` and `_error` → `error`. The issue prose says `default:` and `error:` but the actual YAML keys must be `_:` and `_error:`:

```yaml
evaluate:
  type: classify
route:
  IMPLEMENT: gate_implement
  DECIDE:    decide
  WIRE:      wire
  REFINE:    refine
  DECOMPOSE: emit_needs_decompose
  _:         emit_implement_failed  # unmatched token fallback
  _error:    emit_implement_failed  # shell action exits non-zero
```

#### Verified token → target mapping for `diagnose`

Derived from the cascade in `rn-remediate.yaml:265-301`:

| Token | Target | Source |
|-------|--------|--------|
| `IMPLEMENT` | `gate_implement` | `route_d_implement.on_yes` |
| `DECIDE` | `decide` | `route_d_decide.on_yes` |
| `WIRE` | `wire` | `route_d_wire.on_yes` |
| `REFINE` | `refine` | `route_d_refine.on_yes` |
| `DECOMPOSE` | `emit_needs_decompose` | `route_d_refine.on_no` (final fallthrough) |
| `_:` (default) | `emit_implement_failed` | all `on_error` arms |
| `_error:` | `emit_implement_failed` | `diagnose.on_error` |

`classify` is NOT in `_EXIT_CODE_AWARE_EVALUATORS`, so a non-zero exit from the shell action routes to `"error"` verdict before `evaluate_classify()` is called — the `_error:` arm handles this.

#### Verified token → target mapping for `check_convergence`

Derived from the cascade in `rn-remediate.yaml:548-581`:

| Token | Target | Source |
|-------|--------|--------|
| `CONVERGED_PASS` | `gate_implement` | `route_conv_pass.on_yes` |
| `CONVERGED_IMPROVED` | `check_remediation_budget` | `route_conv_improved.on_yes` |
| `NEEDS_MANUAL_REVIEW` | `emit_needs_manual_review` | `route_conv_manual_review.on_yes` |
| `CONVERGED_STALLED` | `check_remediation_budget` | `route_conv_manual_review.on_no` |
| `_:` (default) | `check_remediation_budget` | safe fallback for unrecognized token |
| `_error:` | `gate_implement` | `check_convergence.on_error: route_conv_pass` (fail-open) |

Note: original `route_conv_manual_review.on_error: emit_needs_decompose` was a pattern-match error guard. With `classify` this path disappears — classify never fails on non-matching tokens. The `_error:` arm now only fires on shell action failure.

#### `capture:` fields must be removed from both states

- `diagnose` has `capture: diagnosis` (line 261) — used only by `route_d_*` states being deleted. Remove it.
- `check_convergence` has `capture: convergence_result` (line 544) — used only by `route_conv_*` states being deleted. Remove it.

No other states in `rn-remediate.yaml` reference `captured.diagnosis.output` or `captured.convergence_result.output` outside the deleted cascade states.

#### Dependency status

- **ENH-2165** (`classify` evaluator): **DONE** — `evaluators.py:416` (`evaluate_classify()`), wired at `evaluators.py:1663-1664`. Minimal migration can proceed.
- **ENH-2164** (decision-table engine): **DEFERRED** — not yet implemented. Only needed for Step 5 (Optional) fully-declarative rules. The `blocked_by: ENH-2164` in frontmatter applies only if the optional step is attempted.

#### Test methods to rewrite in `test_rn_remediate.py`

**`TestDiagnoseRouting` class (lines 169-258) — methods to delete/rewrite:**
- `test_diagnose_routes_to_route_d_implement` (line 214) — DELETE; replace with: assert `diagnose.evaluate.type == "classify"` and `route:` table present
- `test_router_chain_covers_all_five_tokens` (line 226) — REWRITE; assert route table has all 5 tokens → correct targets (table above)
- `test_routers_use_output_contains_with_source` (line 243) — DELETE; assert `route_d_*` states no longer exist

**`TestReassessAndConvergence` class — methods to update:**
- `test_check_convergence_captures_as_convergence_result` (line 558) — DELETE; no more `capture: convergence_result`
- `test_convergence_router_chain_is_correct` (line 564) — REWRITE; assert `check_convergence.route` table (table above)
- `test_convergence_routers_use_output_contains_with_source` (line 585) — DELETE; `route_conv_*` states are gone
- `test_above_minimal_entry_points_route_through_gate` (line 444) — UPDATE; check `diagnose.route["IMPLEMENT"] == "gate_implement"` instead of `route_d_implement.on_yes`

### Tests
- `scripts/tests/test_rn_remediate.py` — assert token→state dispatch for every `diagnose`/`check_convergence` token + `default`; assert BUG-2006 disambiguation preserved
- `scripts/tests/test_builtin_loops.py` — `rn-remediate` still passes the universal validation fixture

_Wiring pass added by `/ll:wire-issue`:_

**Additional methods in `test_rn_remediate.py` that will break (beyond the issue's original identified list):**
- `TestDiagnoseRouting.test_diagnose_captures_output_as_diagnosis` (line 178) — DELETE; `capture: diagnosis` is being removed from `diagnose`
- `TestDiagnoseRouting.test_diagnose_on_error_routes_to_failed` (line 220) — UPDATE; `on_error` key replaced by `route._error`; assert `diagnose["route"]["_error"] == "emit_implement_failed"` instead
- `TestFSMHealth.test_mr1_non_llm_evaluators_present` (lines 832–837) — UPDATE the two tail assertions; currently references `route_d_implement` and `route_conv_pass` (deleted states) to assert `evaluate.type == "output_contains"`; rewrite to assert `diagnose["evaluate"]["type"] == "classify"` and `check_convergence["evaluate"]["type"] == "classify"`
- `TestOutcomeTokenChannel.test_decompose_token_distinguishes_stall_from_too_large` (line 972) — REWRITE as `test_bug2006_token_disambiguation_preserved`; currently asserts `route_d_refine.on_no`, `route_conv_improved.on_no`, `route_conv_manual_review.on_no` — all deleted; rewrite using `route:` table assertions (see new tests below)

**New tests to write in `test_rn_remediate.py`:**
- `TestDiagnoseRouting.test_diagnose_has_classify_evaluator` — assert `data["states"]["diagnose"]["evaluate"]["type"] == "classify"` and `data["states"]["diagnose"].get("capture") is None`
- `TestDiagnoseRouting.test_diagnose_route_table_covers_all_five_tokens` — assert `route:` table keys: `IMPLEMENT`→`gate_implement`, `DECIDE`→`decide`, `WIRE`→`wire`, `REFINE`→`refine`, `DECOMPOSE`→`emit_needs_decompose`, `_`→`emit_implement_failed`, `_error`→`emit_implement_failed`; follow pattern in `test_fsm_executor.py:1469`
- `TestReassessAndConvergence.test_check_convergence_has_classify_evaluator` — assert `data["states"]["check_convergence"]["evaluate"]["type"] == "classify"` and `data["states"]["check_convergence"].get("capture") is None`
- `TestReassessAndConvergence.test_check_convergence_route_table_covers_all_tokens` — assert `route:` table keys: `CONVERGED_PASS`→`gate_implement`, `CONVERGED_IMPROVED`→`check_remediation_budget`, `NEEDS_MANUAL_REVIEW`→`emit_needs_manual_review`, `CONVERGED_STALLED`→`check_remediation_budget`, `_`→`check_remediation_budget`, `_error`→`gate_implement`
- `test_route_d_states_absent` — assert `route_d_implement`, `route_d_decide`, `route_d_wire`, `route_d_refine` are NOT in `data["states"]`
- `test_route_conv_states_absent` — assert `route_conv_pass`, `route_conv_improved`, `route_conv_manual_review` are NOT in `data["states"]`
- `test_bug2006_token_disambiguation_preserved` (replaces the rewritten test above) — assert `diagnose` route: table sends `DECOMPOSE`→`emit_needs_decompose`; assert `check_convergence` route: table sends `CONVERGED_STALLED`→`check_remediation_budget`; assert both `emit_needs_decompose` and `emit_stalled_needs_decompose` states still exist, preserving the distinct token vocabulary the parent `rn-implement` relies on

### Reference Test Patterns (for new dispatch tests)
- `scripts/tests/test_fsm_executor.py:1469` — `test_classify_route_dispatches_to_correct_state()` — canonical pattern for asserting classify + route: table dispatch
- `scripts/tests/test_fsm_executor.py:1500` — `test_classify_route_default_catches_unknown_token()` — verifies `_:` fallback
- `scripts/tests/test_fsm_executor.py:1524` — `test_classify_nonzero_exit_routes_error()` — verifies `_error:` arm
- `scripts/tests/test_harness_optimize.py:134` — `test_gate_routes_correctly()` — test pattern for asserting route: table keys in a loop YAML

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — once migrated, `rn-remediate` becomes the reference example for the decision-router pattern in a real loop

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — `### rn-remediate` section has four stale references to update: (1) Phase 2 FSM flow diagram explicitly names `route_d_implement → route_d_decide → route_d_wire → route_d_refine`; (2) Phase 5 FSM flow diagram explicitly names `route_conv_pass → route_conv_improved → route_conv_manual_review`; (3) "23 states across 5 phases" state count decreases by 7 to 16; (4) "Stall vs. too-large outcome tokens" paragraph anchors the `DECOMPOSE` path to `route_d_refine.on_no` — update to reference the `route:` table `DECOMPOSE:` key directly
- `docs/guides/LOOPS_GUIDE.md` (classify section) — the `#### classify` code example uses `source: "${captured.diagnosis.output}"` modeled on the pre-migration `rn-remediate` pattern; post-migration the canonical form no longer needs `source:` since `classify` reads action stdout directly — update the example to match the new form, or add a note that `source:` is optional

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
- `/ll:ready-issue` - 2026-06-16T01:46:02 - `79f9085a-898d-4a55-80d5-0599290e4fa6.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `27c6eb5f-65f7-4450-8321-e20099eaea0c.jsonl`
- `/ll:wire-issue` - 2026-06-16T01:39:07 - `a7a2c13d-80a1-4674-af7a-b59a585951f8.jsonl`
- `/ll:refine-issue` - 2026-06-16T01:02:00 - `e9cc82c4-5d2e-4176-91b8-ad6205bbef80.jsonl`
- `/ll:format-issue` - 2026-06-16T00:52:49 - `4701f487-3561-4050-bd66-8340313d8517.jsonl`
- `/ll:capture-issue` - 2026-06-15T05:55:00Z - manual
