---
id: ENH-2692
title: rn-refine final_score rubric verdict has no effect on control flow
type: ENH
priority: P3
status: done
captured_at: '2026-07-19T00:00:00Z'
completed_at: '2026-07-19T19:15:50Z'
discovered_date: 2026-07-19
discovered_by: audit-loop-run
labels:
- loops
- rn-refine
- degenerate-gate
decision_needed: false
confidence_score: 100
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2692: rn-refine final_score rubric verdict has no effect on control flow

## Summary

`final_score` in `loops/rn-refine.yaml` scores the reassembled root plan
against the 9-dimension rubric and emits `ALL_VERY_HIGH` or `ITERATE`, but
both `on_yes` and `on_no` route to the same next state (`preflight_check`).
The loop's own description says the reassembled plan is "refined to rubric
convergence," but nothing downstream of `final_score` actually depends on
whether convergence was reached — an `ITERATE` verdict proceeds through
`preflight_check`/`finalize` exactly like `ALL_VERY_HIGH` would.

## Evidence

Run `2026-07-19T161520-rn-refine`
(`.loops/.history/2026-07-19T161520-rn-refine/`): `final_score` returned
`ITERATE` at iteration 53, and the loop proceeded to `preflight_check`
at iteration 54 regardless (which then separately aborted for an unrelated
reason — see ENH-2690). Had `preflight_check`'s invariant passed, the run
would have written back a plan that never reached rubric convergence, with no
record that the finalize path bypassed the loop's own quality bar.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-refine.yaml` — `final_score` state
  (lines 540-550) if Option A; top-level `description` (line 9, echoed
  lines 20-23) if Option B.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/lib/common.yaml:233-262` — `plan_rubric_score`
  fragment shared by `final_score` here, `rn-plan.yaml`'s `score` state, and
  `oracles/plan-node-refine.yaml`'s `score_node` state; unaffected by either
  option since only the caller's routing/description changes.

### Similar Patterns
- `scripts/little_loops/loops/oracles/plan-node-refine.yaml:171-194`
  (`score_node` / `check_node_budget`) — the bounded loop-back shape to
  model Option A after, though it operates per-node, not at the
  reassembled-root level (see Codebase Research Findings below).
- `scripts/little_loops/loops/rn-plan.yaml:178-182` (`score` state) —
  same `plan_rubric_score` fragment with genuinely differentiated
  `on_yes: done` / `on_no: research_iteration` routing.
- `scripts/little_loops/loops/interactive-component-generator.yaml:507-509`
  (`vision_gate`) — model for Option B's "ADVISORY" description wording.

### Tests
- `scripts/tests/test_rn_refine.py` — existing rn-refine structural/safety
  test suite; would need a new case asserting `final_score`'s routing
  (either differentiated on_yes/on_no for Option A, or unchanged for
  Option B).
- `scripts/tests/test_fsm_validation.py::TestPartialRouteDeadEnd`
  (lines 1460-1621) — MR-4 test suite; not directly affected since MR-4
  doesn't fire on this state's current shape either way.

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — contains an rn-refine state-flow
  description that may need a matching wording update if Option B's
  `description` change is made.

## Proposed Solution

Either:

**Option A**: Give `final_score` a real `on_no` path (e.g. one more `refine_iteration`-style
   pass on the reassembled root, bounded by a max-root-iterations cap), or

> **Selected:** Option B — matches the existing house ADVISORY convention and
> the state's own (already-accurate) inline comment, with no functional
> dependents to reconcile.

**Option B**: If root-level rubric convergence is intentionally advisory (per-node
   convergence during the walk is the real gate), update the loop
   `description` to say so explicitly, so the rubric score in the final
   report isn't read as a pass/fail signal it doesn't function as.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`final_score`'s exact wiring**: `loops/rn-refine.yaml:538-546` uses
  `fragment: plan_rubric_score` (defined in `loops/lib/common.yaml:233-262`),
  whose own docstring (`common.yaml:241`) states the calling state "must
  supply: on_yes (convergence route), on_no (iterate route), on_error." —
  `rn-refine.yaml` maps `on_yes`, `on_no`, and `on_error` all to
  `preflight_check`, so the fragment's own contract is unmet here. The
  in-file comment directly above the state (lines 539-542) already states
  the design intent: "it does not loop — the recursive per-node refinement
  is where convergence happens."
- **`preflight_check` has no rubric awareness**: `loops/rn-refine.yaml:548-622`
  is a purely structural diff-size/heading-preservation invariant guard
  (ENH-2418) — it checks non-empty output, byte-length floor vs. source, and
  heading preservation, then routes `on_yes: finalize` / `on_no:
  finalize_aborted` (lines 620-622). It runs identically regardless of
  whether `final_score` returned `ALL_VERY_HIGH` or `ITERATE`, confirming
  the rubric verdict has zero downstream effect today.
- **Option A feasibility gap**: there is no existing "re-refine the
  reassembled root `plan.md`" state to loop back to. The one bounded
  loop-back pattern in this loop family —
  `oracles/plan-node-refine.yaml`'s `score_node` (lines 171-178) /
  `check_node_budget` (lines 180-194), which checks a `.node_iter` counter
  file against `context.max_node_iters` (default `2`, set at
  `rn-refine.yaml:43`) via `output_numeric lt` before routing back to
  `refine_iteration` — operates **per-node during the tree walk**, before
  assembly. Implementing Option A means either introducing a new
  root-level refine state (non-trivial: it would need to re-walk/re-refine
  after reassembly, not just re-run one prompt) or re-triggering the
  per-node walk for underperforming dimensions, which is a larger change
  than "one more pass."
- **Option B wording precedent**: `loops/interactive-component-generator.yaml`'s
  `vision_gate` state (lines 507-509) is the closest existing model for
  Option B's phrasing — it explicitly labels itself "ADVISORY" and states
  in-line exactly which key to flip (`on_no`) and which existing counter
  (`.compose_rounds`) would bound it if made binding later. `rn-refine.yaml`'s
  current comment (line 540) states the same intent but without that
  "ADVISORY" vocabulary; adopting matching wording would align with
  house style. The claim needing correction lives at
  `loops/rn-refine.yaml:9` ("The root plan is refined to rubric
  convergence...") and is echoed at lines 20-21.
- **Related lint gap**: MR-4's validator
  (`scripts/little_loops/fsm/validation.py:_validate_partial_route_dead_end`,
  lines 1603-1644) only fires when `on_no`/`on_partial` is missing
  entirely — it does not currently detect an `on_no` that is present but
  routes to the same target as `on_yes` (this state's actual shape), so
  `ll-loop validate` would not have caught this pattern. Out of scope for
  this issue, but worth a follow-up if Option B is chosen (since the
  "verdict has no effect" family — see ENH-2691's `synth_dispatch` — would
  keep evading MR-4 as-is).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-19.

**Selected**: Option B — update the loop `description` to state the root-level
rubric verdict is advisory.

**Reasoning**: Option B has a direct, exact wording template already in-repo
(`interactive-component-generator.yaml`'s `vision_gate` ADVISORY comment, plus
a two-site precedent in `auto-refine-and-implement.yaml`'s `verify_verdict`/
`EPIC_MERGE_VERDICT` advisory language), and `final_score`'s own inline
comment already states the intended behavior — so the fix is templatable
prose, not new design. Option A, by contrast, has zero codebase precedent for
looping back on a *fully reassembled tree root* (the reusable refinement
prompt, `oracles/plan-research-iteration`, only operates on individual
node/run dirs), would overturn a documented intentional design decision, and
leaves the `on_error`-branch bounding question unresolved.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| Option B | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: no existing loop implements a decompose→reassemble→root-rescore
  loop-back; the counter-file/`output_numeric lt` idiom
  (`oracles/plan-node-refine.yaml:180-194`, `svg-textgrad.yaml:109-127`) is
  reusable in spirit but node-scoped, not root-scoped, and the currently
  passing test `test_final_score_routes_to_preflight_check` would need to be
  rewritten, not extended (reuse score 1/3).
- Option B: matches a proven house-wide "ADVISORY" convention used at 3 other
  sites, the target state's own comment already says what the description
  needs to say, and no test or doc currently relies on the misleading claim
  being true (reuse score 2/3).

## Acceptance Criteria

- [x] Either `final_score`'s verdict visibly affects whether the plan is
      written back, or the loop's `description` is corrected to state the
      rubric is reporting-only at the root level.

## Impact

- **Priority**: P3 — did not change this run's outcome (a separate invariant
  aborted first), but the rubric threshold in the loop's stated contract is
  currently non-binding at the point that matters most (final write-back).
- **Effort**: Small — either a `description` wording fix, or adding a bounded
  loop-back state in `loops/rn-refine.yaml`.

## Related Files

- `loops/rn-refine.yaml` (`final_score`)

## Status

**Open** | Created: 2026-07-19 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-07-19T19:15:25 - `1f601417-ec93-4019-aa8b-641779a23a76.jsonl`
- `/ll:ready-issue` - 2026-07-19T19:11:25 - `cefb69cc-072c-4b5c-9515-35a57f6eec8e.jsonl`
- `/ll:confidence-check` - 2026-07-19T19:10:00 - `710a5284-0f20-4164-8f7b-c1ab5cc119b2.jsonl`
- `/ll:decide-issue` - 2026-07-19T19:06:12 - `ba13332f-53e1-4d55-bfb7-0c510d3bbc89.jsonl`
- `/ll:refine-issue` - 2026-07-19T19:01:57 - `5ac5ce51-3790-4ef4-a5d4-e797493d98a2.jsonl`
