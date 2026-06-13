---
id: ENH-2107
title: 'rn-remediate: CONVERGED_STALLED should retry diagnose with a different action
  before escalating'
type: ENH
priority: P2
status: done
captured_at: '2026-06-12T21:57:47Z'
completed_at: '2026-06-13T00:25:08Z'
discovered_date: '2026-06-12'
discovered_by: capture-issue
parent: EPIC-1811
labels:
- enhancement
- loop
- fsm
- rn-remediate
decision_needed: false
confidence_score: 93
outcome_confidence: 88
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2107: rn-remediate: CONVERGED_STALLED should retry diagnose with a different action before escalating

## Summary

When `rn-remediate`'s `check_convergence` returns `CONVERGED_STALLED` (zero delta — scores unchanged after the first remediation action), the loop immediately emits `STALLED_NEEDS_DECOMPOSE` and terminates. It never tries a second action. Since `CONVERGED_IMPROVED` loops back to `diagnose` but `CONVERGED_STALLED` does not, a zero-delta result from WIRE (the most common first action for high-ambiguity issues) silently forecloses REFINE — even though REFINE might succeed where WIRE couldn't.

## Current Behavior

`diagnose` (`rn-remediate.yaml:191-205`) uses priority-ordered routing:

```
1. confidence ≥ threshold AND outcome ≥ threshold → IMPLEMENT
2. decision_needed                                → DECIDE
3. missing_artifacts                              → WIRE
4. ambiguity ≥ 15                                → WIRE   ← fires first for high-ambiguity issues
5. complexity ≥ 15 OR confidence < 50            → REFINE ← never reached if rule 4 fires
6. change_surface ≥ 15                           → DECOMPOSE
```

After WIRE runs, `re_assess` re-scores the issue. If wiring added content but didn't raise outcome confidence above the threshold, scores are unchanged (delta=0). `check_convergence` emits `CONVERGED_STALLED`. All three routing states (`route_conv_pass`, `route_conv_improved`, `route_conv_manual_review`) return no-match, and the loop terminates with `STALLED_NEEDS_DECOMPOSE`. REFINE is never attempted.

**Observed in `rn-implement-20260612T152910.log`** — BUG-2094:
- First pass: ambiguity=18 → WIRE → `/ll:wire-issue` ran → outcome stayed at 72 (threshold: 75)
- `CONVERGED_STALLED` → `STALLED_NEEDS_DECOMPOSE` → decomposition declined → deferred
- REFINE was never tried despite complexity=14 and an outcome gap of only 3 points

## Expected Behavior

When `CONVERGED_STALLED` fires and fewer than `max_remediation_passes` attempts have been made, the loop should re-enter `diagnose` with a record of actions already tried. `diagnose` skips previously-tried actions and routes to the next best option (e.g., REFINE after WIRE). Only after all viable actions are exhausted — or `max_remediation_passes` is reached — does the loop emit `STALLED_NEEDS_DECOMPOSE`.

## Scope Boundaries

- **In scope**: Convergence routing logic in `rn-remediate.yaml`; `CONVERGED_STALLED` retry path; per-issue pass counter tracking under `$RUN_DIR`; tried-action skip logic in `diagnose`
- **Out of scope**: Changes to other `rn-*` loops; modifying `diagnose` scoring thresholds or ambiguity/complexity cutoff values; altering `CONVERGED_IMPROVED` routing behavior; decompose/defer terminal behavior after passes exhausted

## Motivation

The current design loses 1-2 remediation passes to a false stall. WIRE adds wiring information; REFINE rewrites the spec with new content. They address different deficiencies and are naturally complementary. Issues where ambiguity (18) and complexity (14) are both near-threshold but straddle the routing boundary get WIRE-only treatment because ambiguity fires first — even when a subsequent REFINE pass would push outcome confidence above threshold.

The `max_remediation_passes` context variable (default: 3) is designed to bound multi-pass remediation, but it's only honored by the `CONVERGED_STALLED` budget check, not by the STALLED-zero-delta path. The budget check path never fires because STALLED terminates before it can exhaust passes.

## Proposed Solution

Two complementary changes in `rn-remediate.yaml`:

### 1. Propagate "tried actions" through convergence routing

Add a `tried_actions` file (e.g., `$RUN_DIR/tried_actions_${ISSUE_ID}.txt`) that records each action taken by `diagnose`. When `CONVERGED_STALLED` fires:
- Read `tried_actions` count
- If count < `max_remediation_passes`: loop back to `diagnose` (same as `CONVERGED_IMPROVED`)
- If count >= `max_remediation_passes`: emit `STALLED_NEEDS_DECOMPOSE` (current behavior)

