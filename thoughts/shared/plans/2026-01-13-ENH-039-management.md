# ENH-039: EXCLUDED_DIRECTORIES missing `issues/` variant - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-039-excluded-directories-missing-issues-variant.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `EXCLUDED_DIRECTORIES` constant is defined in two files but only includes `.issues/` (with dot prefix), not `issues/` (without dot):

### Key Discoveries
- `scripts/little_loops/git_operations.py:15-21` - EXCLUDED_DIRECTORIES missing `issues/`
- `scripts/little_loops/work_verification.py:18-24` - EXCLUDED_DIRECTORIES missing `issues/`
- `scripts/little_loops/parallel/worker_pool.py:807-808` - **Correctly** handles both variants: `file_path.startswith((".issues/", "issues/"))`
- `scripts/little_loops/parallel/merge_coordinator.py:175-178, 382-385` - **Correctly** handles both variants

## Desired End State

Both `EXCLUDED_DIRECTORIES` tuples include `"issues/"` variant so that projects configured with `issues.base_dir = "issues"` (without dot) work correctly.

### How to Verify
- New test case confirms `"issues/"` is in EXCLUDED_DIRECTORIES
- Existing tests continue to pass
- `filter_excluded_files()` correctly filters files in `issues/` directory

## What We're NOT Doing

- Not refactoring the duplicate EXCLUDED_DIRECTORIES definitions (that's a separate concern)
- Not changing merge_coordinator.py or worker_pool.py (they already handle both correctly)
- Not adding dynamic config-based exclusions (out of scope)

## Problem Analysis

The codebase inconsistently handles issue directory path variants:
- Some files check for both `.issues/` and `issues/` (worker_pool.py, merge_coordinator.py)
- Two files only check for `.issues/` (git_operations.py, work_verification.py)

If `issues.base_dir` is configured as `issues` (without dot):
- Work verification would NOT exclude issue file changes
- Issue files would be incorrectly counted as "meaningful work"
- This could cause false positives when checking if real implementation work was done

## Solution Approach

Simple fix: add `"issues/"` to both `EXCLUDED_DIRECTORIES` tuples, following the established pattern.

## Implementation Phases

### Phase 1: Update EXCLUDED_DIRECTORIES Constants

#### Overview
Add `"issues/"` to EXCLUDED_DIRECTORIES in both git_operations.py and work_verification.py.

#### Changes Required

**File**: `scripts/little_loops/git_operations.py`
**Lines**: 15-21
**Changes**: Add `"issues/"` after `".issues/"`

```python
EXCLUDED_DIRECTORIES = (
    ".issues/",
    "issues/",  # Support non-dotted variant (issues.base_dir = "issues")
    ".speckit/",
    "thoughts/",
    ".worktrees/",
    ".auto-manage",
)
```

**File**: `scripts/little_loops/work_verification.py`
**Lines**: 18-24
**Changes**: Add `"issues/"` after `".issues/"`

```python
EXCLUDED_DIRECTORIES = (
    ".issues/",
    "issues/",  # Support non-dotted variant (issues.base_dir = "issues")
    ".speckit/",
    "thoughts/",
    ".worktrees/",
    ".auto-manage",
)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_work_verification.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Add Test Coverage

#### Overview
Add test cases to verify `"issues/"` variant is included and filtered correctly.

#### Changes Required

**File**: `scripts/tests/test_work_verification.py`
**Changes**: Add two new test methods

In `TestExcludedDirectories` class (after line 29):
```python
def test_excluded_directories_contains_issues_no_dot(self) -> None:
    """EXCLUDED_DIRECTORIES includes issues/ directory (without dot prefix)."""
    assert "issues/" in EXCLUDED_DIRECTORIES
```

In `TestFilterExcludedFiles` class (after line 55):
```python
def test_filters_issues_directory_no_dot(self) -> None:
    """Files in issues/ directory (without dot) are filtered out."""
    files = ["issues/bugs/BUG-001.md", "src/main.py"]
    result = filter_excluded_files(files)
    assert result == ["src/main.py"]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_work_verification.py -v`
- [ ] All new tests pass
- [ ] Lint passes: `ruff check scripts/`

---

## Testing Strategy

### Unit Tests
- Test that `"issues/"` is in EXCLUDED_DIRECTORIES constant
- Test that `filter_excluded_files()` filters files in `issues/` directory

### Integration Tests
- Existing tests verify the filtering logic works end-to-end
- No additional integration tests needed

## References

- Original issue: `.issues/enhancements/P3-ENH-039-excluded-directories-missing-issues-variant.md`
- Related patterns: `scripts/little_loops/parallel/worker_pool.py:807-808`
- Similar implementation: `scripts/little_loops/parallel/merge_coordinator.py:175-178`
