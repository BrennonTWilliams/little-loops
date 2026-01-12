# BUG-008: Merge coordination stash pop failure (Reopened) - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-008-stash-pop-failure-loses-local-changes.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix
- **Status**: Reopened on 2026-01-11

## Current State Analysis

### Previous Fix (2026-01-09)
The previous fix added **visibility/tracking** for stash pop failures:
- `_stash_pop_failures` dict tracks which issues had stash pop failures (`merge_coordinator.py:73`)
- `_current_issue_id` tracks current issue for attribution (`merge_coordinator.py:74-76`)
- Failures are recorded in `_pop_stash()` (`merge_coordinator.py:254-260`)
- `stash_pop_failures` property exposes failures (`merge_coordinator.py:973-981`)
- Orchestrator reports warnings in final summary (`orchestrator.py:591-602`)

### Why It's Still Failing
The stash mechanism itself still fails when:

1. **Renamed files cause conflicts** (`merge_coordinator.py:159-161`)
   - Issue files moved to `completed/` create `R  old -> new` entries
   - Stash stores destination path, but merge may change that file
   - Pop conflicts because HEAD changed

2. **Re-stash creates duplicate entries** (`merge_coordinator.py:647-654`)
   - Pull failure with local changes triggers `_stash_local_changes()` again
   - Creates second stash entry for same files
   - Pop only handles first stash, leaving second orphaned

3. **Stash created against old HEAD** (`merge_coordinator.py:588`)
   - Stash is created before checkout/pull/merge
   - Merge changes HEAD to new commit
   - Stash pop tries to apply old changes to new HEAD = conflict

### Key Evidence from Logs
```
[22:54:00] Tracked files to stash: ['R  .issues/enhancements/P2-ENH-618-... -> .issues/completed/P2-ENH-618-...']
[22:54:01] Re-stashed local changes after pull conflict
[22:54:01] Failed to pop stash:
[22:54:01] Cleaned up conflicted stash pop, merge preserved
```

## Desired End State

When local changes exist during merge:
1. Changes are preserved through the merge without requiring manual recovery
2. Known safe patterns (issue file moves) are handled automatically
3. No stash pop failures occur for orchestrator-managed files
4. User's actual local changes (non-orchestrator files) are still properly stashed/restored

### How to Verify
- Run ll-parallel with lifecycle completion (file moves to completed/)
- Verify no stash pop failure warnings appear
- Verify issue files are correctly in completed/ after run
- Run tests to ensure no regressions

## What We're NOT Doing

- Not abandoning stash mechanism entirely (still needed for actual user changes)
- Not committing orchestrator changes automatically (would create noise commits)
- Not making complex merge strategies (keep it simple)
- Not changing how user's non-orchestrator changes are handled

## Problem Analysis

### Root Cause
The orchestrator moves issue files to `completed/` **after merge succeeds** but **before stash pop**. This creates a race condition:

1. Merge coordinator stashes the orchestrator's file moves (line 588)
2. Merge succeeds, changes HEAD
3. Stash pop tries to restore file moves but conflicts with new HEAD

The file moves are **orchestrator-managed**, not user changes. They shouldn't be stashed at all.

### Key Insight
Issue file moves matching `.issues/**/P*-*.md -> .issues/completed/P*-*.md` are orchestrator-managed lifecycle transitions. These should be **excluded from stashing** just like the state file.

## Solution Approach

**Exclude orchestrator lifecycle file moves from stashing**

The state file is already excluded (`merge_coordinator.py:162-163`). We extend this pattern to also exclude:
- Issue files being moved to completed/ (rename entries `R  old -> new`)
- Files in the `.issues/completed/` directory (newly created there)

This is a targeted, minimal change that solves the specific problem without changing the overall stash/pop architecture.

## Implementation Phases

### Phase 1: Exclude Lifecycle File Moves from Stashing

