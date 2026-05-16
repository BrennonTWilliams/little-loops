---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# BUG-421: TOCTOU file deletion race in _move_issue_to_completed()

## Summary

The pattern `if original_path.exists(): original_path.unlink()` appears three times in `_move_issue_to_completed()`. This is a Time-Of-Check-Time-Of-Use (TOCTOU) race condition — in parallel processing, another worker could delete the file between the `exists()` check and `unlink()` call, causing `FileNotFoundError`.

## Location

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Line(s)**: 299-304, 321-322, 331-332 (at scan commit: 71616c7)
- **Anchor**: `in function _move_issue_to_completed()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/71616c711e2fe9f5f1ececcf1c64552bca9d82ec/scripts/little_loops/issue_lifecycle.py#L299-L332)
- **Code**:
```python
if completed_path.exists():
    logger.info(f"Destination already exists: {completed_path.name}, updating content")
    completed_path.write_text(content)
    if original_path.exists():  # TOCTOU race
        original_path.unlink()
    return True
```

## Current Behavior

File existence is checked before deletion, but in parallel execution another worker could delete the file between the check and the unlink.

## Expected Behavior

File deletion should be atomic — use `missing_ok=True` parameter on `unlink()` or wrap in try/except `FileNotFoundError`.

## Steps to Reproduce

1. Run parallel issue processing with multiple workers
2. Have two workers complete the same issue simultaneously
3. One worker deletes `original_path` between the other's `exists()` check and `unlink()` call
4. Second worker gets `FileNotFoundError`

## Actual Behavior

`FileNotFoundError` raised when the file is deleted by another process between the `exists()` check and `unlink()` call.

## Root Cause

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Anchor**: `in function _move_issue_to_completed()`
- **Cause**: TOCTOU race condition from check-then-act pattern on filesystem operations in a concurrent environment.

## Proposed Solution

Replace the check-then-act pattern with `missing_ok=True` (Python 3.8+):

```python
# Before (TOCTOU):
if original_path.exists():
    original_path.unlink()

# After (atomic):
original_path.unlink(missing_ok=True)
```

Apply this fix at all three locations (lines 302-303, 321-322, 331-332).

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — calls lifecycle functions
- `scripts/little_loops/issue_manager.py` — calls lifecycle functions

### Similar Patterns
- Search for other `exists()` + `unlink()` patterns in the codebase

### Tests
- `scripts/tests/test_issue_lifecycle.py` — add concurrent deletion test

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Replace all three `if exists(): unlink()` patterns with `unlink(missing_ok=True)`
2. Search for similar patterns elsewhere in codebase
3. Add test simulating concurrent file deletion

## Impact

- **Priority**: P3 - Can cause failures in parallel processing, which is a core feature
- **Effort**: Small - Three line changes
- **Risk**: Low - `missing_ok=True` is a drop-in replacement
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `parallel`, `race-condition`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-14
- **Status**: Completed

### Changes Made
- Replaced 3x `if path.exists(): path.unlink()` TOCTOU patterns with `path.unlink(missing_ok=True)` in `_move_issue_to_completed()`
- Fixed same pattern in `parallel/orchestrator.py` `_complete_issue_lifecycle_if_needed()`
- Added concurrent deletion test `test_source_deleted_by_concurrent_worker`

### Files Changed
  - `scripts/little_loops/issue_lifecycle.py`
  - `scripts/little_loops/parallel/orchestrator.py`
  - `scripts/tests/test_issue_lifecycle.py`

### Verification Results
- 66 tests passed
- ruff check: All checks passed
- mypy: No issues found

---

## Status

**Completed** | Created: 2026-02-15 | Completed: 2026-02-14 | Priority: P3
