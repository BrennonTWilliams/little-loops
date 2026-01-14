# BUG-018: Merge blocked by lifecycle file conflict - REOPENED Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P1-BUG-018-merge-blocked-lifecycle-file-conflict.md`
- **Type**: bug
- **Priority**: P1
- **Action**: fix
- **Reopened**: 2026-01-14

## Current State Analysis

The original BUG-018 was about lifecycle file moves causing "local changes would be overwritten" errors. That was fixed by adding `_commit_pending_lifecycle_moves()` to commit pending lifecycle moves before merge.

This reopened issue is about a **different problem**: genuine source code merge conflicts that leave unmerged entries in the git index. When the merge coordinator aborts and retries, it encounters the same conflict again because:

1. The source file has genuine conflicts that require manual resolution
2. The abort and hard reset clears the index but doesn't resolve the conflict
3. When the merge is retried, it hits the same conflict again
4. The retry logic exhausts and the issue fails

### Key Discoveries from Research

**Current flow when merge encounters genuine conflicts:**
1. `_process_merge()` at line 788 attempts merge
2. Merge fails with "CONFLICT" in output (line 830)
3. `_handle_conflict()` is called (line 831)
4. Merge is aborted (line 861-865)
5. Rebase is attempted in worktree (line 901-907)
6. **If rebase also has conflicts**, it's aborted (line 921-926)
7. Issue is marked as failed (line 934-937)

**Alternative flow (from reopened log):**
1. Merge attempt starts
2. Merge encounters genuine content conflict in source file
3. Before `_handle_conflict()` runs, `_check_and_recover_index()` detects dirty state
4. Hard reset clears the index (line 615, 635-639)
5. Merge is retried (line 823-825)
6. Same genuine conflict occurs again
7. Retry exhausted, issue fails (line 826-827)

**The core problem:**
The `_check_and_recover_index()` method is designed to recover from **dirty index state** (leftover unmerged entries from incomplete operations). However, it cannot resolve **genuine source code conflicts** that exist between the branch being merged and main.

When a merge fails with genuine conflicts, the current logic:
1. Aborts the merge (good)
2. Hard resets to clear the index (good for state cleanup)
3. Retries the merge (bad - same conflict will occur again)
4. Exhausts retries and fails (correct outcome, but via confusing path)

**Similar implementations in codebase:**
- Pattern 7 from research: `test_merge_coordinator.py` has tests for conflict handling
- The `_handle_conflict()` method already handles conflicts via rebase retry
- The issue is that "unmerged files in index" error path bypasses `_handle_conflict()`

### Root Cause

The "unmerged files in index" error path at `merge_coordinator.py:817-827` treats all unmerged files as index state problems. However, when the unmerged files are from **genuine merge conflicts** (not leftover state), the retry-after-reset approach doesn't help because:

1. Hard reset clears the conflicted index entries
2. But the source files on the branch still conflict with main
3. The next merge attempt encounters the same conflicts
4. This is not a recoverable error for automated processing

## Desired End State

After the fix:
- Genuine merge conflicts in source code should be detected immediately
- Instead of retrying after reset, they should go through the existing `_handle_conflict()` rebase flow
- If rebase also fails, the issue should fail cleanly without confusing retry attempts
- The log should clearly indicate "genuine merge conflict" vs "index state corruption"

### How to Verify
- Create a branch with changes that genuinely conflict with main
- Attempt merge via merge coordinator
- Verify it goes through rebase retry flow and fails cleanly
- No confusing "recovered from unmerged files" logs when conflict is genuine

## What We're NOT Doing

- Not changing the existing `_handle_conflict()` rebase retry logic
- Not changing the lifecycle file move fix from original BUG-018
- Not adding manual conflict resolution (automated system cannot do this)
- Not changing the circuit breaker or pause logic

## Problem Analysis

**Current problematic code path:**
```python
# Line 817-827 in merge_coordinator.py
if self._is_unmerged_files_error(error_output):
    self.logger.warning(f"Merge blocked by unmerged files in index: {error_output[:200]}")
    # Attempt recovery and retry once
    if request.retry_count < 1 and self._check_and_recover_index():
        request.retry_count += 1
        self.logger.info("Recovered from unmerged files, retrying merge")
        self._queue.put(request)
        return
    raise RuntimeError(f"Merge failed due to unmerged files: {error_output[:200]}")
```

This code assumes "unmerged files" means index state corruption. However, the error "you have unmerged files" can also occur when:

1. A previous incomplete merge left unmerged entries (recoverable) ← current assumption
2. The current merge attempt found conflicts and left unmerged entries (genuine conflict) ← not handled

