# BUG-018: Merge blocked by lifecycle file conflict - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P1-BUG-018-merge-blocked-lifecycle-file-conflict.md`
- **Type**: bug
- **Priority**: P1
- **Action**: fix

## Current State Analysis

The bug occurs in the interaction between the orchestrator's lifecycle completion and the merge coordinator's stash exclusion logic.

### Key Discoveries
- `orchestrator.py:665-668` - `git mv` stages a rename immediately
- `orchestrator.py:697-704` - Commit may return "nothing to commit" but the rename stays staged
- `merge_coordinator.py:162-166` - Stash exclusion skips lifecycle file moves
- `merge_coordinator.py:725-729` - Merge fails with "local changes would be overwritten"

### Root Cause

1. `_complete_issue_lifecycle_if_needed()` runs `git mv` (stages rename)
2. Then writes updated content to the file
3. Then runs `git add -A` and `git commit`
4. If commit returns "nothing to commit" (e.g., content unchanged), the rename stays staged
5. When the next merge happens, stash exclusion skips the rename
6. Git merge then fails because the staged rename conflicts with the merge

The critical bug is in the "nothing to commit" handling at lines 702-704. The code checks for "nothing to commit" in stdout and treats it as success, but it doesn't account for the fact that the `git mv` is already staged. The commit is failing because there's "nothing to commit" relative to what was already staged - but something IS staged.

Actually, looking more carefully: the issue is that `git add -A` at lines 683-686 should pick up the file changes (the content write at line 680). But if the file content is identical to what was already there, `git add -A` won't create a new entry, and the commit will say "nothing to commit" despite the staged rename from `git mv`.

The fix: When `git mv` succeeds, we need to ensure the commit always happens. The "nothing to commit" check should only apply when `git mv` failed (the fallback path at lines 674-677).

## Desired End State

After the fix:
- Lifecycle file moves are always committed immediately after `git mv` succeeds
- No uncommitted lifecycle file renames can exist to block merges
- The merge coordinator continues to exclude lifecycle moves from stash (no change needed there)

### How to Verify
- Run tests to ensure lifecycle completion commits work correctly
- Manual test with parallel issues to verify no merge blocking

## What We're NOT Doing

- Not changing the stash exclusion logic in merge_coordinator.py - it's correct
- Not changing when lifecycle completion runs - it's correct to run after merge
- Not adding new configuration options

## Problem Analysis

The `git commit` in `_complete_issue_lifecycle_if_needed()` can legitimately return "nothing to commit" in one case:
- When `git mv` failed (line 670) and the fallback path wrote the file manually

But when `git mv` succeeds (line 678), there's always a staged rename that needs committing. The current code incorrectly treats "nothing to commit" as success even when `git mv` succeeded.

The bug is likely triggered when:
1. The worker branch already moved the file to completed/ but the move wasn't included in merge
2. Or the worker's file content is identical to the original
3. The orchestrator's `git mv` succeeds, staging the rename
4. `git add -A` doesn't add anything new (content unchanged)
5. `git commit` says "nothing to commit" (but rename IS staged!)
6. The rename stays staged, blocking next merge

Wait - this analysis is incomplete. Let me reconsider...

Actually, if `git mv` succeeds, it stages a rename. Then `git commit` should see that staged rename and commit it. "Nothing to commit" should NOT happen when there's a staged `git mv`.

Let me look at the code more carefully. At line 680, after `git mv` succeeds, we write the content:
```python
completed_path.write_text(content)
```

This creates a modification on top of the `git mv`. Then `git add -A` stages this modification. Then `git commit` commits both the rename and the content change.

The "nothing to commit" could happen if:
1. The commit somehow doesn't see the staged changes
2. Or there's a race condition

Actually, I see the bug now! The log shows:
```
[13:01:46] Completing lifecycle for ENH-625 (merged but file not moved)
[13:01:47] Git status output: RM .issues/enhancements/P1-ENH-625-*.md -> .issues/completed/P1-ENH-625-*.md
[13:01:47] Merge blocked by local changes despite stash
```

The "RM" prefix in `git status --porcelain` means **R**ename in index, **M**odified in worktree. So:
1. `git mv` succeeded (R - rename staged)
2. Content was written (M - worktree modified)
3. But then something happened before the commit...

I think there's a race condition. The merge coordinator might be checking status/attempting to merge before the orchestrator's commit completes. Let me check the timing...

The orchestrator at line 554-557 loops through merged issues and calls `_complete_issue_lifecycle_if_needed()` for each one. Meanwhile, the merge coordinator runs in a background thread and processes its queue.

The race: After ENH-625 merge succeeds, the orchestrator:
1. Marks ENH-625 completed in queue
2. Calls `_complete_issue_lifecycle_if_needed("ENH-625")`
3. `git mv` runs
4. Content is written
5. `git add -A` runs
6. `git commit` runs

But simultaneously, the merge coordinator might be processing ENH-643's merge from its queue. If the merge for ENH-643 starts between steps 3-6, it will see the uncommitted rename.

