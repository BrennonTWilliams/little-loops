# Test Quality Audit

*Audited: 2026-04-03*

## Summary

| Metric | Value |
|--------|-------|
| Test files | 87 |
| Total tests | ~4,045 |
| Test code (lines) | ~81,000 |
| Source modules covered | 32 of 33 |

Overall breadth is strong. The quality gaps are concentrated in the `parallel/` subsystem, specifically the orchestrator's integration wiring.

---

## Module Grades

| Module | Source Lines | Grade | Primary Weakness |
|--------|-------------|-------|-----------------|
| `fsm/executor.py` | 794 | **A** | None meaningful — routing, all 5+ termination modes, sub-loops, retries all covered |
| `fsm/evaluators.py` | 836 | **B+** | `diff_stall` stale-count-file reset not tested |
| `parallel/merge_coordinator.py` | 1,244 | **B** | 3-step merge fallback sequence never tested end-to-end; stash pop conflict cleanup path untested |
| `parallel/worker_pool.py` | 1,372 | **B−** | Concurrency paths missing; worktree cleanup failure not tested |
| `parallel/orchestrator.py` | 1,251 | **C** | Marked `integration` but all three core components (`WorkerPool`, `MergeCoordinator`, `IssuePriorityQueue`) are `MagicMock` — P0 routing, parallel dispatch, and completion callbacks have no real coverage |

---

## Gaps in Detail

### CRITICAL

**`test_orchestrator.py` mocks every collaborator**

The test fixture patches all three components on import:
```python
with (
    patch("little_loops.parallel.orchestrator.WorkerPool"),
    patch("little_loops.parallel.orchestrator.MergeCoordinator"),
    patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
):
```
This means the actual dispatch logic (`_execute`), P0 sequential routing, parallel dispatch, and the worker completion callback (`_on_worker_complete` → `merge_coordinator.queue_merge`) are never exercised. The `integration` mark is misleading.

### HIGH

**MergeCoordinator: 3-step fallback sequence not tested end-to-end**

Individual steps are verified in isolation:
- `_stash_local_changes` / `_pop_stash` — tested in `TestMergeStashBehavior`
- `_handle_conflict` rebase attempt — tested in `TestMergeStrategySkipsRebaseRetry`
- Error classification helpers — tested in `TestIsLocalChangesError` etc.

But there is no test that calls `_process_merge` with a real git conflict, walks through `git merge --no-ff` failing → `_handle_conflict` → `git rebase` on the worktree → re-queue. The coordinated fallback path has never been exercised as a unit.

**MergeCoordinator: stash pop conflict cleanup path not tested**

In `_pop_stash`, when `git stash pop` fails with unmerged entries, the code cleans up via `git checkout --theirs . && git reset HEAD`. This path (lines 268–281 in `merge_coordinator.py`) has no test verifying the cleanup behavior.

**WorkerPool: concurrency under concurrent leak detection**

`_detect_main_repo_leaks` and `_recover_committed_leaks` are tested for their logic, but not under concurrent worker load. The `GitLock` serialization assumption is never verified with multiple threads running simultaneously.

### MEDIUM

**`diff_stall`: stale count file not reset on first call**

If the state file is deleted but the count file is not (e.g., partial cleanup), the next call has `previous_diff = None` and correctly re-baselines — but no test verifies that the count file is reset to `"0"` in that scenario.

**WorkerPool: worktree cleanup failure**

`_cleanup_worktree` has no test for what happens when `git worktree remove` itself fails mid-cleanup.

**WorkerPool: continuation prompt under error state**

`_run_with_continuation` is tested for the happy path but not when the continuation prompt triggers an error state.

---

## What Was Done

As part of this audit, tests were added for the three most impactful gaps:

1. **`test_orchestrator.py`** — Added `TestDispatchRouting` class:
   - `test_p0_issue_routes_to_sequential`: verifies P0 issues call `_process_sequential`
   - `test_p1_issue_routes_to_parallel`: verifies P1 issues call `_process_parallel`
   - `test_on_worker_complete_success_queues_merge`: verifies completion callback calls `merge_coordinator.queue_merge`
   - `test_on_worker_complete_failure_marks_failed`: verifies failed workers are marked failed
   - `test_on_worker_complete_interrupted_not_marked_failed`: verifies interrupted workers are not failed

2. **`test_merge_coordinator.py`** — Added `TestProcessMergeFallbackSequence` class:
   - `test_merge_conflict_triggers_handle_conflict`: real git conflict via `_process_merge`, verifies `_handle_conflict` path is reached
   - `test_stash_pop_conflict_cleans_up_theirs`: stash pop fails with unmerged entries → verifies `checkout --theirs` cleanup

3. **`test_fsm_evaluators.py`** — Added to `TestDiffStallEvaluator`:
   - `test_first_call_resets_stale_count_file`: count file exists with non-zero value, state file deleted → verifies baseline resets count to 0

---

## Recommendations

| Priority | Action |
|----------|--------|
| High | Consider a true end-to-end smoke test for `ll-parallel` that creates real issues and runs through the full pipeline with a mock Claude subprocess |
| Medium | Add concurrent worker stress test for `WorkerPool` to verify `GitLock` actually serializes concurrent git ops |
| Medium | Add test for `_cleanup_worktree` when `git worktree remove` fails |
| Low | Add test for `_run_with_continuation` error state handling |
