---
id: BUG-2115
title: "rn-remediate re_assess: MR-4 violation \u2014 missing on_partial/on_no routes\
  \ causes subloop to terminate with error"
priority: P2
type: BUG
status: open
captured_at: '2026-06-13T00:00:00Z'
discovered_date: '2026-06-13'
discovered_by: audit-loop-run
affects: scripts/little_loops/loops/rn-remediate.yaml
labels:
- rn-remediate
- loop-defect
- mr-4
- evaluator
relates_to:
- BUG-2075
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2115: rn-remediate re_assess MR-4 — missing on_partial/on_no terminates subloop with error

## Summary

The `re_assess` state in `rn-remediate.yaml` has the same MR-4 violation that BUG-2075 fixed for the `assess` state: it defines only `on_success: verify_re_assess_scores` with no `on_partial` or `on_no`. When the LLM evaluator returns `partial` (confidence-check completed but the persistence step was unconfirmed), the FSM has no route and terminates the subloop with `terminated_by: error` — leaving no `subloop_outcome_<ID>.txt`, so the parent `rn-implement` loop never receives a verdict.

## Current Behavior

When `re_assess` executes `/ll:confidence-check` and the LLM evaluator returns `partial`, the FSM finds no `on_partial` route in the state definition. The subloop terminates with `terminated_by: error` and does not write `subloop_outcome_<ID>.txt`, causing the parent `rn-implement` loop to receive no verdict and stall.

## Steps to Reproduce

1. Select an issue ready for implementation
2. Run `ll-loop run rn-implement --issue <ID>`
3. Allow the loop to proceed through `assess` and `wire` states
4. Observe `re_assess` state executing `/ll:confidence-check <ID> --auto`
5. When the LLM evaluator returns `partial` (core work confirmed, persistence step unconfirmed), the subloop terminates with `terminated_by: error`
6. No `subloop_outcome_<ID>.txt` is written; parent loop receives no verdict

## Observed Instance

**Run**: `rn-implement-20260613T124334`, input BUG-2011  
**Sequence** (from `usage.jsonl`):
1. `17:47:07Z` — `assess` → `/ll:confidence-check BUG-2011 --auto` (8 581 output tokens)
2. `18:06:33Z` — `wire` → `/ll:wire-issue BUG-2011 --auto` (25 902 output tokens)
3. `18:10:28Z` — `re_assess` → `/ll:confidence-check BUG-2011 --auto` (8 982 output tokens)

After step 3, no `subloop_outcome_BUG-2011.txt` was written and no further events are recorded. The `re_assess` LLM evaluator returned `partial` (action completed, persistence step unconfirmed), found no `on_partial` route, and the subloop silently died with error.

## Root Cause

**File**: `scripts/little_loops/loops/rn-remediate.yaml` — `re_assess` state

```yaml
re_assess:
  fragment: with_rate_limit_handling
  action: "/ll:confidence-check ${context.issue_id} --auto"
  action_type: slash_command
  on_success: verify_re_assess_scores
  on_error: emit_implement_failed
  on_rate_limit_exhausted: rate_limit_diagnostic
  # ← no on_partial, no on_no
```

The `with_rate_limit_handling` fragment adds retry/backoff fields but no LLM-verdict routes. When the action exits `0` but the evaluator returns `partial`, there is no route → FSM dead-end → error termination.

BUG-2075 applied the fix to `assess`:
```yaml
assess:
  on_yes: verify_scores_persisted
  on_no: refine
  on_partial: verify_scores_persisted   # ← added by BUG-2075
```

But `re_assess` was not updated at the same time.

## Expected Behavior

`re_assess` should route `partial` → `verify_re_assess_scores` (treat partial as "core work done, proceed optimistically") and `on_no` → `refine` (re-assess found low confidence, fall back to refine), mirroring the BUG-2075 fix on `assess`.

## Proposed Solution

```yaml
# rn-remediate.yaml — re_assess state
re_assess:
  fragment: with_rate_limit_handling
  action: "/ll:confidence-check ${context.issue_id} --auto"
  action_type: slash_command
  on_success: verify_re_assess_scores
  on_partial: verify_re_assess_scores   # ADD: partial → proceed (core work done)
  on_no: refine                          # ADD: no → fall back to refine
  on_error: emit_implement_failed
  on_rate_limit_exhausted: rate_limit_diagnostic
```

## Acceptance Criteria

- [ ] `re_assess` state in `rn-remediate.yaml` has `on_partial: verify_re_assess_scores`
- [ ] `re_assess` state has `on_no: refine`
- [ ] `ll-loop validate rn-remediate` passes with no MR-4 warnings on `re_assess`
- [ ] A test in `scripts/tests/test_rn_remediate.py` asserts `on_partial` and `on_no` are set on `re_assess` (model after the `assess` MR-4 test added by BUG-2075)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `re_assess` state: add `on_partial: verify_re_assess_scores` and `on_no: refine`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — FSM route-table processor (no changes needed)

### Similar Patterns
- `assess` state in `rn-remediate.yaml` — same fix already applied by BUG-2075 (`on_partial: verify_scores_persisted`, `on_no: refine`)

### Tests
- `scripts/tests/test_rn_remediate.py` — add assertion that `re_assess` has `on_partial` and `on_no` (model after the `assess` MR-4 regression test added by BUG-2075)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `on_partial: verify_re_assess_scores` and `on_no: refine` to `re_assess` state in `rn-remediate.yaml`
2. Run `ll-loop validate rn-remediate` to confirm no MR-4 warnings on `re_assess`
3. Add regression test in `scripts/tests/test_rn_remediate.py` asserting `on_partial` and `on_no` present on `re_assess`
4. Run test suite to verify

## Impact

- **Priority**: P2 — Blocks `rn-implement` from completing when confidence check returns partial; subloop silently fails with no outcome artifact
- **Effort**: Small — Two-field YAML addition + one test assertion; mirrors BUG-2075 fix on `assess`
- **Risk**: Low — YAML config change only, no Python logic changes; same pattern as BUG-2075
- **Breaking Change**: No

## Session Log
- `/ll:ready-issue` - 2026-06-13T18:40:57 - `e0c93114-1916-4d4e-b266-17bd9d715aab.jsonl`
- `/ll:format-issue` - 2026-06-13T18:32:54 - `bd2eb6a7-568d-4a00-8298-d0d06d2d9a27.jsonl`
- `/ll:audit-loop-run` - 2026-06-13T00:00:00Z - discovered during audit of rn-implement-20260613T124334
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `aa68867a-a48d-436c-bfa2-c625e339801a.jsonl`