#### Overview
Modify `_stash_local_changes()` to skip issue file rename operations that represent lifecycle completion (moves to `completed/`).

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`

1. Add helper method to detect lifecycle file moves (after line 348):
```python
def _is_lifecycle_file_move(self, porcelain_line: str) -> bool:
    """Check if a porcelain status line represents a lifecycle file move.

    Lifecycle file moves are issue files being moved to completed/ directory.
    These are managed by the orchestrator and should not be stashed, as they
    will conflict with the merge when popping.

    Args:
        porcelain_line: A line from `git status --porcelain` output

    Returns:
        True if this is a lifecycle file move that should be excluded from stash
    """
    # Rename entries have format: R  old_path -> new_path
    if not porcelain_line.startswith("R"):
        return False

    # Check if it's a move to completed/ directory
    if " -> " not in porcelain_line:
        return False

    # Extract destination path (after " -> ")
    parts = porcelain_line[3:].split(" -> ")
    if len(parts) != 2:
        return False

    dest_path = parts[1].strip()

    # Check if destination is in .issues/completed/
    return ".issues/completed/" in dest_path or dest_path.startswith(".issues/completed/")
```

2. Update `_stash_local_changes()` to skip lifecycle moves (modify lines 156-165):

Change from:
```python
for line in status_result.stdout.splitlines():
    if not line or line.startswith("??"):
        continue
    # Extract file path from porcelain format (XY filename or XY -> filename for renames)
    # Format: XY filename  or  XY old -> new (XY is exactly 2 chars + 1 space)
    file_path = line[3:].split(" -> ")[-1].strip()
    if file_path == state_file_str or file_path.endswith(state_file_name):
        continue  # Skip state file - orchestrator manages it independently
    tracked_changes.append(line)
    files_to_stash.append(file_path)
```

To:
```python
for line in status_result.stdout.splitlines():
    if not line or line.startswith("??"):
        continue
    # Skip lifecycle file moves (issue files moved to completed/)
    # These are managed by orchestrator and cause stash pop conflicts
    if self._is_lifecycle_file_move(line):
        self.logger.debug(f"Skipping lifecycle file move from stash: {line}")
        continue
    # Extract file path from porcelain format (XY filename or XY -> filename for renames)
    # Format: XY filename  or  XY old -> new (XY is exactly 2 chars + 1 space)
    file_path = line[3:].split(" -> ")[-1].strip()
    if file_path == state_file_str or file_path.endswith(state_file_name):
        continue  # Skip state file - orchestrator manages it independently
    tracked_changes.append(line)
    files_to_stash.append(file_path)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/merge_coordinator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/merge_coordinator.py`

**Manual Verification**:
- [ ] Run ll-parallel with an issue that completes lifecycle
- [ ] Verify no stash pop failure warnings

---

### Phase 2: Handle Completed Directory Files

#### Overview
Also exclude files already in `.issues/completed/` from stashing. These are completed issue files that shouldn't be stashed.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`

Update `_stash_local_changes()` file exclusion logic (in the for loop):

```python
for line in status_result.stdout.splitlines():
    if not line or line.startswith("??"):
        continue
    # Skip lifecycle file moves (issue files moved to completed/)
    # These are managed by orchestrator and cause stash pop conflicts
    if self._is_lifecycle_file_move(line):
        self.logger.debug(f"Skipping lifecycle file move from stash: {line}")
        continue
    # Extract file path from porcelain format (XY filename or XY -> filename for renames)
    # Format: XY filename  or  XY old -> new (XY is exactly 2 chars + 1 space)
    file_path = line[3:].split(" -> ")[-1].strip()
    if file_path == state_file_str or file_path.endswith(state_file_name):
        continue  # Skip state file - orchestrator manages it independently
    # Skip files in completed directory - these are lifecycle-managed
    if ".issues/completed/" in file_path or file_path.startswith(".issues/completed/"):
        self.logger.debug(f"Skipping completed directory file from stash: {file_path}")
        continue
    tracked_changes.append(line)
    files_to_stash.append(file_path)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/merge_coordinator.py`

---

### Phase 3: Add Unit Tests

