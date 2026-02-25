# Plan: BUG-424 - Bare exception catch swallows errors in merge loop

## Issue Summary

In `_merge_loop()` at `merge_coordinator.py:680`, `except Exception` catches all exceptions from `self._queue.get(timeout=1.0)` when only `queue.Empty` should be caught. This silently swallows programming bugs.

## Research Findings

- **Correct pattern exists**: `priority_queue.py:101-108` catches `Empty` specifically (imported from `queue` module)
- **Completed similar issue**: BUG-233 fixed the same pattern in `priority_queue.py`
- **Test pattern exists**: `test_priority_queue.py:766-772` verifies non-Empty exceptions propagate
- **Import style**: `merge_coordinator.py:14` already imports `from queue import Queue` — needs `Empty` added

## Implementation Plan

### Phase 1: Fix the import and exception handler

**File**: `scripts/little_loops/parallel/merge_coordinator.py`

1. **Line 14**: Change `from queue import Queue` to `from queue import Empty, Queue`
2. **Line 680**: Change `except Exception:` to `except Empty:`

### Phase 2: Add test

**File**: `scripts/tests/test_merge_coordinator.py`

Add a new test class `TestMergeLoopExceptionHandling` with:
1. Test that `queue.Empty` is handled gracefully (loop continues)
2. Test that non-Empty exceptions propagate to the outer handler (logged, not silently swallowed)

Model after `test_priority_queue.py:760-772`.

## Success Criteria

- [ ] `except Exception` on line 680 replaced with `except Empty`
- [ ] `Empty` imported from `queue` module
- [ ] Test verifies `queue.Empty` continues loop
- [ ] Test verifies non-Empty exceptions reach outer handler
- [ ] All existing tests pass
- [ ] Lint and type checks pass

## Risk Assessment

- **Risk**: Low — narrowing exception handling is strictly better
- **Breaking change**: No — behavior is identical for the expected `queue.Empty` case
