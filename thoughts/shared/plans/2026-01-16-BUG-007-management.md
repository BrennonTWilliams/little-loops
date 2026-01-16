# BUG-007: Worktree isolation files leak to main repo - Implementation Plan (Fourth Fix)

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-007-worktree-files-leak-to-main-repo.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The issue has been reopened four times. Previous fixes applied:
1. **First fix**: Copy `.claude/` directory to worktrees + set `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` environment variable
2. **Second fix**: Added environment variable to `_detect_worktree_model_via_api()` function
3. **Third fix**: Added path variant handling for `issues/` (without dot prefix) in detection and cleanup

Despite these fixes, leaks continue to occur. The fourth reopening shows:
- BUG-779 detected ENH-827's issue file as leaked
- ENH-827 also detected its own issue file as leaked
- Both cleanup attempts failed with "Leaked file not found (may have been moved)"
- **Same file was detected twice by two different workers**

### Key Discoveries

1. **Cross-worker false positive detection** (`worker_pool.py:798`): The condition `issue_id_lower in file_lower` matches files containing ANY issue ID, not just the current worker's issue ID
2. **Race condition in cleanup**: When worker A detects worker B's leaked file, cleanup fails because:
   - Worker B may have already cleaned it up
   - The file may have been moved by lifecycle management
3. **Workers run in parallel**: BUG-779 completed at 15:52:30, ENH-827 completed at 15:55:04 - both detected the same file

### Code Analysis

At `worker_pool.py:797-799`:
```python
file_lower = file_path.lower()
if issue_id_lower in file_lower:
    leaked_files.append(file_path)
```

This check is overly broad. When BUG-779 runs detection:
- `issue_id_lower` = "bug-779"
- A file `P2-ENH-827-partial-completion-claim.md` appears in the new files set
- The substring check `"bug-779" in "p2-enh-827-partial-completion-claim.md"` is False
- BUT the file is caught by the fallback `issues/` directory check at line 808

The actual issue: ALL issue directory files are now treated as leaks (from third fix), but this includes files leaked by OTHER workers running in parallel.

## Desired End State

1. Leak detection only attributes files to the worker that actually created them
2. Workers don't interfere with each other's leak detection/cleanup
3. Each worker only cleans up its own leaked files
4. If a worker detects another worker's leak, it should log it but not try to clean it up

### How to Verify
- Run parallel processing with multiple workers
- Each worker should only report and clean up files containing its own issue ID
- Workers should not report "file not found" errors for other workers' leaks

## What We're NOT Doing

- Not removing the `issues/` directory detection (third fix) - it's correct for catching leaks
- Not changing the baseline-delta detection algorithm - it correctly identifies new files
- Not modifying the preventive measures - they work but aren't 100% reliable
- Not adding cross-worker synchronization/locking for cleanup - that's over-engineering

## Problem Analysis

### Root Cause

The leak detection function catches too many files because:

1. **Issue ID match is correct** (line 798): Only catches files with THIS worker's issue ID
2. **Directory-based catch-all is too broad** (lines 801-809): Catches ALL files in `issues/`, `src/`, etc., regardless of which worker created them

The third fix (adding `issues/` directory detection) was correct but created a side effect: now ALL issue files that appear during ANY worker's execution are detected as leaks.

### Why This Causes Problems

1. Worker A and Worker B run in parallel
2. Worker B leaks an issue file to main repo
3. Worker A completes first, runs leak detection
4. Worker A sees Worker B's leaked file in the `issues/` directory
5. Worker A tries to clean it up, but Worker B is still using it or has already moved it
6. Cleanup fails with "file not found"

### Solution

Filter directory-based catches to ONLY include files that likely belong to THIS worker:
- If a file in `issues/` contains an issue ID that is NOT this worker's issue ID, skip it
- This prevents cross-worker contamination while still catching legitimate leaks

## Solution Approach

Refine the leak detection logic to be worker-specific:

1. Keep the primary issue ID match (line 798) - this is correct
2. For directory-based catches (lines 801-809), add a secondary filter:
   - If the file appears to be issue-related (in `issues/` or `.issues/`), only include it if:
     - It contains this worker's issue ID, OR
     - It doesn't contain any recognizable issue ID pattern (e.g., it's a generic file)
   - For source directories (`src/`, `tests/`, etc.), continue catching all files

This approach ensures:
- Direct issue ID matches are always caught
- Issue files from other workers are NOT caught
- Source code leaks from any worker are still caught (safer)

## Implementation Phases

### Phase 1: Refine Issue Directory Detection

#### Overview
Modify `_detect_main_repo_leaks()` to filter issue directory files to only those belonging to the current worker.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Location**: Lines 806-809 in `_detect_main_repo_leaks()`

**Current code**:
```python
            # Catch issue files in any issue directory variant
            # Handles both .issues/ (with dot) and issues/ (without dot)
            elif file_path.startswith((".issues/", "issues/")):
                leaked_files.append(file_path)
```

**New code**:
```python
            # Catch issue files in any issue directory variant
            # Handles both .issues/ (with dot) and issues/ (without dot)
            # Only include if it contains this worker's issue ID or has no recognizable issue ID
            # This prevents cross-worker contamination where worker A detects worker B's leak
            elif file_path.startswith((".issues/", "issues/")):
                # Check if file contains any issue ID pattern (e.g., BUG-123, ENH-456, FEAT-789)
                import re
                issue_id_pattern = re.search(r'(bug|enh|feat)-\d+', file_lower)
                if issue_id_pattern:
                    # Only include if it's THIS worker's issue ID
                    if issue_id_lower in file_lower:
                        leaked_files.append(file_path)
                    # else: skip - belongs to another worker
                else:
                    # No recognizable issue ID - include it (could be generic file)
                    leaked_files.append(file_path)
```