### 2. `diagnose` skips already-tried actions

Pass tried actions into `diagnose` (via the file or a context variable). In the routing block, skip actions already in the tried set:

```bash
# Before choosing WIRE, check if already tried:
if [ "$AMBIGUITY" -ge "$AMBIGUITY_THRESHOLD" ] && ! grep -qx "WIRE" "$TRIED_FILE" 2>/dev/null; then
  echo "WIRE"
elif [ "$COMPLEXITY" -ge "$COMPLEXITY_THRESHOLD" ] && ! grep -qx "REFINE" "$TRIED_FILE" 2>/dev/null; then
  echo "REFINE"
...
```

If all actions have been tried, `diagnose` emits a new `EXHAUSTED` token that routes directly to `STALLED_NEEDS_DECOMPOSE`.

### Minimal alternative (lower complexity)

> **Selected:** Minimal Fix (one-line routing change) — reuses existing `check_remediation_budget` infrastructure with zero new states or tokens

If the tried-actions mechanism is too invasive: change the `CONVERGED_STALLED` routing to simply loop back to `diagnose` up to `max_remediation_passes` (same logic as `CONVERGED_IMPROVED`). Without skip logic, `diagnose` will route to the same action again — but on a re-run it has updated scores (post-wire), so the routing might change naturally as ambiguity flags clear.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**The minimal fix is a single routing-line change.** Research confirms that `check_convergence` (lines 381–385) already increments `remediation_count_<ID>.txt` on *every* convergence evaluation — including `CONVERGED_STALLED` passes. `check_remediation_budget` (lines 448–466) already reads this counter and gates loop-back to `diagnose` via `output_numeric lt max_remediation_passes`. The only missing wiring is that `route_conv_manual_review.on_no` (line 445) routes directly to `emit_stalled_needs_decompose` instead of going through `check_remediation_budget`.

Minimal fix — one line change in `rn-remediate.yaml`:
```yaml
# Before (line 445):
on_no: emit_stalled_needs_decompose

# After:
on_no: check_remediation_budget
```

This gives `CONVERGED_STALLED` the identical budget-gated retry behavior as `CONVERGED_IMPROVED` with zero new states and no new token required. The `CONVERGED_STALLED_RETRY` token described in the full solution is unnecessary for the minimal path.

**Tried-action skip pattern (full solution reference):** The codebase convention is an append-only file per run + `grep -qxF` membership check (same pattern as `sprint-refine-and-implement.yaml` lines 36–40 and `recursive-refine.yaml` init at lines 57–63). For rn-remediate, write action tokens (`WIRE`, `REFINE`, `DECIDE`) to `${RUN_DIR}/tried_actions_${ID}.txt` immediately after dispatching, then add `grep -qxF "WIRE" "$TRIED_FILE" 2>/dev/null` guards in `diagnose` before each routing token. Use `$${RUN_DIR}` double-brace escape for shell variable references inside FSM YAML actions.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-12.

**Selected**: Minimal Fix — `route_conv_manual_review.on_no: check_remediation_budget`

**Reasoning**: `check_remediation_budget` (lines 448–466) already reads `remediation_count_${ID}.txt`, gates loop-back to `diagnose` via `output_numeric lt max_remediation_passes`, and handles terminal escalation — making this a zero-new-state fix. `CONVERGED_IMPROVED` already routes `on_yes: check_remediation_budget` as the direct parallel, and `check_convergence` (lines 381–385) already increments the counter unconditionally on every pass including STALLED, so all required infrastructure is in place. The full solution's tried-action skip logic adds value but introduces new shell idioms into `diagnose` with no existing precedent in this file.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Full Solution (tried-actions file + skip guards) | 2/3 | 1/3 | 1/3 | 2/3 | 6/12 |
| Minimal Fix (one-line routing change) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Full Solution**: `sprint-refine-and-implement.yaml:38` and `recursive-refine.yaml:58–491` establish the append-only + `grep -qxF` idiom, but no existing loop uses action-token membership guards inside a routing dispatch script; `diagnose` has no init/setup phase today
- **Minimal Fix**: `route_conv_improved.on_yes: check_remediation_budget` (line 427) is the identical wiring shape; `rn-build.yaml` (`eval_gate → check_eval_retry_budget`) is a cross-loop precedent; reuse score 3/3

## Implementation Steps

