# P2-BUG-051: Issue lifecycle: git mv fails when source not under version control - Implementation Plan

## Issue Reference
- **File**: `/Users/brennon/AIProjects/brenentech/little-loops/.issues/bugs/P2-BUG-051-git-mv-fails-source-not-versioned.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `_move_issue_to_completed()` function in `scripts/little_loops/issue_lifecycle.py:119-161` attempts to move issue files to the `completed/` directory using `git mv`. However, when issue files are not under git version control (e.g., newly created files that haven't been `git add`ed yet), the `git mv` command fails with "fatal: not under version control".

### Key Discoveries

1. **Missing Pre-Check**: The function checks if destination exists (BUG-009 fix at line 137) but does NOT check if source is under git version control before attempting `git mv` (line 144-148).

2. **Issue File Creation**: Issue files are created with `write_text()` but are NOT immediately added to git. The `git add` happens later (batch operation at end of scan_codebase, or manually by user).

3. **Pattern Exists**: The codebase already uses `git ls-files` to check if file is tracked at `merge_coordinator.py:304-313`:
   ```python
   ls_files = self._git_lock.run(
       ["ls-files", state_file],
       cwd=self.repo_path,
       timeout=10,
   )
   if not ls_files.stdout.strip():
       # File not tracked, nothing to do
       return True
   ```

4. **Fallback Works**: When `git mv` fails, the function falls back to manual copy+delete (line 153-155), which works correctly. The issue is that we're attempting `git mv` unnecessarily when the source is not tracked.

5. **Inconsistent Handling**:
   - `ll-auto` skips `close_issue()` for `invalid_ref` at `issue_manager.py:493`
   - `ll-parallel` calls `close_issue()` for all close reasons at `orchestrator.py:480`

## Desired End State

The `_move_issue_to_completed()` function should:
1. Check if the source file is under git version control before attempting `git mv`
2. If source is tracked, use `git mv` for history preservation
3. If source is NOT tracked, use manual copy+delete directly (skip `git mv` attempt)
4. Log appropriately based on the path taken

### How to Verify
- Run existing tests in `scripts/tests/test_issue_lifecycle.py`
- Create new test for untracked source file scenario
- Manual test: Create an untracked issue file and run close_issue to verify clean execution

## What We're NOT Doing

- Not changing the fallback behavior (manual copy+delete works fine)
- Not adding `git add` before `git mv` (would commit files that user may not want tracked)
- Not refactoring the close_issue flow (deferred to separate issue)
- Not changing the inconsistent handling between ll-auto and ll-parallel (deferred to separate issue)

## Problem Analysis

**Root Cause**: The `_move_issue_to_completed()` function assumes source file is under git version control and attempts `git mv` without checking first. When source is not tracked, `git mv` fails with "fatal: not under version control", and the function falls back to manual copy+delete. While this works functionally, it produces unnecessary error logs and is inefficient.

**Why Issue Files Are Untracked**:
- Issue files are created with `Path.write_text()` in scan_codebase command
- The `git add` happens as a batch operation at the end of scan
- During parallel processing, issue files may be processed before the batch `git add`

## Solution Approach

Add a pre-check using `git ls-files` to determine if the source file is under git version control. If the source is not tracked, skip the `git mv` attempt and go directly to manual copy+delete.

This follows the existing pattern in `merge_coordinator.py:304-313`.

## Implementation Phases

### Phase 1: Add Source Tracking Check

#### Overview
Add a helper function to check if a file is under git version control, then use it in `_move_issue_to_completed()` to decide whether to attempt `git mv` or use manual copy+delete directly.

#### Changes Required

**File**: `scripts/little_loops/issue_lifecycle.py`

**Add new helper function** after line 118 (before `_cleanup_stale_source`):

```python
def _is_git_tracked(file_path: Path) -> bool:
    """Check if a file is under git version control.

    Args:
        file_path: Path to the file to check

    Returns:
        True if file is tracked by git, False otherwise
    """
    result = subprocess.run(
        ["git", "ls-files", str(file_path)],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())
