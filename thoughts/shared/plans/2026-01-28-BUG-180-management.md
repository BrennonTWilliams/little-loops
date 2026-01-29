# BUG-180: Stale worktree base commits cause merge failures - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-180-stale-worktree-base-causes-merge-failures.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The parallel processing system creates worktrees from `main` at time T0 when workers are dispatched. The merge coordinator then does `git pull --rebase origin main` before attempting to merge each worker branch. If `origin/main` has advanced since T0, this pull moves local `main` to T1, causing worker branches (still based on T0) to conflict during merge.

### Key Discoveries
- Worktree creation at `worker_pool.py:426-442` uses `git worktree add -b <branch> <path>` without any pre-sync
- The `git pull --rebase origin main` at `merge_coordinator.py:778-783` advances main during merge
- The conflict handler's rebase at `merge_coordinator.py:981-987` runs in the worktree against `main`, but the worktree's reference to `main` may be stale
- There is no pre-flight sync before orchestrator starts workers at `orchestrator.py:549-551`

## Desired End State

Worker branches merge successfully when their changes don't actually conflict with the content in main, regardless of when main advanced on the remote.

### How to Verify
- Sprint execution succeeds when origin/main advances during execution
- Worker branches are rebased onto latest origin/main before merge coordination
- No "skipped previously applied commit" warnings during merge

## What We're NOT Doing

- Not changing the merge coordinator's pull behavior (it needs to stay synchronized)
- Not implementing automatic conflict resolution (genuine conflicts should still fail)
- Not changing the worktree isolation model
- Not implementing pre-flight sync in orchestrator (adds complexity without solving the actual failure mode)

## Problem Analysis

The root cause is that worker branches are based on T0 but the merge coordinator syncs to T1 before merging. The proposed solution in the issue suggests two parts, but Part 2 (worker-side fetch/rebase before queuing for merge) is the essential fix because:

1. It addresses the actual failure mode: "first merge failed immediately, not due to other workers' changes but due to main advancing during the pull"
2. It fails early in worker context rather than during merge coordination
3. Workers can update their base independently before entering the serialized merge queue

Part 1 (pre-flight sync) is good hygiene but doesn't solve the problem if main advances during sprint execution. I'll implement Part 2 as the primary fix.

## Solution Approach

Add a `_update_branch_base()` method to `WorkerPool` that fetches `origin/main` and rebases the worker branch before returning the result. This ensures each worker's branch is based on the latest main commit before it enters the merge queue.

## Implementation Phases

### Phase 1: Add worker-side base update in WorkerPool

#### Overview
Add a method to fetch origin/main and rebase the worker branch onto it before returning from `_process_issue()`. This ensures the branch is up-to-date with remote main before merge coordination.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`

**Change 1**: Add `_update_branch_base()` method after `_get_changed_files()` (around line 722)

```python
def _update_branch_base(self, worktree_path: Path, issue_id: str) -> tuple[bool, str]:
    """Fetch origin/main and rebase worker branch onto it.

    This ensures the worker branch is based on the latest main before
    merge coordination, preventing conflicts when main advances during
    sprint execution (BUG-180).

    Args:
        worktree_path: Path to the worker's worktree
        issue_id: Issue ID for logging

    Returns:
        Tuple of (success, error_message)
    """
    # Fetch latest main from origin
    fetch_result = subprocess.run(
        ["git", "fetch", "origin", "main"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if fetch_result.returncode != 0:
        return False, f"Failed to fetch origin/main: {fetch_result.stderr}"

    # Rebase current branch onto origin/main
    rebase_result = subprocess.run(
        ["git", "rebase", "origin/main"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if rebase_result.returncode != 0:
        # Abort the failed rebase
        subprocess.run(
            ["git", "rebase", "--abort"],
            cwd=worktree_path,
            capture_output=True,
            timeout=10,
        )
        return False, f"Failed to rebase onto origin/main: {rebase_result.stderr}"

    self.logger.info(f"[{issue_id}] Rebased branch onto origin/main")
    return True, ""
```

**Change 2**: Call `_update_branch_base()` in `_process_issue()` after verification passes but before returning successful result (around line 395)

Insert before the final `return WorkerResult(...)` for success:

```python
            # Step 9: Update branch base before merge (BUG-180)
            # Fetch origin/main and rebase to ensure branch is based on latest main
            base_updated, base_error = self._update_branch_base(worktree_path, issue.issue_id)
            if not base_updated:
                return WorkerResult(
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    changed_files=changed_files,
                    leaked_files=leaked_files,
                    duration=time.time() - start_time,
                    error=base_error,
                    stdout=manage_result.stdout,
                    stderr=manage_result.stderr,
                )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/worker_pool.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/worker_pool.py`

---

### Phase 2: Add unit tests for base update

#### Overview
Add tests for the new `_update_branch_base()` method to verify fetch and rebase behavior.

#### Changes Required

**File**: `scripts/tests/test_worker_pool.py`

Add a new test class for the base update functionality:

```python
class TestUpdateBranchBase:
    """Tests for _update_branch_base method (BUG-180 fix)."""

    def test_successful_fetch_and_rebase(
        self,
        worker_pool: WorkerPool,
        temp_git_repo_with_remote: Path,
    ) -> None:
        """Should successfully fetch and rebase when no conflicts."""
        # Create worktree
        worktree_path = temp_git_repo_with_remote / ".worktrees" / "worker-test"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "test-branch", str(worktree_path)],
            cwd=temp_git_repo_with_remote,
            capture_output=True,
            check=True,
        )

        success, error = worker_pool._update_branch_base(worktree_path, "TEST-001")

        assert success is True
        assert error == ""

    def test_rebase_conflict_aborts_cleanly(
        self,
        worker_pool: WorkerPool,
        temp_git_repo_with_remote: Path,
    ) -> None:
        """Should abort rebase and return error on conflict."""
        # Setup: create conflicting changes on main and worktree
        # ... test implementation
        pass
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v -k "test_update_branch_base or TestUpdateBranchBase"`
- [ ] Full test suite passes: `python -m pytest scripts/tests/ -v`

---

### Phase 3: Update merge coordinator conflict handler

#### Overview
Update the conflict handler to rebase onto `origin/main` instead of `main`, ensuring consistency with the worker-side update.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`

**Change 1**: In `_handle_conflict()`, update the rebase command at line 980-987 to use `origin/main`:

```python
            # Fetch latest main before rebase
            subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=result.worktree_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Rebase the branch onto latest origin/main
            rebase_result = subprocess.run(
                ["git", "rebase", "origin/main"],  # Changed from "main"
                cwd=result.worktree_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/merge_coordinator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/merge_coordinator.py`

---

## Testing Strategy

### Unit Tests
- Test `_update_branch_base()` succeeds with clean fetch/rebase
- Test `_update_branch_base()` fails gracefully and aborts on rebase conflict
- Test `_update_branch_base()` handles fetch failures

### Integration Tests
The fix is best verified through actual sprint execution where main advances during processing. Manual testing would involve:
1. Start a sprint with multiple issues
2. While workers are running, push a commit to origin/main
3. Verify merges succeed without "skipped previously applied commit" warnings

## References

- Original issue: `.issues/bugs/P2-BUG-180-stale-worktree-base-causes-merge-failures.md`
- Worker pool implementation: `scripts/little_loops/parallel/worker_pool.py:209-410`
- Merge coordinator conflict handling: `scripts/little_loops/parallel/merge_coordinator.py:915-1022`
- Similar rebase pattern: `scripts/little_loops/parallel/merge_coordinator.py:981-987`