1. In `rn-remediate.yaml`, update `check_convergence`: when `CONVERGED_STALLED` fires, check pass count vs `max_remediation_passes`; if under budget, emit a new `CONVERGED_STALLED_RETRY` token and route to `diagnose` instead of `emit_stalled_needs_decompose`
2. Add a `pass_count` tracking mechanism: a file `$RUN_DIR/pass_count_${ISSUE_ID}.txt` initialized to 0, incremented at the start of each diagnose→remediate cycle
3. Update `route_conv_*` routing states to handle `CONVERGED_STALLED_RETRY`
4. Optionally: add tried-action skip logic to `diagnose` for cleaner multi-pass behavior
5. Add a test to `test_builtin_loops.py` or a new test file validating that a stall-then-retry sequence routes to a second action

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete state references:**
- Step 1 target: `route_conv_manual_review.on_no` (line 445) — change value from `emit_stalled_needs_decompose` to `check_remediation_budget`; no change to `check_convergence` needed for the minimal fix
- `check_remediation_budget` (lines 448–466): shell reads `remediation_count_${ID}.txt` → `output_numeric lt ${context.max_remediation_passes}` → `on_yes: diagnose` / `on_no: emit_stalled_needs_decompose`; this state already handles both loop-back and terminal escalation correctly
- Step 2 (pass counter): already exists — `check_convergence` lines 381–385 write `remediation_count_${ID}.txt` and increment on every pass. If adding `CONVERGED_STALLED_RETRY` (full solution), a new counter separate from `remediation_count` may be cleaner; for the minimal fix no new counter is needed
- Step 5 test: follow `TestRnRemediateAssessRouting` pattern (`test_builtin_loops.py` lines 6816–6838) — load YAML, assert `data["states"]["route_conv_manual_review"].get("on_no") == "check_remediation_budget"`; add to `test_rn_remediate.py` for integration-level stall-then-retry coverage

**Recommended implementation order (minimal fix first, validate, then optionally add tried-action skip):**
1. Change `route_conv_manual_review.on_no` → `check_remediation_budget` (one line)
2. Update two breaking tests in `test_rn_remediate.py`: `test_convergence_router_chain_is_correct` (line 440) and `test_decompose_token_distinguishes_stall_from_too_large` (line 846) — change `"emit_stalled_needs_decompose"` to `"check_remediation_budget"` in the `route_conv_manual_review` assertions
3. Add structural test asserting the new `on_no` target
4. Validate with `ll-loop validate rn-remediate` — no new MR violations expected
5. Run `python -m pytest scripts/tests/test_rn_remediate.py scripts/tests/test_builtin_loops.py -v`
6. Update `docs/guides/LOOPS_REFERENCE.md` lines 520, 522, and 544–548 to reflect budget-gated STALLED routing
7. Optionally layer tried-action skip logic on top if needed based on runtime behavior

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_rn_remediate.py` — fix `TestConvergenceRouting.test_convergence_router_chain_is_correct` (line 456): change `assert rcmr["on_no"] == "emit_stalled_needs_decompose"` to `"check_remediation_budget"`
7. Update `scripts/tests/test_rn_remediate.py` — fix `TestOutcomeTokenChannel.test_decompose_token_distinguishes_stall_from_too_large` (line 855): same assertion update for `route_conv_manual_review`
8. Update `docs/guides/LOOPS_REFERENCE.md` — three stale passages: line 520 (convergence rules sentence), line 522 (stall-token emitter anchor), lines 544–548 (Phase 5 FSM flow block comment + typo fix `emit_needs_decompose` → `emit_stalled_needs_decompose`)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `check_convergence`, `diagnose`, routing states

### Tests
- `scripts/tests/test_rn_remediate.py` — **primary test file** (88 tests); covers convergence routing, budget tracking, and `remediation_count` file logic; add new `CONVERGED_STALLED` retry tests here
- `scripts/tests/test_builtin_loops.py` — structural routing assertions via `TestRnRemediateAssessRouting` (lines 6816–6838); pattern: load YAML, assert `state.get("on_no") == "target_state"`; add assertion for `route_conv_manual_review.on_no` here
- `scripts/tests/test_rn_implement.py` — parent orchestrator tests; validates `max_remediation_passes` parameter passing to rn-remediate

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_remediate.py` — `TestConvergenceRouting.test_convergence_router_chain_is_correct` (line 440): asserts `rcmr["on_no"] == "emit_stalled_needs_decompose"` — **will break**, must update to `"check_remediation_budget"` [Agent 3 finding]
- `scripts/tests/test_rn_remediate.py` — `TestOutcomeTokenChannel.test_decompose_token_distinguishes_stall_from_too_large` (line 846): asserts `data["states"]["route_conv_manual_review"]["on_no"] == "emit_stalled_needs_decompose"` — **will break**, must update to `"check_remediation_budget"` [Agent 3 finding]

