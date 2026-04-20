---
discovered_date: "2026-04-20"
discovered_by: parallel-fsm-review
depends_on: [FEAT-1075, FEAT-1076]
parent_issue: ENH-1175
---

# FEAT-1184: Parallel Worker Side-Effect Cleanup Contract

## Summary

Define and enforce the side-effect cleanup contract for workers that fail, time out, or are cancelled during parallel fan-out. Covers worktree branch disposition, thread-mode write safety documentation, and the always-one-entry-per-item guarantee for `${captured.<state>.results}`. Extracted from the cleanup half of ENH-1175 (the retry half remains P3 and stays in ENH-1175) because without a documented cleanup contract, v1 behavior is undefined — a failed worktree worker may leak orphaned branches and callers cannot distinguish "no worker ran for item N" from "worker ran for item N and failed."

## Current Behavior (as of FEAT-1075 / FEAT-1076 as specified)

`ParallelRunner` treats any worker failure as terminal but the cleanup side is implicit:
- Worktree mode: whether a failed worker's branch is deleted, kept for inspection, or half-merged is undefined.
- Thread mode: workers share the parent filesystem; partial writes from a failing worker may persist on disk.
- `self.captured[state_name].results` contents after failure are not specified — callers don't know if failed items appear at all.

These implicit choices surface as inconsistent behavior in production, especially across thread-vs-worktree modes.

## Expected Behavior

### Worktree mode

1. **Successful worker** — worker's branch is merged back to the parent branch via `MergeCoordinator`; worktree is torn down; all side effects are now visible on the parent branch.
2. **Failed worker** (`verdict == "no"`, `terminated_by in {"error", "timeout", "max_iterations", "handoff"}`) — worker's branch is **NOT merged**; the worktree is torn down; the branch is **deleted** via `git branch -D`. No partial state leaks to the parent branch.
3. **Cancelled worker** (`terminated_by == "cancelled"` — reserved for ENH-1165 Option A full cancellation) — branch state as of last worker checkpoint is preserved; worktree is kept for manual inspection; the `ParallelItemResult` records `terminated_by: "cancelled"` so downstream tools can locate the preserved worktree.

### Thread mode

Thread-mode workers share the parent filesystem, so automatic cleanup is impossible. Document explicitly in `docs/generalized-fsm-loop.md` and in `skills/create-loop/loop-types.md`:

> **Thread mode is safe for read-only or idempotent sub-loops.** If a thread-mode sub-loop writes files, there is no rollback on failure; partial writes from a failing worker persist on disk. Use `isolation: worktree` for any sub-loop that writes files concurrently. `fail_mode: collect` + thread-mode writers is "last write wins, possibly corrupted."

### `all_results` / `${captured.<state>.results}` contract

Regardless of mode or `fail_mode`:
- `len(result.all_results) == len(items)` after the run completes (in `collect`) or raises (in `fail_fast`, cancelled slots are still populated with `terminated_by: "cancelled"` sentinels).
- Entry `result.all_results[i]` always corresponds to `items[i]` (ordering guarantee from FEAT-1075).
- Each entry carries `verdict`, `terminated_by`, `error` fields (FEAT-1075 `ParallelItemResult`).
- Downstream states can filter on `verdict == "yes"` to distinguish successful workers from failed ones without losing item-index correspondence.

## Use Case

**Who**: An automation engineer running a parallel `recursive-refine` over 10 issues where 1 worker hits a transient git-lock contention and fails in worktree mode.

**Context**: The failed worker's branch currently lingers in the repo (no cleanup defined), cluttering `git branch -a` output over time. Worse, a half-merged state could corrupt the parent branch if `MergeCoordinator` is invoked partway through.

**Goal**: The failed worker's branch is deleted cleanly; no merge artifacts reach the parent; the downstream `on_partial` route sees a complete `results[]` list with one entry per input item and can decide how to handle the 1 failure.

**Outcome**: v1 parallel ships with defined, testable cleanup behavior. No orphaned worktree branches accumulate over time.

## Proposed Solution

### 1. Worktree cleanup in `ParallelRunner`

**Critical: where cleanup runs determines correctness.** Two constraints:

1. Worktree teardown (`git worktree remove`) can run in the worker thread as soon as the worker's `FSMExecutor.run()` returns — it touches only the worker's private worktree directory.
2. **Branch operations (merge-back via `MergeCoordinator`, or `git branch -D` on failure) MUST run on the main thread, serialized by the existing `GitLock`**, AFTER the worker's future has been joined. They must NOT run inside the worker thread. Rationale: two sibling workers' branch operations can race against the main process's merge-back of a third sibling, and `git`'s own ref locking will not protect all of these cases in a multi-threaded process. Serializing through `GitLock` from a single dispatch point makes ordering deterministic and testable.

Proposed shape:

```python
# Inside worker thread: teardown only, no branch ops
try:
    child_result = child_executor.run(...)
finally:
    worktree_utils.teardown(worktree_path)   # safe to run in worker
return (child_result, worker_branch)

# Main thread, AFTER joining each future (as_completed loop):
for future in as_completed(futures):
    child_result, worker_branch = future.result(...)
    with git_lock:
        if succeeded(child_result):
            merge_coordinator.merge_back(worker_branch)
        else:
            subprocess.run(["git", "branch", "-D", worker_branch], check=False)
```

