# BUG-007: Worktree isolation files leak to main repo - Implementation Plan (Third Fix)

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-007-worktree-files-leak-to-main-repo.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The issue has been reopened three times. Previous fixes applied:
1. **First fix**: Copy `.claude/` directory to worktrees + set `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` environment variable
2. **Second fix**: Added environment variable to `_detect_worktree_model_via_api()` function

Despite these fixes, leaks continue to occur. The third reopening shows:
- ENH-706 leaked to `issues/enhancements/` (no dot prefix)
- ENH-692 leaked to `.issues/enhancements/` (with dot prefix)
- ENH-706 leak was NOT cleaned up, causing cascading pull failures (BUG-038)

### Key Discoveries

1. **Path variation handling gap** (`worker_pool.py:759`): Leak detection only checks hardcoded directories: `backend/`, `src/`, `lib/`, `tests/`
2. **Issue directory not explicitly checked** (`worker_pool.py:754-763`): Issue files are only detected if they contain the issue ID in the filename
3. **Completed directory skip only handles one variation** (`merge_coordinator.py:172-175`): Only checks `.issues/completed/`, not `issues/completed/`
4. **External repo uses `issues/` not `.issues/`**: The blender-agents repo uses a different directory structure

## Desired End State

1. All issue-related directories are detected as potential leaks (with or without dot prefix)
2. Cleanup logic handles all path variations for completed directory
3. The safety net catches all leaks regardless of the preventive measures' effectiveness

### How to Verify
- Leak detection should catch files in `issues/`, `.issues/`, and their subdirectories
- Cleanup should work for `issues/completed/` and `.issues/completed/`
- Tests should cover all path variations

## What We're NOT Doing

