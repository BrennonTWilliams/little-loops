---
discovered_date: 2026-04-12
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# BUG-1079: recursive-refine runs issue-size-review twice when breakdown_issue fires

## Summary

When the `refine-to-ready-issue` sub-loop exits via `breakdown_issue` (issue failed readiness and hit the refine limit), the outer `recursive-refine` loop immediately runs `/ll:issue-size-review` a second time via its `run_size_review` state. This produces two back-to-back size-review prompt executions on the same issue, wasting LLM API calls. Observed on FEAT-1075 and FEAT-1076 in the same run (2026-04-12T204421).

## Current Behavior

After `refine-to-ready-issue` runs `breakdown_issue` → exits via `done`:

1. Outer loop: `check_passed` → exit=1 (issue not ready) → `detect_children`
2. `detect_children` → exit=1 (no child issues detected) → `size_review_snap` → `recheck_scores`
3. `recheck_scores` re-reads confidence/outcome scores; since `breakdown_issue` doesn't raise scores, it exits=1 → `run_size_review`
4. `run_size_review` calls `/ll:issue-size-review` **again**

Both executions run on the same issue ID within ~1 minute of each other.

## Expected Behavior

If `breakdown_issue` already ran inside the sub-loop, the outer loop's `run_size_review` state should be skipped. The loop should proceed directly to `enqueue_or_skip` (or the equivalent next step), since the size-review already completed and no new children were created.

## Motivation

Each redundant size-review prompt costs ~45–55 seconds of LLM wall-clock time and one full API call. At the scale of a recursive refine run over 5+ issues, this compounds. It also produces confusing audit history where the same issue appears to be reviewed twice in rapid succession.

## Proposed Solution

Add a flag file that `breakdown_issue` writes after executing (e.g., `.loops/tmp/refine-to-ready-broke-down`). In the outer `recursive-refine` loop, add a `check_broke_down` state (or extend `size_review_snap`) to check this flag:

- If the flag is set → skip `run_size_review`, go straight to `enqueue_or_skip`
- If the flag is not set → proceed through `recheck_scores` → `run_size_review` as today

Clear the flag at the start of each `run_refine` iteration (e.g., in `capture_baseline` or `resolve_issue`).