#### Overview
Add tests to verify lifecycle file moves are correctly excluded from stashing.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`

Add new test class after `TestStashPopFailureTracking`:

```python
class TestLifecycleFileMoveExclusion:
    """Tests for excluding lifecycle file moves from stashing."""

    def test_is_lifecycle_file_move_detects_rename_to_completed(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should detect rename entries moving files to completed directory."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Rename to completed should be detected
        assert coordinator._is_lifecycle_file_move(
            "R  .issues/bugs/P1-BUG-001.md -> .issues/completed/P1-BUG-001.md"
        )
        assert coordinator._is_lifecycle_file_move(
            "R  .issues/enhancements/P2-ENH-123.md -> .issues/completed/P2-ENH-123.md"
        )

    def test_is_lifecycle_file_move_ignores_other_renames(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not detect renames to other directories."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Rename to other directory should not be detected
        assert not coordinator._is_lifecycle_file_move(
            "R  src/old.py -> src/new.py"
        )
        assert not coordinator._is_lifecycle_file_move(
            "R  .issues/bugs/P1-BUG-001.md -> .issues/bugs/P1-BUG-001-renamed.md"
        )

    def test_is_lifecycle_file_move_ignores_non_renames(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should not detect non-rename entries."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Modified files should not be detected
        assert not coordinator._is_lifecycle_file_move("M  .issues/completed/P1-BUG-001.md")
        assert not coordinator._is_lifecycle_file_move("A  .issues/completed/P1-BUG-001.md")

    def test_stash_excludes_lifecycle_file_moves(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Stash should exclude lifecycle file moves from being stashed."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create an issue file and commit it
        issues_dir = temp_git_repo / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_file = issues_dir / "P1-BUG-TEST.md"
        issue_file.write_text("# Test issue")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add issue"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Create completed directory and move the file (simulating lifecycle completion)
        completed_dir = temp_git_repo / ".issues" / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "mv", str(issue_file), str(completed_dir / "P1-BUG-TEST.md")],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Also create a regular change that should be stashed
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified content")

        # Stash should succeed
        result = coordinator._stash_local_changes()

        # If there was a regular change to stash, result is True
        # The lifecycle file move should NOT be stashed
        # Verify by checking stash - if pop succeeds without the rename, it worked
        if result:
            coordinator._pop_stash()
            # After pop, test.txt should be restored to modified
            assert test_file.read_text() == "modified content"
            # The git mv should still be staged (not stashed)
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=temp_git_repo,
                capture_output=True,
                text=True,
            )
            # Should still have the rename entry
            assert "R  " in status.stdout or "-> " in status.stdout
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestLifecycleFileMoveExclusion -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/tests/test_merge_coordinator.py`

---

### Phase 4: Update Documentation

#### Overview
Update the docstring for `_stash_local_changes()` to reflect the new exclusions.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`

Update docstring for `_stash_local_changes()`:

```python
def _stash_local_changes(self) -> bool:
    """Stash any uncommitted tracked changes in the main repo.

    Only stashes tracked file modifications. Untracked files are not stashed
    because git stash pathspec exclusions don't work reliably with -u flag.
    Untracked file conflicts during merge are handled by _handle_untracked_conflict.

    The following are explicitly excluded from stashing:
    1. State file - managed by orchestrator and continuously updated
    2. Lifecycle file moves - issue files being moved to completed/ directory
    3. Files in completed directory - lifecycle-managed files

    These exclusions prevent stash pop conflicts after merge, since the merge
    may change HEAD and create conflicts with stashed rename operations.

    Returns:
        True if changes were stashed, False if working tree was clean
    """
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/merge_coordinator.py`

---

## Testing Strategy

### Unit Tests
- Test `_is_lifecycle_file_move()` detection logic
- Test that lifecycle moves are excluded from stash
- Test that regular changes are still stashed correctly
- Test edge cases (partial matches, different paths)

### Integration Tests
- Existing stash/pop tests continue to pass
- New tests verify lifecycle exclusion

## References

- Original issue: `.issues/bugs/P2-BUG-008-stash-pop-failure-loses-local-changes.md`
- Previous plan: `thoughts/shared/plans/2026-01-09-BUG-008-management.md`
- Merge coordinator: `scripts/little_loops/parallel/merge_coordinator.py:122-270`
- State file exclusion pattern: `scripts/little_loops/parallel/merge_coordinator.py:162-163`
