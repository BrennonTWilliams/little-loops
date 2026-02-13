# ENH-240: Consolidate Duplicated Work Verification Code - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-240-consolidate-duplicated-work-verification-code.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

### Key Discoveries
- `EXCLUDED_DIRECTORIES` is identical in both `git_operations.py:18-25` and `work_verification.py:18-25`
- `filter_excluded_files()` is identical in both `git_operations.py:202-215` and `work_verification.py:28-41`
- `verify_work_was_done()` diverges: `work_verification.py:44-125` has diagnostic logging (lists excluded files), while `git_operations.py:218-283` logs generic messages
- `work_verification.py` is the enhanced/canonical version

### Import Graph
| Consumer | Imports From | Symbols Used |
|----------|-------------|-------------|
| `issue_manager.py:22` | `git_operations` | `check_git_status`, `verify_work_was_done` |
| `worker_pool.py:33` | `work_verification` | `EXCLUDED_DIRECTORIES`, `verify_work_was_done` |
| `__init__.py:8-13` | `git_operations` | `EXCLUDED_DIRECTORIES`, `check_git_status`, `filter_excluded_files`, `verify_work_was_done` |
| `test_subprocess_mocks.py` (7 tests) | `git_operations` (inline imports) | `verify_work_was_done` |
| `test_work_verification.py:17` | `work_verification` | all 3 symbols |

## Desired End State

- `work_verification.py` is the single canonical source for `EXCLUDED_DIRECTORIES`, `filter_excluded_files`, and `verify_work_was_done`
- `git_operations.py` re-exports these 3 symbols from `work_verification` for backward compatibility
- `__init__.py` imports these 3 symbols from `work_verification` (canonical source)
- All consumers get the enhanced version with diagnostic logging
- All existing tests pass without modification (re-exports preserve import paths)

### How to Verify
- All tests pass: `python -m pytest scripts/tests/`
- Lint passes: `ruff check scripts/`
- Types pass: `python -m mypy scripts/little_loops/`
- `from little_loops.git_operations import verify_work_was_done` still works
- `from little_loops.work_verification import verify_work_was_done` still works
- `from little_loops import verify_work_was_done` still works

## What We're NOT Doing

- Not changing any function signatures or behavior
- Not updating `issue_manager.py` or `worker_pool.py` imports (re-exports handle backward compat)
- Not modifying any test files (re-exports preserve all import paths)
- Not refactoring `check_git_status` (it's only in `git_operations.py`, not duplicated)

## Solution Approach

1. Remove the duplicated definitions from `git_operations.py`
2. Add re-exports from `work_verification` in `git_operations.py`
3. Update `__init__.py` to import from `work_verification` for the 3 consolidated symbols (keep `check_git_status` from `git_operations`)
4. Update `__all__` comment in `__init__.py` to reflect new source

## Implementation Phases

### Phase 1: Replace duplicated code in `git_operations.py` with re-exports

#### Overview
Remove `EXCLUDED_DIRECTORIES`, `filter_excluded_files()`, and `verify_work_was_done()` from `git_operations.py` and replace with imports from `work_verification.py`.

#### Changes Required

**File**: `scripts/little_loops/git_operations.py`
**Changes**:
1. Add import of the 3 symbols from `work_verification` at the top
2. Remove `EXCLUDED_DIRECTORIES` (lines 16-25)
3. Remove `filter_excluded_files()` (lines 202-215)
4. Remove `verify_work_was_done()` (lines 218-283)
5. Remove unused `subprocess` import reference and `Logger` import if no longer needed by remaining code (note: `check_git_status` still uses both, so they stay)

The re-export will be:
```python
from little_loops.work_verification import (
    EXCLUDED_DIRECTORIES,
    filter_excluded_files,
    verify_work_was_done,
)
```

**File**: `scripts/little_loops/__init__.py`
**Changes**: Update imports so the 3 consolidated symbols come from `work_verification`:

```python
from little_loops.git_operations import (
    check_git_status,
)
from little_loops.work_verification import (
    EXCLUDED_DIRECTORIES,
    filter_excluded_files,
    verify_work_was_done,
)
```

Update `__all__` comments to reflect new sources.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

No new tests needed. The re-exports preserve all existing import paths, so:
- `test_work_verification.py` continues testing the canonical implementations
- `test_subprocess_mocks.py` continues importing from `git_operations` (which re-exports)
- `test_git_operations.py` only imports `get_untracked_files` (unaffected)

## References

- Original issue: `.issues/enhancements/P3-ENH-240-consolidate-duplicated-work-verification-code.md`
- Backward compat alias pattern: `scripts/little_loops/config.py:682-683`
- Package re-export pattern: `scripts/little_loops/__init__.py:7-23`
