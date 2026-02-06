---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# BUG-233: Overly broad exception catch in priority queue hides errors

## Summary

The `ThreadSafePriorityQueue.get()` method catches `except Exception` to handle `queue.Empty`, but this also silently swallows any other exceptions that may occur inside the lock block, masking real errors.

## Location

- **File**: `scripts/little_loops/parallel/priority_queue.py`
- **Line(s)**: 101-108 (at scan commit: a8f4144)
- **Anchor**: `in method ThreadSafePriorityQueue.get`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/parallel/priority_queue.py#L101-L108)
- **Code**:
```python
try:
    queued = self._queue.get(block=block, timeout=timeout)
    with self._lock:
        self._queued.discard(queued.issue_info.issue_id)
        self._in_progress.add(queued.issue_info.issue_id)
    return queued
except Exception:
    return None
```

## Current Behavior

`except Exception: return None` catches `queue.Empty` as intended, but also silently catches `AttributeError`, `KeyError`, or any other exception inside the lock block. This makes debugging very difficult when things go wrong.

## Expected Behavior

The catch should be narrowed to `except queue.Empty:` so that only the expected empty-queue condition is handled, and real errors propagate.

## Reproduction Steps

1. Introduce any error in the priority queue (e.g., a malformed `queued` object)
2. The error is silently swallowed and `None` is returned
3. Caller proceeds with `None` instead of seeing the real error

## Proposed Solution

```python
import queue as queue_module

try:
    queued = self._queue.get(block=block, timeout=timeout)
    with self._lock:
        self._queued.discard(queued.issue_info.issue_id)
        self._in_progress.add(queued.issue_info.issue_id)
    return queued
except queue_module.Empty:
    return None
```

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p2`

---

## Status
**Open** | Created: 2026-02-06T03:41:30Z | Priority: P2
