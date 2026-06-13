---
id: BUG-2111
title: "FSM capture-ordering fix prerequisites \u2014 verify harness-optimize seeding\
  \ and classify unlisted ALLOWLIST entries"
type: BUG
priority: P1
status: done
parent: BUG-2094
captured_at: '2026-06-13T00:00:00Z'
completed_at: '2026-06-13T16:16:51Z'
discovered_date: '2026-06-13'
relates_to:
- BUG-2094
- ENH-1961
size: Small
confidence_score: 96
outcome_confidence: 90
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 25
labels:
- fsm
- capture-ordering
- prerequisite
- investigation
---

# BUG-2111: FSM capture-ordering fix prerequisites — verify harness-optimize seeding and classify unlisted ALLOWLIST entries

## Summary

Prerequisite classification work for BUG-2094. Two ambiguities must be resolved before the main fix branch (BUG-2112) can correctly manage `TestValidatorWarningBudget.ALLOWLIST`:

1. Whether `harness-optimize.yaml` `init_prev` state seeds `state_name` and `benchmark_score` (determines Bucket A vs Bucket B)
2. Whether two unlisted ALLOWLIST entries (`goal-cluster/reassess` and `integrate-sdk/scaffold_integration`) are sub-loop false positives or bypass-path crash risks

## Parent Issue

Decomposed from BUG-2094: FSM loops reference captures from states that may not have executed (InterpolationError crashes)

## Current Behavior

`TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py` contains:
- `("harness-optimize", "capture-ordering")` entries for `propose` and `apply` states — status uncertain (Bucket A or B pending seeding verification)
- `("goal-cluster", "capture-ordering"): states.reassess.action` — not in triage table, unclassified
- `("integrate-sdk", "capture-ordering"): states.scaffold_integration.action` — not in triage table, unclassified

## Steps to Reproduce

1. Open `scripts/tests/test_builtin_loops.py` and inspect `TestValidatorWarningBudget.ALLOWLIST`
2. Note the `("harness-optimize", "capture-ordering")` entries for `propose` and `apply` states — bucket (A vs B) is undetermined without tracing `init_prev` seeding
3. Note `("goal-cluster", "capture-ordering")` and `("integrate-sdk", "capture-ordering")` entries absent from the BUG-2094 triage table — classification unknown
4. Attempt to implement BUG-2112 ALLOWLIST management without these classifications — BUG-2112 implementer cannot safely act on entries without A/B determination

## Expected Behavior

Each entry is classified as either:
- **Bucket A** (sub-loop false positive → keep in ALLOWLIST with explanatory comment)
- **Bucket B** (bypass-path crash risk → add `:default=` then handle per Approach A/B in BUG-2112)

Classification decisions are documented so BUG-2112 can proceed without re-investigation.

## Proposed Solution

### Task 1 — Verify harness-optimize.yaml seeding

Read `scripts/little_loops/loops/harness-optimize.yaml` and trace the `init_prev` state:

```bash
# Look for what init_prev produces / writes into context
grep -A 20 "init_prev:" scripts/little_loops/loops/harness-optimize.yaml
```

Check whether `init_prev` populates `state_name` and `benchmark_score` in its output/captures. If yes → `propose` and `apply` are false positives (sub-loop or init-seeded data), classify as **Bucket A**. If no → classify as **Bucket B** (bypass-path crash risk).

### Task 2 — Classify unlisted ALLOWLIST entries

Run the validator on each loop:

```bash
ll-loop validate scripts/little_loops/loops/goal-cluster.yaml
ll-loop validate scripts/little_loops/loops/integrate-sdk.yaml
```

For `goal-cluster` `states.reassess.action`: identify which `${captured.*}` references it uses and whether the capturing state can be bypassed. Classify as Bucket A (sub-loop produce) or Bucket B (bypass-path crash).

For `integrate-sdk` `states.scaffold_integration.action`: same analysis. This state is adjacent to `diagnose_and_block` which is already Bucket B in the triage table; confirm whether `scaffold_integration` is a separate bypass-path case or a sub-loop dependency.

### Task 3 — Record findings

Update BUG-2112 (or document here as completed notes) with the resolved classifications so the implementer has authoritative guidance for ALLOWLIST decisions.

## Implementation Steps