However, looking at the code flow, this shouldn't happen because:
- `merge_coordinator.wait_for_completion(timeout=120)` at line 552 should wait for all merges to complete before the loop at 555-557 runs

Let me re-read... Actually, no - `wait_for_completion()` waits for the queue to be empty, but new merges could be queued. Let me look at the parallel flow.

OK, I think I now understand the actual race:

1. Multiple workers complete in parallel
2. Orchestrator processes completed workers, queuing merges for each
3. Merge coordinator processes merges sequentially from its queue
4. When merge for ENH-625 succeeds, `_finalize_merge` is called
5. But the merge coordinator loop continues processing the next item (ENH-643)
6. Meanwhile, orchestrator hasn't run `wait_for_completion()` yet...

Actually, let me look at when `_complete_issue_lifecycle_if_needed` is called:

```python
# Update queue with merge results and complete lifecycle
for issue_id in self.merge_coordinator.merged_ids:
    self.queue.mark_completed(issue_id)
    self._complete_issue_lifecycle_if_needed(issue_id)
```

This runs AFTER `wait_for_completion()`. So by the time lifecycle completion runs, all merges should be done...

Unless `merged_ids` is being read while the merge coordinator is still running? Let me check `merged_ids`:

```python
@property
def merged_ids(self) -> list[str]:
    """List of successfully merged issue IDs."""
    with self._lock:
        return list(self._merged)
```

It's thread-safe, returning a copy. But the issue is that `wait_for_completion()` only checks if the queue is empty. If a merge is IN PROGRESS (not in queue, being processed), it returns True.

```python
def wait_for_completion(self, timeout: float | None = None) -> bool:
    while not self._queue.empty():
        if timeout and (time.time() - start_time) > timeout:
            return False
        time.sleep(0.5)
    return True
```

This doesn't account for the currently-processing merge! So:
1. Queue has ENH-625 and ENH-643
2. Merge coordinator takes ENH-625 from queue (queue now has ENH-643)
3. ENH-625 merge starts processing
4. ENH-643 is taken from queue (queue now empty)
5. `wait_for_completion()` is called, queue is empty, returns True
6. Orchestrator loops through `merged_ids` (only ENH-625 so far)
7. Calls `_complete_issue_lifecycle_if_needed("ENH-625")`
8. Meanwhile, ENH-643 merge is still running
9. Lifecycle completion for ENH-625 does `git mv`, writes content, add, commit
10. ENH-643 merge tries to run, sees the staged rename from ENH-625

Actually wait, that's still not quite right because the lifecycle completion should fully commit before the next iteration...

Let me look at the log timestamps again:
```
[13:01:46] Completing lifecycle for ENH-625 (merged but file not moved)
[13:01:47] Git status output: RM ...
[13:01:47] Merge blocked by local changes despite stash
```

The "Git status output" log is from merge_coordinator._stash_local_changes() at line 528:
```python
if status_result.stdout.strip():
    self.logger.debug(f"Git status output: {status_result.stdout[:500]}")
```

So the timeline is:
- 13:01:46 - Orchestrator starts lifecycle completion for ENH-625
- 13:01:47 - Merge coordinator checking status before ENH-643 merge

The lifecycle completion for ENH-625 must not have completed before ENH-643's merge attempt started. This confirms my earlier hypothesis about the race condition.

But wait, `wait_for_completion()` should have returned before the orchestrator started lifecycle completion. Let me trace more carefully...

The race is between:
- Orchestrator loop calling `_complete_issue_lifecycle_if_needed()`
- Merge coordinator processing its queue