```

**Modify `_move_issue_to_completed()`** function (lines 119-161):

```python
def _move_issue_to_completed(
    original_path: Path,
    completed_path: Path,
    content: str,
    logger: Logger,
) -> bool:
    """Move issue file to completed dir, preferring git mv for history.

    Args:
        original_path: Source path of issue file
        completed_path: Destination path in completed directory
        content: Updated file content to write
        logger: Logger for output

    Returns:
        True if move succeeded
    """
    # Handle pre-existing destination (e.g., from parallel worker or worktree leak)
    if completed_path.exists():
        logger.info(f"Destination already exists: {completed_path.name}, updating content")
        completed_path.write_text(content)
        if original_path.exists():
            original_path.unlink()
        return True

    # Check if source is under git version control before attempting git mv
    source_tracked = _is_git_tracked(original_path)

    if source_tracked:
        # Source is tracked, use git mv for history preservation
        result = subprocess.run(
            ["git", "mv", str(original_path), str(completed_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # git mv failed, fall back to manual copy + delete
            logger.warning(f"git mv failed: {result.stderr}")
            completed_path.write_text(content)
            if original_path.exists():
                original_path.unlink()
        else:
            logger.success(f"Used git mv to move {original_path.stem}")
            # Write updated content to the moved file
            completed_path.write_text(content)
    else:
        # Source is not tracked, use manual copy + delete directly
        logger.info(f"Source not tracked by git, using manual copy: {original_path.name}")
        completed_path.write_text(content)
        if original_path.exists():
            original_path.unlink()

    return True
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_lifecycle.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_lifecycle.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_lifecycle.py`

**Manual Verification**:
- [ ] Create an untracked issue file and verify it moves without error logs
- [ ] Create a tracked issue file and verify git mv is used

---

### Phase 2: Add Tests for Untracked Source Scenario

#### Overview
Add test cases to verify the behavior when source file is not under git version control.

#### Changes Required

**File**: `scripts/tests/test_issue_lifecycle.py`

**Add test after line 313** (after `test_git_mv_fallback`):

```python
def test_untracked_source_skips_git_mv(
    self, tmp_path: Path, mock_logger: MagicMock
) -> None:
    """Test that untracked source files use manual copy without attempting git mv."""
    original = tmp_path / "bugs" / "issue.md"
    completed = tmp_path / "completed" / "issue.md"
    original.parent.mkdir(parents=True, exist_ok=True)
    completed.parent.mkdir(parents=True, exist_ok=True)
    original.write_text("Original content")

    content = "Updated content with resolution"

    git_mv_attempted = False

    def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal git_mv_attempted
        if "git" in cmd and "mv" in cmd:
            git_mv_attempted = True
            # Simulate git mv failure for untracked file
            return subprocess.CompletedProcess(
                cmd, 1, stdout="", stderr="fatal: not under version control"
            )
        if "git" in cmd and "ls-files" in cmd:
            # Simulate file not being tracked
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=mock_run):
        result = _move_issue_to_completed(original, completed, content, mock_logger)

    assert result is True
    assert completed.exists()
    assert completed.read_text() == content
    assert not original.exists()
    # With the fix, git mv should NOT be attempted when source is not tracked
    assert not git_mv_attempted
    mock_logger.info.assert_called()
```

**Add test for tracked source** (to ensure git mv is still used when appropriate):

```python
def test_tracked_source_uses_git_mv(
    self, tmp_path: Path, mock_logger: MagicMock
) -> None:
    """Test that tracked source files use git mv for history preservation."""
    original = tmp_path / "bugs" / "issue.md"
    completed = tmp_path / "completed" / "issue.md"
    original.parent.mkdir(parents=True, exist_ok=True)
    completed.parent.mkdir(parents=True, exist_ok=True)
    original.write_text("Original content")

    content = "Updated content with resolution"

    git_mv_attempted = False

    def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal git_mv_attempted
        if "git" in cmd and "mv" in cmd:
            git_mv_attempted = True
            # Simulate successful git mv
            original.rename(completed)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "git" in cmd and "ls-files" in cmd:
            # Simulate file being tracked
            return subprocess.CompletedProcess(cmd, 0, stdout=str(original), stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=mock_run):
        result = _move_issue_to_completed(original, completed, content, mock_logger)

    assert result is True
    assert completed.exists()
    assert completed.read_text() == content
    # With the fix, git mv SHOULD be attempted when source is tracked
    assert git_mv_attempted
    mock_logger.success.assert_called()
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_issue_lifecycle.py::TestMoveIssueToCompleted::test_untracked_source_skips_git_mv -v`
- [ ] New tests pass: `python -m pytest scripts/tests/test_issue_lifecycle.py::TestMoveIssueToCompleted::test_tracked_source_uses_git_mv -v`
- [ ] All existing tests still pass: `python -m pytest scripts/tests/test_issue_lifecycle.py -v`

**Manual Verification**:
- [ ] Review test coverage to ensure both paths (tracked/untracked) are tested

---

### Phase 3: Verify and Document

#### Overview
Run all verification commands and update documentation if needed.

#### Changes Required

**Run verification commands**:
```bash
# Run all issue lifecycle tests
python -m pytest scripts/tests/test_issue_lifecycle.py -v

# Run full test suite
python -m pytest scripts/tests/

# Lint the changed file
ruff check scripts/little_loops/issue_lifecycle.py

# Type check the changed file
python -m mypy scripts/little_loops/issue_lifecycle.py
```

**Update docstring** for `_move_issue_to_completed()` to reflect new behavior:

```python
def _move_issue_to_completed(
    original_path: Path,
    completed_path: Path,
    content: str,
    logger: Logger,
) -> bool:
    """Move issue file to completed dir, preferring git mv for history.

    Checks if source is under git version control before attempting git mv.
    If source is tracked, uses git mv for history preservation.
    If source is not tracked, uses manual copy + delete directly.

    Args:
        original_path: Source path of issue file
        completed_path: Destination path in completed directory
        content: Updated file content to write
        logger: Logger for output

    Returns:
        True if move succeeded
    """
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Docstring accurately describes the new behavior
- [ ] No new warnings or errors in test output

---

## Testing Strategy

### Unit Tests
- Test `_is_git_tracked()` helper function with tracked and untracked files
- Test `_move_issue_to_completed()` with untracked source (git mv not attempted)
- Test `_move_issue_to_completed()` with tracked source (git mv attempted)
- Test `_move_issue_to_completed()` with pre-existing destination
- Test `_move_issue_to_completed()` with git mv failure (fallback still works)

### Integration Tests
- Existing tests in `test_issue_lifecycle.py` cover the full close_issue flow
- No new integration tests needed (behavior unchanged from user perspective)

## References

- Original issue: `.issues/bugs/P2-BUG-051-git-mv-fails-source-not-versioned.md`
- Primary file: `scripts/little_loops/issue_lifecycle.py:119-161`
- Test file: `scripts/tests/test_issue_lifecycle.py:265-345`
- Similar pattern: `scripts/little_loops/parallel/merge_coordinator.py:304-313`
- Related bug: `.issues/completed/P1-BUG-009-git-mv-fails-destination-exists.md`
