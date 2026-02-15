---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# BUG-424: Bare exception catch swallows errors in merge loop

## Summary

In `_merge_loop()`, the inner try-except catches `Exception` for the queue get operation. While this is intended to catch `queue.Empty`, it also silently swallows unexpected errors like `AttributeError` or `TypeError` that would indicate programming bugs, making debugging difficult.

## Location

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Line(s)**: 678-681 (at scan commit: 71616c7)
- **Anchor**: `in method _merge_loop()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/71616c711e2fe9f5f1ececcf1c64552bca9d82ec/scripts/little_loops/parallel/merge_coordinator.py#L678-L681)
- **Code**:
```python
try:
    request = self._queue.get(timeout=1.0)
except Exception:  # Catches ALL exceptions
    continue
```

## Current Behavior

All exceptions from `self._queue.get()` are silently caught and ignored with `continue`.

## Expected Behavior

Only `queue.Empty` should be caught. Unexpected exceptions should be logged or re-raised.

## Steps to Reproduce

1. Introduce a bug that causes an unexpected exception during queue operations
2. The error is silently swallowed
3. Debugging requires adding manual logging to find the issue

## Actual Behavior

Unexpected exceptions are silently ignored, making it impossible to diagnose issues without adding instrumentation.

## Root Cause

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Anchor**: `in method _merge_loop()`
- **Cause**: Overly broad `except Exception` clause catches expected `queue.Empty` but also unexpected errors.

## Proposed Solution

Narrow the exception to `queue.Empty`:

```python
import queue

try:
    request = self._queue.get(timeout=1.0)
except queue.Empty:
    continue
```

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/merge_coordinator.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — creates MergeCoordinator

### Similar Patterns
- Search for other `except Exception` patterns that should be narrower

### Tests
- `scripts/tests/` — add test for merge loop error handling

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Change `except Exception` to `except queue.Empty`
2. Search for similar broad exception patterns
3. Add test verifying unexpected exceptions propagate

## Impact

- **Priority**: P4 - Affects debuggability, not correctness in normal operation
- **Effort**: Small - One line change
- **Risk**: Low - More specific exception handling is strictly better
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `error-handling`, `parallel`

## Resolution

- **Fixed in**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Changes**:
  - Added `Empty` to import from `queue` module (line 14)
  - Narrowed `except Exception` to `except Empty` in `_merge_loop()` (line 680)
- **Tests added**: `TestMergeLoopExceptionHandling` in `scripts/tests/test_merge_coordinator.py`
  - `test_merge_loop_handles_queue_empty` — verifies loop continues on `queue.Empty`
  - `test_merge_loop_propagates_non_empty_to_outer_handler` — verifies unexpected exceptions reach outer handler and are logged
- **Verification**: All 83 tests pass, lint clean, mypy clean

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`
- `/ll:manage-issue bug fix BUG-424` - 2026-02-14

## Status

**Resolved** | Created: 2026-02-15 | Resolved: 2026-02-14 | Priority: P4