Since they run on different threads, and the lifecycle completion involves multiple git operations, there's a window where:
1. Orchestrator does `git mv` for ENH-625
2. Merge coordinator starts processing ENH-643 (sees ENH-625's uncommitted mv)
3. Orchestrator continues with add/commit for ENH-625

The fix should ensure that lifecycle completion commits are FULLY COMPLETE before any subsequent merges start. There are two approaches:

**Option A**: Fix in merge_coordinator - commit any pending lifecycle file moves before merge
**Option B**: Fix in orchestrator - ensure lifecycle completion finishes before allowing more merges

Option A is cleaner and matches "Option 3" from the issue: "Force commit before merge".

## Solution Approach

Add a method to merge_coordinator that commits any uncommitted lifecycle file moves before attempting a merge. Call this at the start of `_process_merge()`.

This is a minimal, targeted fix that:
1. Doesn't change lifecycle completion timing
2. Doesn't require synchronization between threads
3. Handles the edge case where lifecycle moves are staged but uncommitted

## Implementation Phases

### Phase 1: Add Lifecycle Commit Method

#### Overview
Add `_commit_pending_lifecycle_moves()` method to MergeCoordinator that commits any staged lifecycle file moves.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`
**Changes**: Add new method and call it at start of `_process_merge()`

After line 375 (after `_is_lifecycle_file_move`), add:

```python
def _commit_pending_lifecycle_moves(self) -> bool:
    """Commit any uncommitted lifecycle file moves.

    Lifecycle file moves (issue files moved to completed/) are excluded from
    stashing to prevent stash pop conflicts. However, if they remain uncommitted
    when a merge starts, they will block the merge. This method commits any such
    pending moves before the merge proceeds.

    Returns:
        True if any lifecycle moves were committed or none existed,
        False if commit failed
    """
    # Check for lifecycle file moves in git status
    status_result = self._git_lock.run(
        ["status", "--porcelain"],
        cwd=self.repo_path,
        timeout=30,
    )

    lifecycle_moves = []
    for line in status_result.stdout.splitlines():
        if self._is_lifecycle_file_move(line):
            lifecycle_moves.append(line)

    if not lifecycle_moves:
        return True

    self.logger.info(
        f"Found {len(lifecycle_moves)} uncommitted lifecycle file move(s), committing..."
    )

    # Stage all changes (lifecycle moves should already be staged from git mv,
    # but add -A ensures any associated content changes are included)
    self._git_lock.run(
        ["add", "-A"],
        cwd=self.repo_path,
        timeout=30,
    )

    # Commit the lifecycle moves
    commit_result = self._git_lock.run(
        [
            "commit",
            "-m",
            "chore(issues): commit pending lifecycle file moves\n\n"
            "Auto-committed before merge to prevent conflicts.",
        ],
        cwd=self.repo_path,
        timeout=30,
    )

    if commit_result.returncode != 0:
        if "nothing to commit" in commit_result.stdout.lower():
            # This shouldn't happen since we detected moves, but handle gracefully
            self.logger.debug("No changes to commit despite detecting lifecycle moves")
            return True
        self.logger.error(f"Failed to commit lifecycle moves: {commit_result.stderr}")
        return False

    self.logger.info("Committed pending lifecycle file moves")
    return True
```

In `_process_merge()`, after line 628 (after `_mark_state_file_assume_unchanged()`), add:

```python
# Commit any uncommitted lifecycle file moves before stash/merge
# These are excluded from stash to prevent pop conflicts, so they must
# be committed to avoid blocking the merge
if not self._commit_pending_lifecycle_moves():
    self._handle_failure(request, "Failed to commit pending lifecycle moves")
    return
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Run ll-parallel with multiple issues that trigger lifecycle completion
- [ ] Verify no "Merge blocked by local changes despite stash" errors

---

### Phase 2: Add Unit Tests

#### Overview
Add tests for the new `_commit_pending_lifecycle_moves()` method.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add test cases for the new method

```python
def test_commit_pending_lifecycle_moves_no_moves(
    self, temp_git_repo: Path, mock_config: MagicMock
) -> None:
    """Test that method returns True when no lifecycle moves exist."""
    coordinator = MergeCoordinator(mock_config, MagicMock(), temp_git_repo)
    assert coordinator._commit_pending_lifecycle_moves() is True


def test_commit_pending_lifecycle_moves_commits_staged_move(
    self, temp_git_repo: Path, mock_config: MagicMock
) -> None:
    """Test that staged lifecycle moves are committed."""
    # Setup: create issue file and move it with git mv
    issues_dir = temp_git_repo / ".issues" / "bugs"
    completed_dir = temp_git_repo / ".issues" / "completed"
    issues_dir.mkdir(parents=True)
    completed_dir.mkdir(parents=True)

    issue_file = issues_dir / "P1-BUG-001-test.md"
    issue_file.write_text("Test issue")

    subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add issue"],
        cwd=temp_git_repo,
        check=True,
    )

    # Move file with git mv (stages the rename)
    subprocess.run(
        ["git", "mv", str(issue_file), str(completed_dir / issue_file.name)],
        cwd=temp_git_repo,
        check=True,
    )

    # Verify the rename is staged
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=temp_git_repo,
        capture_output=True,
        text=True,
    )
    assert "R " in status.stdout  # Staged rename

    # Run the method
    coordinator = MergeCoordinator(mock_config, MagicMock(), temp_git_repo)
    result = coordinator._commit_pending_lifecycle_moves()

    assert result is True

    # Verify the rename is now committed
    status_after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=temp_git_repo,
        capture_output=True,
        text=True,
    )
    assert status_after.stdout.strip() == ""  # No uncommitted changes
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] All tests pass: `python -m pytest scripts/tests/`

---

## Testing Strategy

### Unit Tests
- Test `_commit_pending_lifecycle_moves()` with no lifecycle moves
- Test `_commit_pending_lifecycle_moves()` with staged lifecycle move
- Test that the method is called in `_process_merge()` flow

### Integration Tests
- The existing merge coordinator tests should continue to pass
- The fix should not affect normal merge operations

## References

- Original issue: `.issues/bugs/P1-BUG-018-merge-blocked-lifecycle-file-conflict.md`
- Related BUG-008 fix: `merge_coordinator.py:162-166` (stash exclusion logic)
- Lifecycle completion: `orchestrator.py:604-718`
- Stash exclusion: `merge_coordinator.py:122-208`
