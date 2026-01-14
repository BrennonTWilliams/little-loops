# ENH-039: EXCLUDED_DIRECTORIES missing `issues/` variant

## Summary

The `EXCLUDED_DIRECTORIES` constant in `git_operations.py` and `work_verification.py` only includes `.issues/` but not `issues/` (without dot). This is inconsistent with other parts of the codebase that correctly handle both variants.

## Problem

The codebase has inconsistent pattern handling for issue directory paths:

### Files that correctly handle BOTH variants:
- `worker_pool.py:807-808` - `file_path.startswith((".issues/", "issues/"))`
- `merge_coordinator.py:173-178, 383-385` - Checks both `.issues/completed/` and `issues/completed/`

### Files that ONLY handle `.issues/` (missing `issues/`):
- `git_operations.py:15-21` - `EXCLUDED_DIRECTORIES = (".issues/", ...)`
- `work_verification.py:18-24` - `EXCLUDED_DIRECTORIES = (".issues/", ...)`

## Impact

If `issues.base_dir` is configured as `issues` (without dot) instead of the default `.issues`:
- Work verification would NOT exclude issue file changes
- Issue files would be incorrectly counted as "meaningful work"
- This could cause false positives when checking if real implementation work was done

## Location

- **File**: `scripts/little_loops/git_operations.py`
- **Line(s)**: 15-21
- **File**: `scripts/little_loops/work_verification.py`
- **Line(s)**: 18-24

## Proposed Solution

Add `"issues/"` to `EXCLUDED_DIRECTORIES` in both files:

```python
EXCLUDED_DIRECTORIES = (
    ".issues/",
    "issues/",  # Add this line
    ".speckit/",
    "thoughts/",
    ".worktrees/",
    ".auto-manage",
)
```

## Verification

1. Update both `EXCLUDED_DIRECTORIES` tuples
2. Add test case for `issues/` variant in `test_work_verification.py`
3. Run existing tests to ensure no regressions

## Priority Rationale

P3 - Low impact since the default config uses `.issues/`, but should be fixed for consistency and to support alternative configurations.

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/git_operations.py`: Added `"issues/"` to EXCLUDED_DIRECTORIES tuple
- `scripts/little_loops/work_verification.py`: Added `"issues/"` to EXCLUDED_DIRECTORIES tuple
- `scripts/tests/test_work_verification.py`: Added two test cases for `issues/` variant

### Verification Results
- Tests: PASS (44 tests)
- Lint: PASS (modified files)
- Types: PASS
