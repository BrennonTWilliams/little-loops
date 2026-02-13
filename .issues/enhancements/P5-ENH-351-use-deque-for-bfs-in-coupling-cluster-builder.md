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

## Motivation

This enhancement would:
- Correct BFS time complexity from O(n^2) to O(n) by replacing `list.pop(0)` with `deque.popleft()`
- Business value: Proper algorithmic complexity for graph traversal, even though current graph sizes are small
- Technical debt: Eliminates a well-known Python anti-pattern (`list.pop(0)`) that could become a bottleneck as data grows

## Implementation Steps

1. **Import deque**: Add `from collections import deque` at the top of `scripts/little_loops/issue_history.py`
2. **Replace list with deque**: Change `queue = [start]` to `queue = deque([start])` in `_build_coupling_clusters`
3. **Replace pop(0) with popleft()**: Change `queue.pop(0)` to `queue.popleft()`
4. **Run tests**: Execute `python -m pytest scripts/tests/test_issue_history.py` to verify no regressions

## Integration Map

- **Files to Modify**: `scripts/little_loops/issue_history.py`
- **Dependent Files (Callers/Importers)**: Internal function called by coupling analysis in `issue_history.py`
- **Similar Patterns**: N/A
- **Tests**: `scripts/tests/test_issue_history.py`
- **Documentation**: N/A
- **Configuration**: N/A

## Scope Boundaries

- Only change the queue data structure, no algorithmic changes

## Impact

- **Priority**: P4 - Minor performance; graph sizes are typically small
- **Effort**: Small - Two-line change
- **Risk**: Low - Standard Python optimization
- **Breaking Change**: No

## Blocked By

- ENH-350: cache issue file contents in history analysis (shared issue_history.py)

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`
- `/ll:format_issue --all --auto` - 2026-02-13


---

**Open** | Created: 2026-02-12 | Priority: P4