The `with git_lock:` block is the serialization boundary. Only one branch op per loop run proceeds at a time; no branch op runs concurrently with a merge-back of a sibling. This is the model `MergeCoordinator` was designed for — reuse it rather than introduce a parallel locking scheme.

Cancellation (preserve-for-inspection) is scoped out until ENH-1165 Option A lands.

**Test to add**: `test_worker_fails_sibling_mergeback_still_succeeds` — 3 workers in worktree mode, worker 1 fails (its branch must be `-D`-deleted), workers 0 and 2 succeed. Assert workers 0 and 2 are merged back into the parent branch cleanly even though worker 1's branch was deleted in between. Covers the interleaving of `git branch -D` and `git merge` operations under `GitLock`.

### 2. Documentation

- `docs/generalized-fsm-loop.md` — new "Cleanup contract" subsection under the parallel state docs enumerating the five rules above
- `skills/create-loop/loop-types.md` — add the thread-mode-write warning to the `parallel:` state type entry
- `skills/create-loop/reference.md` — link to the cleanup contract from the `isolation` field reference

### 3. Tests

- `test_worktree_failed_worker_branch_deleted` — simulate a worker failure in worktree mode; assert the worker's branch no longer appears in `git branch -a` after the run
- `test_worktree_successful_worker_branch_merged` — baseline; confirms cleanup path doesn't regress success case
- `test_collect_results_one_entry_per_item_on_partial_failure` — 4 items, 1 fails; assert `len(results) == 4`, `results[3].verdict == "no"`, `results[3].error` is non-empty
- `test_fail_fast_populates_cancelled_slots` — 4 items, item 1 fails with `fail_mode: fail_fast`; assert items 2/3 slots are populated with `terminated_by: "cancelled"` sentinels (not missing)

## Files to Modify

- `scripts/little_loops/fsm/parallel_runner.py` — add branch-delete on failure in worktree mode; ensure cancelled slots get sentinel entries in `fail_fast`
- `docs/generalized-fsm-loop.md` — add "Cleanup contract" subsection
- `skills/create-loop/loop-types.md` — thread-mode-write warning
- `skills/create-loop/reference.md` — link to cleanup contract

## Dependencies

- **Hard blockers**: FEAT-1076 (dispatcher owns the branch-cleanup loop; runs on the main thread under `GitLock` in `as_completed`). FEAT-1075 provides the data the dispatcher needs: `ParallelRunner.run()` returns `(child_result, worker_branch)` per future (FEAT-1075 line 72) — the runner itself performs NO branch operations. *(Note: the previous phrasing of this line said "FEAT-1075 (runner owns the cleanup hook)", which contradicted the Proposed Solution §74–81 — corrected 2026-04-20.)*
- **Interacts with**: ENH-1165 (cancellation — `terminated_by: "cancelled"` branch preservation requires Option A), ENH-1175 (retry — retry-success-then-cleanup ordering)

## Acceptance Criteria

- Worktree mode, failed worker: worktree is torn down AND branch is deleted (`git branch -D`); no orphaned branches after the run
- Worktree mode, successful worker: unchanged behavior (merge-back via `MergeCoordinator`)
- Thread-mode write warning is documented in both `docs/generalized-fsm-loop.md` and `skills/create-loop/loop-types.md`
- `result.all_results` has `len(items)` entries in every terminal state (including `fail_fast`; cancelled slots populated with sentinel `ParallelItemResult`)
- Tests cover: worktree branch deletion on failure; one-entry-per-item on partial failure; fail_fast cancelled-slot sentinels
- `test_worker_fails_sibling_mergeback_still_succeeds` asserts that when one worker fails mid-run in worktree mode, sibling workers' branches merge back cleanly — no race between the failing worker's `git branch -D` and siblings' `git merge`
- Branch operations (merge-back, delete) are serialized through `GitLock` on the main thread; a test asserts branch ops do NOT execute in worker threads (instrument with `threading.get_ident()`)
- **Ownership contract**: the dispatcher (FEAT-1076) owns the branch-cleanup loop and holds `GitLock`; the runner (FEAT-1075) owns worker-thread-local work only (worktree dir teardown, returning `(child_result, worker_branch)` tuples). No code path may issue a `git branch -D`, `git merge`, or any other ref-modifying git command from inside a worker thread. A unit test MUST assert this by wrapping `subprocess.run` or the git helper in a shim that records `threading.get_ident()` and failing the test if any git ref-modification is observed on a non-main thread.

## Impact

- **Priority**: P2 — v1 correctness concern; defines the observable post-failure state of the filesystem and captures, which downstream routing depends on.
- **Effort**: Small-to-Medium — runner changes + documentation + integration tests
- **Risk**: Low-Medium — aggressive branch deletion must not run on successful workers; guard with an explicit verdict check and test the success case
- **Breaking Change**: No — defines behavior that was previously undefined

## Labels

`fsm`, `parallel`, `worktree`, `cleanup`, `contract`

---

## Session Log
- `parallel-fsm-review` - 2026-04-20T00:00:00Z - extracted from ENH-1175 to surface the cleanup contract as a v1 blocker (FEAT-1075/1076 ship companion)

---

**Open** | Created: 2026-04-20 | Priority: P2
