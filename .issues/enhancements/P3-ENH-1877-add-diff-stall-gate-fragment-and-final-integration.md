---
id: ENH-1877
title: "Add diff_stall_gate fragment and complete Wave 4 integration"
type: ENH
priority: P3
parent: ENH-1777
captured_at: '2026-06-02T00:00:00Z'
discovered_date: 2026-06-02
discovered_by: issue-size-review
---

# ENH-1877: Add diff_stall_gate fragment and complete Wave 4 integration

## Summary

Add the `diff_stall_gate` fragment to `loops/lib/common.yaml`, convert the 3 caller loops, update documentation and skill references, bump the README loop count, and run the full Wave 4 validation suite. This is the final child of Wave 4 — it should be worked after ENH-1874 and ENH-1876 are merged so the README loop count reflects all new oracles.

## Parent Issue

Decomposed from ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows

## Current Behavior

The `diff_stall` evaluator is used in 3 loops with identical configuration: `incremental-refactor.yaml` (state `execute_step`, `on_no: replan`), `harness-multi-item.yaml` (state `check_stall`, `on_no: advance`), and `harness-single-shot.yaml` (state `check_stall`, `on_no: done`). All three use `max_stall: 2`. The `evaluate:` block is duplicated across all three.

## Expected Behavior

- `diff_stall_gate` fragment in `loops/lib/common.yaml` supplying `evaluate.type: diff_stall` and `evaluate.max_stall: 2` as defaults; caller supplies `action`, `action_type`, and all routing (`on_yes`, `on_no`, `on_error`)
- `incremental-refactor.yaml:execute_step`, `harness-multi-item.yaml:check_stall`, and `harness-single-shot.yaml:check_stall` converted to use `fragment: diff_stall_gate`
- `README.md` loop count updated from `**67 FSM loops**` to `**69 FSM loops**` (after the two new oracles from ENH-1874 and ENH-1876 are merged)
- Documentation updated in `skills/create-loop/reference.md` and `docs/guides/LOOPS_GUIDE.md`
- Full Wave 4 test suite passes

## Proposed Solution

1. Add `diff_stall_gate` fragment to `scripts/little_loops/loops/lib/common.yaml` — supplies `evaluate.type: diff_stall` and `evaluate.max_stall: 2`; model after `convergence_gate` (evaluator-only fragment); include `description:` field; caller supplies `action`, `action_type`, and routing
2. Convert `scripts/little_loops/loops/incremental-refactor.yaml:execute_step` `evaluate:` block to use `fragment: diff_stall_gate`; `on_no` routes to `replan`
3. Convert `scripts/little_loops/loops/harness-multi-item.yaml:check_stall` to use `fragment: diff_stall_gate`; `on_no: advance`
4. Convert `scripts/little_loops/loops/harness-single-shot.yaml:check_stall` to use `fragment: diff_stall_gate`; `on_no: done`
5. Run `ll-loop validate` on all 3 modified loops
6. Update `skills/create-loop/reference.md` — add `diff_stall_gate` row to `## Fragment Catalog → ### lib/common.yaml fragments` table; update `## Stall Detection` code example (~line 391) to show `fragment: diff_stall_gate` pattern
7. Update `docs/guides/LOOPS_GUIDE.md` — revise `### Stall Detection` inline example (~line 2766) to use `fragment: diff_stall_gate`
8. After ENH-1874 and ENH-1876 are merged: update `README.md` — bump loop count from `**67 FSM loops**` to `**69 FSM loops**`; run `ll-verify-docs` to confirm count matches
9. Run expanded Wave 4 test suite: `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py scripts/tests/test_loops_recursive_refine.py scripts/tests/test_deep_research.py scripts/tests/test_deep_research_arxiv.py scripts/tests/test_doc_counts.py -v --tb=short`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — add `diff_stall_gate` fragment (depends on ENH-1875 adding `queue_pop`/`queue_track` to same file — merge ENH-1875 first)
- `scripts/little_loops/loops/incremental-refactor.yaml` — convert `execute_step` evaluate block
- `scripts/little_loops/loops/harness-multi-item.yaml` — convert `check_stall`
- `scripts/little_loops/loops/harness-single-shot.yaml` — convert `check_stall`
- `README.md` — bump loop count to `**69 FSM loops**` (after ENH-1874 and ENH-1876 merged)
- `skills/create-loop/reference.md` — add `diff_stall_gate` to fragment catalog + update Stall Detection example
- `docs/guides/LOOPS_GUIDE.md` — update Stall Detection example

### Dependent Files
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_diff_stall()` implementation; persists state to `.loops/tmp/ll-diff-stall-<hash>.txt`; optional `scope:` field limits diff to specific paths — read to understand what the fragment wraps

### Ordering Constraint
- This child modifies `loops/lib/common.yaml`; ENH-1875 also modifies this file. Merge ENH-1875 before working this child to avoid conflicts.
- The README count bump (step 8) must wait for ENH-1874 and ENH-1876 to merge.

### Tests
- `scripts/tests/test_fsm_fragments.py` — add `TestDiffStallGateFragment` class following `TestConvergenceGateFragment` pattern (schema presence + `resolve_fragments` integration test); ensure `description:` field present
- Ensure `test_all_common_yaml_fragments_have_description` passes for `diff_stall_gate`

## Success Metrics

- `diff_stall_gate` standardizes `diff_stall` evaluator configuration across 3 loops
- All modified loops pass `ll-loop validate`
- All Wave 4 documentation updated
- `ll-verify-docs` passes with updated loop count
- Full Wave 4 test suite passes: test_builtin_loops, test_fsm_fragments, test_loops_recursive_refine, test_deep_research, test_deep_research_arxiv, test_doc_counts

## Session Log
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