### Dependent Files (Callers/Importers)
- `ll-loop run rn-remediate` — CLI entry point that executes this loop
- Other `rn-*` loops (`rn-plan`, `rn-build`, `rn-refine`) — share convergence patterns; review for consistency

### Similar Patterns
- `scripts/little_loops/loops/rn-plan.yaml` — `check_substrate` feasibility gate as reference for bounded-retry pattern
- `scripts/little_loops/loops/rn-build.yaml` — convergence + pass-count pattern to mirror

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — **primary doc target** (lines 474–520): convergence rules, parameters table, and `max_remediation_passes` semantics; update the CONVERGED_STALLED description if convergence contract changes
- `scripts/little_loops/loops/README.md` — built-in loops overview; lists rn-remediate parameters
- `docs/guides/LOOPS_GUIDE.md` — general loop authoring guide; lower-priority update

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` line 520 — convergence rules sentence reads `CONVERGED_STALLED → failed`; after fix it routes to `check_remediation_budget` first — update to reflect budget-gated path [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` line 522 — "Stall vs. too-large outcome tokens (BUG-2006)" paragraph names `route_conv_manual_review.on_no` as the direct stall-token emitter; after fix this anchor delegates to `check_remediation_budget` — update parenthetical [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` lines 544–548 — Phase 5 FSM flow block comment reads `STALLED or budget exhausted → emit_needs_decompose → failed`; after fix both `CONVERGED_STALLED` and budget-exhausted paths converge at `check_remediation_budget` (also contains pre-existing typo: `emit_needs_decompose` should be `emit_stalled_needs_decompose`) — update comment [Agent 2 finding]

### Configuration
- N/A — `max_remediation_passes` is a context variable in `rn-remediate.yaml`, not external config

## Acceptance Criteria

- [ ] BUG-2094-style scenario (WIRE → zero-delta → REFINE attempt) exercises the retry path
- [ ] `max_remediation_passes` is respected: loop terminates after N total actions, not just N IMPROVED passes
- [ ] STALLED-after-all-passes-exhausted still routes to decompose/defer (no change to terminal behavior)
- [ ] Existing convergence tests pass

## Impact

- **Priority**: P2 — currently causes any high-ambiguity issue with a near-threshold outcome confidence to be deferred after one WIRE attempt, even when REFINE would resolve it
- **Effort**: Medium — convergence routing change + pass counter + optional skip logic
- **Risk**: Low — adds a bounded retry path; existing STALLED terminal behavior preserved

## Resolution

**Minimal fix** implemented as decided by `/ll:decide-issue`:

- Changed `route_conv_manual_review.on_no` from `emit_stalled_needs_decompose` → `check_remediation_budget` in `rn-remediate.yaml` (single line)
- Updated two breaking assertions in `test_rn_remediate.py` (`test_convergence_router_chain_is_correct`, `test_decompose_token_distinguishes_stall_from_too_large`)
- Updated three stale passages in `docs/guides/LOOPS_REFERENCE.md` (convergence rules sentence, stall-token description, Phase 5 FSM flow block)
- All 915 tests pass; `ll-loop validate rn-remediate` clean

`CONVERGED_STALLED` now enters the same budget-gated retry path as `CONVERGED_IMPROVED`, re-entering `diagnose` up to `max_remediation_passes` times before escalating to `STALLED_NEEDS_DECOMPOSE`.

## Status

**Done** | Created: 2026-06-12 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-06-13T00:21:36 - `6c003b5f-1f63-4f09-9f19-fd239ed12dee.jsonl`
- `/ll:confidence-check` - 2026-06-12T22:00:00 - `c071609e-50a7-4b62-8251-935df44f93be.jsonl`
- `/ll:wire-issue` - 2026-06-13T00:12:11 - `27829a52-4279-4c2e-8374-4fe6e74105ec.jsonl`
- `/ll:decide-issue` - 2026-06-12T22:59:15 - `244f5266-6bd9-41d3-b93e-d3b4145272d1.jsonl`
- `/ll:refine-issue` - 2026-06-12T22:45:10 - `c4e926c4-e320-4f15-ab00-fef63e5cca3e.jsonl`
- `/ll:format-issue` - 2026-06-12T22:36:58 - `c502b76d-4bbe-49e5-8ab6-1fda49f65344.jsonl`
- `/ll:capture-issue` - 2026-06-12T21:57:47Z - `1d082110-33a6-4d3d-81dc-2230772df08a.jsonl`
