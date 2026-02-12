---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# ENH-351: Use collections.deque for BFS in coupling cluster builder

## Summary

The BFS implementation in `_build_coupling_clusters` uses `list.pop(0)` which is O(n) per dequeue, making overall BFS O(n^2). Should use `collections.deque.popleft()` for O(1).

## Location

- **File**: `scripts/little_loops/issue_history.py`
- **Line(s)**: 1639-1648 (at scan commit: be30013)
- **Anchor**: `_build_coupling_clusters`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/be30013d0e2446b479c121af1d58a2309b3cfeb5/scripts/little_loops/issue_history.py#L1639-L1648)
- **Code**:
```python
queue = [start]
while queue:
    node = queue.pop(0)  # O(n) operation
```

## Current Behavior

BFS uses `list.pop(0)` - O(n) per dequeue making overall BFS O(n^2).

## Expected Behavior

BFS uses `collections.deque.popleft()` - O(1) per dequeue making overall BFS O(n).

## Proposed Solution

```python
from collections import deque
queue = deque([start])
while queue:
    node = queue.popleft()
```

## Scope Boundaries

- Only change the queue data structure, no algorithmic changes

## Impact

- **Priority**: P4 - Minor performance; graph sizes are typically small
- **Effort**: Small - Two-line change
- **Risk**: Low - Standard Python optimization
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`


---

**Open** | Created: 2026-02-12 | Priority: P4