1. Read `harness-optimize.yaml` to trace `init_prev` → `propose`/`apply` capture chain; classify harness-optimize entries
2. Run `ll-loop validate goal-cluster.yaml`; read `states.reassess.action` in the YAML; classify
3. Run `ll-loop validate integrate-sdk.yaml`; read `states.scaffold_integration.action`; classify
4. Add classification findings to the "## Findings" section in this issue (update before closing)
5. Mark this issue `done` once all three ambiguities are resolved

## Files to Read (no changes expected)

- `scripts/little_loops/loops/harness-optimize.yaml` — trace `init_prev` state
- `scripts/little_loops/loops/goal-cluster.yaml` — read `states.reassess.action`
- `scripts/little_loops/loops/integrate-sdk.yaml` — read `states.scaffold_integration.action`
- `scripts/tests/test_builtin_loops.py` — current `ALLOWLIST` for reference

## Acceptance Criteria

- [x] harness-optimize `propose`/`apply` classified as Bucket A or Bucket B with documented reasoning
- [x] `goal-cluster` `states.reassess.action` classified as Bucket A or Bucket B
- [x] `integrate-sdk` `states.scaffold_integration.action` classified as Bucket A or Bucket B
- [x] Findings recorded in this issue before closing

## Impact

- **Priority**: P1 — prerequisite for BUG-2112; unresolved, `test_allowlist_entries_are_not_stale` will fail in BUG-2112
- **Effort**: Small — investigation/read-only; no code changes expected
- **Risk**: None — read-only analysis
- **Breaking Change**: No

## Findings

### harness-optimize `propose` and `apply` — **Bucket B** (bypass-path crash risk)

`init_prev` does NOT seed `state_name` or `benchmark_score`. It only captures `prev_score` (echoes `baseline.output`).

- `propose` references `${captured.benchmark_score.output}`: `benchmark_score` is captured by `score` which runs *after* `propose`/`apply`. On every first iteration the path is `init_run → load_directive → baseline_score → init_prev → propose` — `score` has not run yet → InterpolationError.
- `propose` references `${captured.state_name.output}`: `state_name` is captured by `dequeue_state`. The validator-identified bypass path `init_run → load_directive → baseline_score → init_prev → propose` skips `dequeue_state` (non-queue-mode run or direct invocation) → InterpolationError.
- `apply` references `${captured.state_name.output}`: same bypass-path risk.

**BUG-2112 action**: Add `:default=` to `benchmark_score` and `state_name` references in `propose` and `apply` actions (Approach A or B per BUG-2112 design). Both ALLOWLIST entries should be removed after the fix.

### goal-cluster `states.reassess.action` — **Bucket A** (sub-loop false positive)

`reassess` uses `fragment: reassess` (a library fragment). No state in goal-cluster captures `plan_display` — the validator explicitly says "may be intentional; if 'plan_display' is produced by a sub-loop." The fragment contract expects `plan_display` to flow in from a parent loop's context when goal-cluster is invoked as a sub-loop. This is an intentional cross-loop context dependency, not a crash risk in normal execution.

**BUG-2112 action**: Keep in ALLOWLIST. Add explanatory comment: `# Bucket A: plan_display injected by parent loop via fragment contract`.

### integrate-sdk `states.scaffold_integration.action` — **Bucket A** (sub-loop false positive)

`targets` is not captured by any state in integrate-sdk itself. The `prove` state invokes the `oracles/enumerate-and-prove` sub-loop (`loop: oracles/enumerate-and-prove`) which parses the `ENUMERATE_JSON:{"targets": [...]}` output from `raw_enumeration` and injects `targets` into the parent context on success. The validator flags this correctly as "may be intentional if 'targets' is produced by a sub-loop." `diagnose_and_block` is Bucket B for separate reasons (bypass of `verify_result` and `scaffold_result` on the `prove → diagnose_and_block` path), but `scaffold_integration` itself is only reachable after `prove` succeeds, so `targets` is always available at that point.

**BUG-2112 action**: Keep in ALLOWLIST. Add explanatory comment: `# Bucket A: targets injected by oracles/enumerate-and-prove sub-loop on success path`.

## Session Log
- `/ll:ready-issue` - 2026-06-13T16:13:29 - `bae49a3a-65cb-4890-b361-62c43d5d9f6a.jsonl`
- `/ll:issue-size-review` - 2026-06-13T00:00:00Z - `d3e9937f-e366-49de-8410-e1dbe3b669f8.jsonl`
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `dee37e54-be42-4d49-9831-e69bf98d57d3.jsonl`
