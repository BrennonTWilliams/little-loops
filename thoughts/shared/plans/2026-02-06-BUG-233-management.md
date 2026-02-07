# BUG-233: Overly broad exception catch in priority queue - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-233-overly-broad-exception-catch-in-priority-queue.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `IssuePriorityQueue.get()` method at `scripts/little_loops/parallel/priority_queue.py:91-108` uses `except Exception` to catch `queue.Empty`, but this also silently swallows any other exceptions (AttributeError, KeyError, etc.) that may occur inside the lock block at lines 103-105.

### Key Discoveries
- `priority_queue.py:10` imports `from queue import PriorityQueue` — the `Empty` exception is NOT currently imported
- `priority_queue.py:107-108` uses `except Exception: return None` — overly broad
- `orchestrator.py:579` is the primary caller, uses `get(block=False)` and checks `if queued:`
- Existing codebase pattern: `from queue import X` (not `import queue as queue_module`)
- Test at `test_priority_queue.py:760-764` verifies empty queue returns `None`

## Desired End State

The `get()` method catches only `queue.Empty` (the expected exception when the queue is empty), allowing real errors to propagate to callers for proper debugging.

### How to Verify
- Empty queue still returns `None` (existing tests pass)
- Other exceptions propagate instead of being silently swallowed
- All existing tests pass
- Lint and type checks pass

## What We're NOT Doing

- Not fixing the similar pattern in `merge_coordinator.py:679-681` — separate issue
- Not changing the caller in `orchestrator.py` — it already handles `None` correctly
- Not adding new error handling/logging to the `get()` method beyond narrowing the catch

## Problem Analysis

The root cause is that `except Exception` was used instead of the specific `except queue.Empty`. The `Empty` exception wasn't imported, which likely led to the shortcut of catching all exceptions.

## Solution Approach

1. Add `Empty` to the existing `from queue import` statement
2. Narrow the `except` clause from `Exception` to `Empty`
3. Update the existing test to verify non-Empty exceptions propagate

## Implementation Phases

### Phase 1: Fix the exception handling

#### Changes Required

**File**: `scripts/little_loops/parallel/priority_queue.py`

1. Update import (line 10): Add `Empty` to existing import
```python
from queue import Empty, PriorityQueue
```

2. Narrow exception catch (line 107): Change `except Exception` to `except Empty`
```python
except Empty:
    return None
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_priority_queue.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/priority_queue.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/priority_queue.py`

### Phase 2: Update test to verify correct exception narrowing

#### Changes Required

**File**: `scripts/tests/test_priority_queue.py`

Update `test_get_exception_handling` to also verify that non-Empty exceptions propagate:

```python
def test_get_exception_handling(self, queue: IssuePriorityQueue) -> None:
    """get() returns None on queue.Empty exception."""
    # Empty queue with block=False should return None, not raise
    result = queue.get(block=False)
    assert result is None

def test_get_propagates_non_empty_exceptions(
    self, queue: IssuePriorityQueue, sample_issue: IssueInfo
) -> None:
    """get() propagates exceptions that aren't queue.Empty."""
    queue.add(sample_issue)
    # Corrupt internal state to trigger an AttributeError
    with unittest.mock.patch.object(
        queue, "_queued", side_effect_on_discard=True
    ):
        ...
    # Use mock to make _queue.get return an object without issue_info
    from unittest.mock import MagicMock
    bad_item = MagicMock(spec=[])  # no issue_info attribute
    queue._queue.put(bad_item)
    with pytest.raises(AttributeError):
        queue.get(block=False)
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_priority_queue.py -v`
- [ ] Full suite passes: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## References

- Original issue: `.issues/bugs/P2-BUG-233-overly-broad-exception-catch-in-priority-queue.md`
- Affected code: `scripts/little_loops/parallel/priority_queue.py:101-108`
- Primary caller: `scripts/little_loops/parallel/orchestrator.py:579`
- Tests: `scripts/tests/test_priority_queue.py:760-764`