- Not investigating why Claude Code still leaks despite project root anchoring - this is an external dependency issue (GitHub #8771)
- Not modifying the preventive measures (`.claude/` copy, environment variable) - they're working as intended
- Not changing the baseline-delta detection algorithm - it's working correctly
- Deferring any changes to how the environment variable is set - the second fix addressed that

## Problem Analysis

### Root Cause
The leak detection and cleanup patterns in `worker_pool.py` and `merge_coordinator.py` are incomplete:

1. **Leak detection** (`worker_pool.py:754-763`) relies on:
   - Issue ID appearing in filename (works for most cases)
   - Hardcoded source directories (doesn't include issue directories)
   - `thoughts/` prefix (works)

2. **Missing patterns**:
   - `issues/` directory (no dot prefix) - used by external repositories
   - `.issues/` directory (with dot prefix) - used by little-loops
   - All subdirectories: `bugs/`, `features/`, `enhancements/`, `completed/`

3. **Completed directory skip** (`merge_coordinator.py:172-175`) only handles `.issues/completed/`, missing `issues/completed/`

### Why ENH-706 Wasn't Cleaned
1. Leaked file: `issues/enhancements/P1-ENH-706-...`
2. Detection DID work (issue ID was in filename)
3. Cleanup DID work (file was deleted)
4. BUT: During continued processing, the issue was moved to completed
5. New leak created at `.issues/completed/P1-ENH-706-...`
6. This happened AFTER leak detection ran
7. Merge coordinator's stash logic skipped `.issues/completed/` files
8. Unstaged change persisted indefinitely

## Solution Approach

Expand the pattern coverage in two locations:

1. **Leak detection** (`worker_pool.py`): Add explicit checks for issue directories with and without dot prefix
2. **Lifecycle file move detection** (`merge_coordinator.py`): Add check for `issues/completed/` (no dot)

This is a minimal, targeted fix that addresses the specific gap identified in the logs.

## Implementation Phases

### Phase 1: Expand Leak Detection Patterns

#### Overview
Add explicit checks for issue directories in the leak detection function.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Location**: Lines 754-763 in `_detect_main_repo_leaks()`

**Current code**:
```python
        # Check if file is related to this issue
        file_lower = file_path.lower()
        if issue_id_lower in file_lower:
            leaked_files.append(file_path)
        # Also catch source files that shouldn't be modified in main
        elif file_path.startswith(("backend/", "src/", "lib/", "tests/")):
            leaked_files.append(file_path)
        # Catch thoughts/plans files
        elif file_path.startswith("thoughts/"):
            leaked_files.append(file_path)
```

**New code**:
```python
        # Check if file is related to this issue
        file_lower = file_path.lower()
        if issue_id_lower in file_lower:
            leaked_files.append(file_path)
        # Also catch source files that shouldn't be modified in main
        elif file_path.startswith(("backend/", "src/", "lib/", "tests/")):
            leaked_files.append(file_path)
        # Catch thoughts/plans files
        elif file_path.startswith("thoughts/"):
            leaked_files.append(file_path)
        # Catch issue files in any issue directory variant
        elif file_path.startswith((".issues/", "issues/")):
            leaked_files.append(file_path)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Expand Completed Directory Skip Logic

#### Overview
Add check for `issues/completed/` (without dot) in the lifecycle file move detection.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`
**Location**: Lines 172-175 (completed directory skip in stash logic)

**Current code**:
```python
            # Skip files in completed directory - these are lifecycle-managed
            if ".issues/completed/" in file_path or file_path.startswith(".issues/completed/"):
                self.logger.debug(f"Skipping completed directory file from stash: {file_path}")
                continue
```

**New code**:
```python
            # Skip files in completed directory - these are lifecycle-managed
            # Handle both .issues/completed/ (with dot) and issues/completed/ (without dot)
            if (
                ".issues/completed/" in file_path
                or file_path.startswith(".issues/completed/")
                or "issues/completed/" in file_path
                or file_path.startswith("issues/completed/")
            ):
                self.logger.debug(f"Skipping completed directory file from stash: {file_path}")
                continue
```

**Location**: Lines 372-374 in `_is_lifecycle_file_move()`

**Current code**:
```python
    # Check if destination is in .issues/completed/
    return ".issues/completed/" in dest_path or dest_path.startswith(".issues/completed/")
```

**New code**:
```python
    # Check if destination is in completed directory (with or without dot prefix)
    return (
        ".issues/completed/" in dest_path
        or dest_path.startswith(".issues/completed/")
        or "issues/completed/" in dest_path
        or dest_path.startswith("issues/completed/")
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 3: Add Tests for Path Variations

#### Overview
Add tests to ensure both path variations are handled correctly.

#### Changes Required

**File**: `scripts/tests/test_worker_pool.py`
**Changes**: Add test for issue directory detection

```python
def test_detect_main_repo_leaks_finds_issue_files(
    self,
    worker_pool: WorkerPool,
) -> None:
    """_detect_main_repo_leaks() identifies issue files in both directory variants."""
    baseline_status: set[str] = set()

    def mock_git_run(
        args: list[str], cwd: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(
                args,
                0,
                # Test both .issues/ and issues/ variants
                "?? .issues/bugs/P1-OTHER-001.md\n?? issues/enhancements/P2-ANOTHER-002.md\n",
                "",
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
        leaks = worker_pool._detect_main_repo_leaks("UNRELATED-999", baseline_status)

    # Both should be detected even without matching issue ID
    assert ".issues/bugs/P1-OTHER-001.md" in leaks
    assert "issues/enhancements/P2-ANOTHER-002.md" in leaks
```

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add test for completed directory skip with both variants

```python
def test_is_lifecycle_file_move_handles_path_variants(
    self,
    merge_coordinator: MergeCoordinator,
) -> None:
    """_is_lifecycle_file_move() handles both .issues/ and issues/ variants."""
    # With dot prefix
    assert merge_coordinator._is_lifecycle_file_move(
        "R  .issues/bugs/P1-BUG-001.md -> .issues/completed/P1-BUG-001.md"
    )
    # Without dot prefix
    assert merge_coordinator._is_lifecycle_file_move(
        "R  issues/bugs/P1-BUG-001.md -> issues/completed/P1-BUG-001.md"
    )
    # Non-lifecycle move
    assert not merge_coordinator._is_lifecycle_file_move(
        "R  src/old.py -> src/new.py"
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test leak detection with `.issues/` paths
- Test leak detection with `issues/` paths (no dot)
- Test lifecycle file move detection with both variants
- Test completed directory skip with both variants

### Integration Tests
- N/A - this fix is contained within existing detection and cleanup logic

## References

- Original issue: `.issues/bugs/P2-BUG-007-worktree-files-leak-to-main-repo.md`
- Related issue: `.issues/bugs/P2-BUG-038-leaked-file-causes-cascading-pull-failures.md`
- Previous plan: `thoughts/shared/plans/2026-01-12-BUG-007-management.md`
- Leak detection: `scripts/little_loops/parallel/worker_pool.py:703-765`
- Lifecycle file move: `scripts/little_loops/parallel/merge_coordinator.py:350-376`
- Completed skip: `scripts/little_loops/parallel/merge_coordinator.py:172-175`
