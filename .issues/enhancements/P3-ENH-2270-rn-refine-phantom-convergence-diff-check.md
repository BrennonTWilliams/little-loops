---
id: ENH-2270
title: "Add diff-based phantom convergence check to rn-refine verify_score"
type: enhancement
status: done
loop: rn-refine
labels:
- enhancement
- fsm
- rn-refine
- evaluation
- convergence
decision_needed: false
confidence_score: 100
completed_at: 2026-06-24 21:31:29+00:00
---

## Summary

Extended `verify_score` in `rn-refine.yaml` with a second-stage diff check to detect phantom convergence: the case where a model claims `ALL_VERY_HIGH` but the `plan.md` is byte-for-byte identical to the previous iteration's snapshot.

## Problem

The `score` state evaluates the plan that `synthesize` just wrote. Because the same model both writes and scores the plan, it can output `ALL_VERY_HIGH` to the rubric file on an unchanged or superficially changed plan, passing the existing `verify_score` grep with no real improvement.

The prior guard (`verify_score` grep on `ALL_VERY_HIGH` in rubric file) only confirmed the string was written correctly — it could not detect that the file had not actually changed.

## Solution

Extended `verify_score` shell action with a two-stage gate:

1. **Stage 1 (existing)**: `grep -q "ALL_VERY_HIGH" plan-rubric.md` — confirms rubric was written.
2. **Stage 2 (new)**: `diff -q plan.md iter-(N-1)/plan.md` — compares current plan against the previous iteration's snapshot. If identical, outputs `PHANTOM_CONVERGENCE` which does not match the `output_contains: ALL_VERY_HIGH` evaluator, routing via `on_no → research_iteration`.

First iteration (`COUNTER <= 1`) skips the diff — no prior snapshot exists, so genuine first-pass convergence is never blocked. If the snapshot file is missing, the `[ -f "$PREV" ]` guard falls through to `ALL_VERY_HIGH`.

The `snapshot` state already ran before `score`, so `iter-N/plan.md` always holds the pre-score plan as the diff baseline. Zero new states, zero new LLM calls, zero new routing edges.

## Changes

- **`scripts/little_loops/loops/rn-refine.yaml:143–177`** — Extended `verify_score` shell action with diff-based phantom convergence detection
- **`scripts/tests/test_rn_refine.py`** — Added `TestPhantomConvergence` class (6 tests): phantom detected, plan-changed passes, first iteration skips diff, rubric-missing/iterate preserved, routing verified via FSM load

## Verification

- All 32 `test_rn_refine.py` tests pass (6 new + 26 existing)
- `PHANTOM_CONVERGENCE` does not match `ALL_VERY_HIGH` pattern → routes to `research_iteration` via `on_no` naturally


## Session Log
- `hook:posttooluse-status-done` - 2026-06-24T21:32:18 - `fa7c169d-eb54-4677-82b2-e67621565732.jsonl`
