---
id: ENH-2107
title: "rn-remediate: CONVERGED_STALLED should retry diagnose with a different action before escalating"
type: ENH
priority: P2
status: open
captured_at: '2026-06-12T21:57:47Z'
discovered_date: '2026-06-12'
discovered_by: capture-issue
parent: EPIC-1811
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

If the tried-actions mechanism is too invasive: change the `CONVERGED_STALLED` routing to simply loop back to `diagnose` up to `max_remediation_passes` (same logic as `CONVERGED_IMPROVED`). Without skip logic, `diagnose` will route to the same action again — but on a re-run it has updated scores (post-wire), so the routing might change naturally as ambiguity flags clear.

## Implementation Steps

1. In `rn-remediate.yaml`, update `check_convergence`: when `CONVERGED_STALLED` fires, check pass count vs `max_remediation_passes`; if under budget, emit a new `CONVERGED_STALLED_RETRY` token and route to `diagnose` instead of `emit_stalled_needs_decompose`
2. Add a `pass_count` tracking mechanism: a file `$RUN_DIR/pass_count_${ISSUE_ID}.txt` initialized to 0, incremented at the start of each diagnose→remediate cycle
3. Update `route_conv_*` routing states to handle `CONVERGED_STALLED_RETRY`
4. Optionally: add tried-action skip logic to `diagnose` for cleaner multi-pass behavior
5. Add a test to `test_builtin_loops.py` or a new test file validating that a stall-then-retry sequence routes to a second action

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `check_convergence`, `diagnose`, routing states

### Tests
- `scripts/tests/test_builtin_loops.py` — convergence routing coverage

## Acceptance Criteria

- [ ] BUG-2094-style scenario (WIRE → zero-delta → REFINE attempt) exercises the retry path
- [ ] `max_remediation_passes` is respected: loop terminates after N total actions, not just N IMPROVED passes
- [ ] STALLED-after-all-passes-exhausted still routes to decompose/defer (no change to terminal behavior)
- [ ] Existing convergence tests pass

## Impact

- **Priority**: P2 — currently causes any high-ambiguity issue with a near-threshold outcome confidence to be deferred after one WIRE attempt, even when REFINE would resolve it
- **Effort**: Medium — convergence routing change + pass counter + optional skip logic
- **Risk**: Low — adds a bounded retry path; existing STALLED terminal behavior preserved

## Session Log
- `/ll:capture-issue` - 2026-06-12T21:57:47Z - `1d082110-33a6-4d3d-81dc-2230772df08a.jsonl`
