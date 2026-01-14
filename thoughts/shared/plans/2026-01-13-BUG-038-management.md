# BUG-038: Leaked file cleanup fails silently for gitignored paths - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-038-leaked-file-causes-cascading-pull-failures.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `_cleanup_leaked_files()` method in `worker_pool.py:771-840` has a silent failure mode when processing gitignored files.

### Key Discoveries
- Leak detection at `worker_pool.py:703-769` works correctly because it uses global `git status --porcelain` (no specific paths)
- Cleanup at `worker_pool.py:791-795` fails because it uses path-specific `git status --porcelain -- <files>` which returns empty for gitignored paths
- When git status returns empty, the loop at lines 800-811 never executes
- Both `tracked_files` and `untracked_files` remain empty (initialized at lines 797-798)
- No cleanup occurs at lines 814-835
- No warning is logged (line 837 only logs when `cleaned > 0`)
- Existing test pattern at `test_worker_pool.py:869-892` shows how to test untracked file cleanup

### Current Code Flow
1. Detection finds leaked file via global status
2. Cleanup calls `git status --porcelain -- <path>` for gitignored path
3. Git returns empty output (gitignored files are excluded from path-specific status)
4. No files added to `tracked_files` or `untracked_files`
5. No cleanup performed, no warning logged
6. File persists, causing cascading pull failures

## Desired End State

When a leaked file is detected but git status returns empty output (gitignored paths):
1. The file should be deleted via direct filesystem operation
2. A log entry should indicate the gitignored file was cleaned up
3. The cleanup count should be incremented appropriately

### How to Verify
- New test case validates gitignored file cleanup
- Existing tests continue to pass
- Cleanup logs show gitignored files being handled

## What We're NOT Doing

- Not modifying stash skip logic in merge_coordinator.py - that logic is intentional for legitimate completed files
- Not changing leak detection logic - it works correctly
- Not adding git index operations for gitignored paths - unnecessary complexity
- Deferring secondary fix (baseline tracking in stash) to separate enhancement

## Problem Analysis

**Root Cause**: `git status --porcelain -- <path>` returns empty output for gitignored paths. The cleanup logic relies solely on this output to categorize files for cleanup. When empty, no cleanup occurs.

**Impact**: Leaked files in gitignored directories persist and cause cascading pull failures during merge operations.

## Solution Approach

Add fallback filesystem deletion for files not reported by git status. After processing git status output, check which leaked files were NOT categorized. For any unaccounted files that exist on disk, delete them directly since:
1. They were detected as leaks (shouldn't be in main repo)
2. Git doesn't track them (likely gitignored)
3. The worktree has the canonical version

## Implementation Phases

### Phase 1: Add Fallback Cleanup Logic

#### Overview
Modify `_cleanup_leaked_files()` to handle gitignored files that git status doesn't report.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Changes**: Add fallback cleanup block after existing tracked/untracked handling

After line 835 (end of untracked file cleanup block), before line 837 (if cleaned > 0), add:

```python
        # Fallback: directly delete files not reported by git status
        # This handles gitignored files that git status --porcelain doesn't show
        accounted_files = set(tracked_files + untracked_files)
        for file_path in leaked_files:
            if file_path not in accounted_files:
                full_path = self.repo_path / file_path
                if full_path.exists():
                    try:
                        full_path.unlink()
                        cleaned += 1
                        self.logger.info(f"Deleted gitignored leaked file: {file_path}")
                    except OSError as e:
                        self.logger.warning(
                            f"Failed to delete gitignored leaked file {file_path}: {e}"
                        )
                else:
                    self.logger.debug(
                        f"Leaked file not found (may have been moved): {file_path}"
                    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Add Test Coverage

#### Overview
Add test case for gitignored file cleanup scenario.

#### Changes Required

**File**: `scripts/tests/test_worker_pool.py`
**Changes**: Add new test method after `test_cleanup_leaked_files_untracked`

```python
    def test_cleanup_leaked_files_gitignored(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_leaked_files() deletes gitignored files not reported by git status."""
        # Create a file that simulates a gitignored leaked file
        gitignored_file = temp_repo_with_config / "issues" / "leaked.md"
        gitignored_file.parent.mkdir(parents=True, exist_ok=True)
        gitignored_file.write_text("leaked content")

        leaked_files = ["issues/leaked.md"]

        def mock_git_run(
            args: list[str], cwd: Path, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["status", "--porcelain"]:
                # Git returns empty for gitignored paths
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
            count = worker_pool._cleanup_leaked_files(leaked_files)

        assert count == 1
        assert not gitignored_file.exists()
```

#### Success Criteria

**Automated Verification**:
- [ ] New test passes: `python -m pytest scripts/tests/test_worker_pool.py::TestWorkerPoolLeakDetection::test_cleanup_leaked_files_gitignored -v`
- [ ] All existing tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Full test suite passes: `python -m pytest scripts/tests/`

---

## Testing Strategy

### Unit Tests
- Test gitignored file cleanup (new test)
- Verify tracked file cleanup still works (existing test)
- Verify untracked file cleanup still works (existing test)
- Verify empty list handling (existing test)

### Edge Cases
- File doesn't exist when cleanup runs (handled by existence check)
- File deletion fails (handled by try/except)
- Mix of tracked, untracked, and gitignored files in same call

## References

- Original issue: `.issues/bugs/P2-BUG-038-leaked-file-causes-cascading-pull-failures.md`
- Cleanup implementation: `scripts/little_loops/parallel/worker_pool.py:771-840`
- Existing test patterns: `scripts/tests/test_worker_pool.py:869-892`
- Related BUG-007 fix: `.issues/completed/P2-BUG-007-worktree-files-leak-to-main-repo.md`