Alternatively, the outer loop could read the sub-loop's terminal state from the loop state JSON to detect whether `breakdown_issue` was the final state.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — extend `size_review_snap` (line 198) to check the broke-down flag, or add a `check_broke_down` state between `size_review_snap` and `recheck_scores`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — add flag-write step to `breakdown_issue` action (line 231); also clear `recursive-refine-broke-down` in `resolve_issue` init block (lines 21–23) alongside the existing `refine-to-ready-wire-done` clear, so all callers (not just `recursive-refine`) get a clean flag per run
- `docs/guides/LOOPS_GUIDE.md` — update FSM diagram (lines 459–471) to show `check_broke_down`; update prose (lines 428, 434) that describes the breakdown/size-review paths; add `recursive-refine-broke-down` to the tmp-files note (line 482) [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:318–381` (`_execute_sub_loop`) — maps `final_state="done"` → `on_yes` for both the confidence-pass path AND the `breakdown_issue → done` path; no changes needed
- `.loops/tmp/` scratch files — new flag file convention (directory already exists with existing flag files)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:37` — calls `loop: recursive-refine` as sub-loop; reads `recursive-refine-skipped.txt`/`recursive-refine-passed.txt` downstream; no changes needed
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:51` — calls `loop: recursive-refine` as sub-loop; same tmp-file read pattern; no changes needed
- `scripts/little_loops/loops/sprint-build-and-validate.yaml:117` — calls `loop: recursive-refine` with `context_passthrough: true`; no changes needed
- `scripts/little_loops/loops/issue-refinement.yaml:29` — calls `loop: refine-to-ready-issue` directly; **side-effect risk**: after the fix, a `breakdown_issue` exit from this caller will write `.loops/tmp/recursive-refine-broke-down` with no `capture_baseline` to clear it. Mitigation: clear the flag in `refine-to-ready-issue`'s `resolve_issue` init block (already identified in Files to Modify)

### Similar Patterns
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:86–108` — `check_wire_done`/`mark_wire_done` pattern: guard reads `cat .loops/tmp/refine-to-ready-wire-done 2>/dev/null || echo 0` evaluated with `output_numeric lt 1`; writer does `printf '1' > .loops/tmp/refine-to-ready-wire-done`; cleared at `resolve_issue:22–23` with `printf '0'`

### Tests
- `scripts/tests/test_builtin_loops.py` — covers `recursive-refine` and `refine-to-ready-issue` by name; add test here asserting `/ll:issue-size-review` fires exactly once when the `breakdown_issue` path is taken
- `scripts/tests/test_fsm_executor.py` — FSM executor tests; covers `_execute_sub_loop` behavior
- `scripts/tests/test_ll_loop_integration.py` — integration test patterns to model after for sub-loop → outer-loop interaction

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break** (must update as part of implementation):
- `scripts/tests/test_builtin_loops.py:948` (`test_required_states_exist` in `TestRecursiveRefineLoop`) — hard-codes required state set; will fail with `"Missing states: {'check_broke_down'}"` unless `"check_broke_down"` is added
- `scripts/tests/test_builtin_loops.py:1042` (`test_size_review_snap_routes_to_recheck_scores` in `TestRecursiveRefineLoop`) — asserts `size_review_snap.next == "recheck_scores"`; breaks when routing changes to `check_broke_down`; rename test to `test_size_review_snap_routes_to_check_broke_down`
- `scripts/tests/test_builtin_loops.py:597` (`test_breakdown_issue_routes_to_done` in `TestRefineToReadyIssueSubLoop`) — asserts `breakdown_issue.next == "done"`; breaks when `write_broke_down` is inserted before `done`

**New tests to write** — follow `check_wire_done` pattern (`test_builtin_loops.py:611–668`) which uses YAML structural assertions only (no executor simulation). Add to `TestRecursiveRefineLoop`:
- `test_check_broke_down_state_exists` — `"check_broke_down" in data["states"]`
- `test_check_broke_down_evaluate_output_numeric_lt_1` — evaluate block: `type=output_numeric`, `operator=lt`, `target=1`
- `test_check_broke_down_on_yes_routes_to_recheck_scores` — `on_yes == "recheck_scores"`
- `test_check_broke_down_on_no_routes_to_enqueue_or_skip` — `on_no == "enqueue_or_skip"`
- `test_check_broke_down_on_error_routes_to_recheck_scores` — `on_error == "recheck_scores"`
- `test_broke_down_flag_cleared_in_capture_baseline` — `"recursive-refine-broke-down" in capture_baseline.action`

Add to `TestRefineToReadyIssueSubLoop`:
- `test_write_broke_down_state_exists` — `"write_broke_down" in data["states"]`
- `test_breakdown_issue_routes_to_write_broke_down` — `breakdown_issue.next == "write_broke_down"`
- `test_write_broke_down_routes_to_done` — `write_broke_down.next == "done"`
- `test_write_broke_down_action_writes_flag` — `"recursive-refine-broke-down" in write_broke_down.action`

**Additional test file to check:**
- `scripts/tests/test_fsm_fragments.py:836–837` — references `recursive-refine.yaml` and `refine-to-ready-issue.yaml` by filename; verify the new `check_broke_down` and `write_broke_down` states don't violate any schema checks in that file

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:459–471` — FSM flow diagram shows `size_review_snap → recheck_scores` directly; will be stale after `check_broke_down` is inserted; update diagram to show the new branch
- `docs/guides/LOOPS_GUIDE.md:428` — prose states "breakdown_issue path or explicit size-review" as two separate mechanisms for child detection, implying the double execution is the design; update to clarify the guard
- `docs/guides/LOOPS_GUIDE.md:434` — "score gate" callout describes `recheck_scores` as the first gate before size-review; incomplete after `check_broke_down` is added as an earlier gate
- `docs/guides/LOOPS_GUIDE.md:482` — notes section lists only `recursive-refine-skipped.txt` and `recursive-refine-passed.txt`; add `recursive-refine-broke-down` to this list

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/loops/refine-to-ready-issue.yaml` `breakdown_issue` state (line 231): convert `action:` to a multi-step shell block that writes the flag then runs the size-review, or change `action_type` to `shell` and chain: `printf '1' > .loops/tmp/recursive-refine-broke-down && ll-loop ... --slash "/ll:issue-size-review ..."`. Simplest: add a `write_broke_down` state before `done` that writes the flag.
2. In `scripts/little_loops/loops/recursive-refine.yaml` `size_review_snap` state (line 198): add a guard check using the same `output_numeric lt 1` pattern as `check_wire_done` (`refine-to-ready-issue.yaml:86–95`) — if flag is set, route `on_no: enqueue_or_skip` (skipping `recheck_scores` and `run_size_review`).
3. In `scripts/little_loops/loops/recursive-refine.yaml` `capture_baseline` state (line 72): add `rm -f .loops/tmp/recursive-refine-broke-down &&` at the start of the action to clear the flag per-issue-iteration.
4. Verify with a dry-run trace that an issue hitting the refine limit produces exactly one `issue-size-review` call; run `python -m pytest scripts/tests/test_builtin_loops.py -v -k "breakdown"` to confirm.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. In `scripts/little_loops/loops/refine-to-ready-issue.yaml` `resolve_issue` init block (lines 21–23): add `printf '0' > .loops/tmp/recursive-refine-broke-down` alongside the existing wire-done clear, so non-`recursive-refine` callers (e.g., `issue-refinement.yaml`) don't accumulate a stale flag across runs
6. In `scripts/tests/test_builtin_loops.py`: update 3 breaking tests (`test_required_states_exist`, `test_size_review_snap_routes_to_recheck_scores`, `test_breakdown_issue_routes_to_done`) per patterns in Tests section above
7. In `scripts/tests/test_builtin_loops.py`: add 10 new structural tests for `check_broke_down` (in `TestRecursiveRefineLoop`) and `write_broke_down` (in `TestRefineToReadyIssueSubLoop`) per patterns in Tests section above; verify `test_fsm_fragments.py:836–837` still passes
8. In `docs/guides/LOOPS_GUIDE.md`: update FSM diagram (lines 459–471), prose (lines 428, 434), and tmp-files note (line 482) to reflect the new `check_broke_down` state

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Exact YAML syntax to follow for the guard state (model after `check_wire_done` at `refine-to-ready-issue.yaml:86`):

```yaml
check_broke_down:
  action: |
    cat .loops/tmp/recursive-refine-broke-down 2>/dev/null || echo 0
  action_type: shell
  evaluate:
    type: output_numeric
    operator: lt
    target: 1
  on_yes: recheck_scores    # 0 → not broken down → proceed normally
  on_no: enqueue_or_skip    # 1 → already size-reviewed → skip
  on_error: recheck_scores
```

Insert this state between `size_review_snap` (line 198) and `recheck_scores` (line 211) in `recursive-refine.yaml`.

## Impact

- **Priority**: P3 — wasteful but not blocking; produces incorrect audit trail
- **Effort**: Small — 3 state action edits across 2 YAML files
- **Risk**: Low — additive flag-check logic; no changes to core runner
- **Breaking Change**: No

## Root Cause

- **File**: `scripts/little_loops/loops/recursive-refine.yaml` (state: `recheck_scores`, line 211)
- **Anchor**: `on_no: run_size_review` (line 250)
- **Cause**: `recheck_scores` routes to `run_size_review` whenever confidence/outcome scores are below threshold — but scores are never raised by `breakdown_issue`, so this path always fires after a breakdown, even though `/ll:issue-size-review` just ran inside the sub-loop.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/executor.py:318–381` (`_execute_sub_loop`): Maps `final_state == "done"` → `on_yes` for **both** the confidence-pass path and the `breakdown_issue → done` path. The outer loop cannot distinguish them.
- `breakdown_issue` (`refine-to-ready-issue.yaml:231–235`): Calls `/ll:issue-size-review` then unconditionally takes `next: done` with no flag written — identical exit signature to a confidence pass.
- Double-invocation path confirmed: `run_refine (line 88) → check_passed:139 (on_no) → detect_children:178 (on_no) → size_review_snap:208 (next) → recheck_scores:250 (on_no) → run_size_review:256`.
- `capture_baseline` (line 72) is the right place to clear the flag — runs immediately before `run_refine` for each dequeued issue, per-iteration.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99711cfa-c6a8-4520-8e2f-6622a3224ca6.jsonl`
- `/ll:wire-issue` - 2026-04-12T23:03:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e3cd62e7-0dae-42cb-bbc9-f72e7d7cff7b.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:40:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7c9802d-2089-4939-b342-91f160e169da.jsonl`

- `/ll:capture-issue` - 2026-04-12T22:33:28+00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9da6eb97-069e-44c5-91dc-b06213bbdb44.jsonl`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3