When case 2 happens, we shouldn't retry after reset - we should let the CONFLICT detection at line 830 handle it via `_handle_conflict()`.

**The fix strategy:**

Option A (Recommended): **Distinguish recoverable vs genuine conflicts before retry**
- Check if unmerged files exist *before* the current merge attempt
- If yes: recover and retry (current behavior, correct for leftover state)
- If no: this is a genuine conflict from current merge, skip retry and go to CONFLICT handling

Option B: **Remove the retry-after-reset logic entirely**
- Always treat unmerged files as conflicts
- Go straight to `_handle_conflict()` rebase flow
- Simpler but may lose recovery for some edge cases

Option C: **Add conflict detection before merge attempt**
- Check if branch-to-merge has conflicts with main before attempting
- Skip merge entirely if conflicts detected
- Requires `git merge --no-commit --no-ff` trial merge or similar

**Recommended: Option A** - Preserves recovery for genuine index corruption while avoiding useless retries for genuine conflicts.

## Solution Approach

Add a check to determine if unmerged files are from **previous** operations (recoverable) or from the **current** merge attempt (genuine conflict).

The key insight: if we detect "unmerged files" error immediately after a merge attempt, those unmerged files are from the **current** merge (genuine conflict). If we detect them at the **start** of `_process_merge()` (before any merge attempt), they're from a **previous** operation (recoverable).

**Implementation:**
1. Move the `_check_and_recover_index()` call that's at line 822 to **only** run at the start of `_process_merge()` (it's already at line 688)
2. Remove the retry-after-reset logic at lines 817-827
3. When merge fails with unmerged files error, treat it as a CONFLICT and call `_handle_conflict()`

This way:
- Index corruption is cleaned up at the start (before merge)
- Genuine conflicts during merge go through the existing rebase retry flow
- No confusing retry-after-reset for genuine conflicts

## Implementation Phases

### Phase 1: Remove Confusing Retry Path

#### Overview
Remove the retry-after-reset logic for "unmerged files" errors and redirect to conflict handling.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`
**Changes**: Modify the error handling in `_process_merge()`

Remove lines 816-827 (the unmerged files error handling block) and replace with redirect to conflict handler:

```python
# Check for merge conflict (including unmerged files from current merge)
# Unmerged files at this point are genuine conflicts, not leftover state
if self._is_unmerged_files_error(error_output) or "CONFLICT" in error_output:
    self._handle_conflict(request)
    return
```

The key change:
- Before: Unmerged files → recover index → retry merge (confusing for genuine conflicts)
- After: Unmerged files → treat as CONFLICT → go through rebase retry flow

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] All tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Create a branch with conflicting changes to main
- [ ] Attempt merge via ll-parallel
- [ ] Verify log shows "Merge conflict" not "Recovered from unmerged files"
- [ ] Verify rebase retry is attempted
- [ ] Verify issue fails cleanly if rebase also conflicts

---

### Phase 2: Update Tests

#### Overview
Update tests to reflect the new error handling behavior.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Update or add tests for unmerged files error handling

The existing test for unmerged files handling should be updated to reflect that it now redirects to conflict handler instead of retry-after-reset.

Add new test to verify that genuine conflicts go through rebase flow:

```python
def test_unmerged_files_from_current_merge_routes_to_conflict_handler(
    self,
    default_config: ParallelConfig,
    mock_logger: MagicMock,
    temp_git_repo: Path,
) -> None:
    """Unmerged files from current merge attempt should route to conflict handler."""
    # Create a branch with conflicting changes
    # ... setup code ...

    # Mock the git commands to simulate conflict
    # ... verification that _handle_conflict is called ...
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] All tests pass: `python -m pytest scripts/tests/`

---

## Testing Strategy

### Unit Tests
- Test that "unmerged files" error routes to `_handle_conflict()`
- Test that pre-existing unmerged files (before merge) are still cleaned up by `_check_and_recover_index()`
- Verify that conflict handler's rebase retry is attempted for genuine conflicts

### Integration Tests
- Create conflicting branch and verify merge fails cleanly through rebase flow
- Verify no confusing "recovered from unmerged files" logs for genuine conflicts
- Verify index corruption is still recovered at merge start

## References

- Original issue: `.issues/bugs/P1-BUG-018-merge-blocked-lifecycle-file-conflict.md`
- Original plan: `thoughts/shared/plans/2026-01-12-BUG-018-management.md`
- Related BUG-008: `.issues/completed/P2-BUG-008-stash-pop-failure-loses-local-changes.md`
- Merge coordinator: `scripts/little_loops/parallel/merge_coordinator.py`
- Test file: `scripts/tests/test_merge_coordinator.py`
- Research findings: Codebase patterns for conflict handling