Wait - we can simplify. The issue ID check at line 798 already catches files with this worker's issue ID. The fallback directory checks should only catch files that DON'T have any issue ID pattern (since those with issue IDs are handled by line 798).

**Revised approach**: For issue directories, only catch files that don't match any issue ID pattern (these are generic files that shouldn't be in main repo). Files with issue IDs are already handled by the primary check.

**Simpler new code**:
```python
            # Catch issue files in any issue directory variant
            # Handles both .issues/ (with dot) and issues/ (without dot)
            # Only include files without an issue ID - files WITH issue IDs are caught by
            # the primary check above (or belong to another worker and should be skipped)
            elif file_path.startswith((".issues/", "issues/")):
                # Skip files that have a different issue ID (avoids cross-worker contamination)
                if not self._has_other_issue_id(file_lower, issue_id_lower):
                    leaked_files.append(file_path)
```

We'll need a helper method to check for other issue IDs.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Add Helper Method for Issue ID Detection

#### Overview
Add a method to detect if a file contains a different issue ID than the current worker's.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Location**: Add new method near `_detect_main_repo_leaks()`

```python
    def _has_other_issue_id(self, file_lower: str, current_issue_id_lower: str) -> bool:
        """Check if file contains a different issue ID than the current worker's.

        Args:
            file_lower: Lowercase file path to check
            current_issue_id_lower: Lowercase issue ID of the current worker

        Returns:
            True if the file contains a different issue ID (belongs to another worker),
            False if the file contains the current issue ID or no recognizable issue ID
        """
        import re

        # Pattern matches common issue ID formats: BUG-123, ENH-456, FEAT-789
        matches = re.findall(r'(bug|enh|feat)-\d+', file_lower)

        if not matches:
            # No issue ID found - file doesn't belong to any specific worker
            return False

        # Check if any of the found issue IDs match the current worker
        for match in matches:
            if match == current_issue_id_lower:
                return False  # File belongs to current worker

        # File has issue ID(s) but none match current worker - belongs to another worker
        return True
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 3: Update Tests for Cross-Worker Isolation

#### Overview
Add tests to verify the new cross-worker isolation behavior.

#### Changes Required

**File**: `scripts/tests/test_worker_pool.py`
**Changes**: Add test for cross-worker contamination prevention

```python
def test_detect_main_repo_leaks_ignores_other_workers_issue_files(
    self,
    worker_pool: WorkerPool,
) -> None:
    """_detect_main_repo_leaks() does not detect other workers' issue files."""
    baseline_status: set[str] = set()

    def mock_git_run(
        args: list[str], cwd: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(
                args,
                0,
                # This worker is BUG-001, but ENH-002 file also appears (from another worker)
                "?? .issues/bugs/P1-BUG-001-this-workers-file.md\n"
                "?? issues/enhancements/P2-ENH-002-other-workers-file.md\n",
                "",
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
        leaks = worker_pool._detect_main_repo_leaks("BUG-001", baseline_status)

    # Should detect this worker's file
    assert ".issues/bugs/P1-BUG-001-this-workers-file.md" in leaks
    # Should NOT detect other worker's file
    assert "issues/enhancements/P2-ENH-002-other-workers-file.md" not in leaks


def test_detect_main_repo_leaks_catches_generic_issue_files(
    self,
    worker_pool: WorkerPool,
) -> None:
    """_detect_main_repo_leaks() detects issue files without specific issue IDs."""
    baseline_status: set[str] = set()

    def mock_git_run(
        args: list[str], cwd: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(
                args,
                0,
                # Files without issue IDs should be detected
                "?? .issues/README.md\n"
                "?? issues/template.md\n",
                "",
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    with patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run):
        leaks = worker_pool._detect_main_repo_leaks("BUG-001", baseline_status)

    # Should detect generic files in issue directories
    assert ".issues/README.md" in leaks
    assert "issues/template.md" in leaks
```

**File**: `scripts/tests/test_worker_pool.py`
**Changes**: Add test for helper method

```python
def test_has_other_issue_id(self, worker_pool: WorkerPool) -> None:
    """_has_other_issue_id() correctly identifies files with other issue IDs."""
    # No issue ID in filename
    assert not worker_pool._has_other_issue_id("readme.md", "bug-001")

    # Same issue ID
    assert not worker_pool._has_other_issue_id("p1-bug-001-fix.md", "bug-001")

    # Different issue ID
    assert worker_pool._has_other_issue_id("p2-enh-002-other.md", "bug-001")

    # Different issue type
    assert worker_pool._has_other_issue_id("p1-feat-001-feature.md", "bug-001")

    # Multiple issue IDs, one matches
    assert not worker_pool._has_other_issue_id("bug-001-related-to-enh-002.md", "bug-001")

    # Multiple issue IDs, none match
    assert worker_pool._has_other_issue_id("enh-002-related-to-feat-003.md", "bug-001")
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test `_has_other_issue_id()` with various file patterns
- Test leak detection correctly filters other workers' files
- Test leak detection still catches generic files in issue directories
- Test existing functionality (source files, thoughts files) is preserved

### Integration Tests
- N/A - this fix is contained within existing detection logic

## References

- Original issue: `.issues/bugs/P2-BUG-007-worktree-files-leak-to-main-repo.md`
- Previous plans:
  - `thoughts/shared/plans/2026-01-12-BUG-007-management.md` (second fix)
  - `thoughts/shared/plans/2026-01-13-BUG-007-management.md` (third fix)
- Leak detection: `scripts/little_loops/parallel/worker_pool.py:745-811`
