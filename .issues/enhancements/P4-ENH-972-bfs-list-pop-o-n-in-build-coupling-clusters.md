---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# ENH-972: BFS queue uses O(n) `list.pop(0)` in `_build_coupling_clusters`

## Summary

`_build_coupling_clusters` implements BFS connected-component detection using a plain `list` as the queue, calling `queue.pop(0)` to dequeue. `list.pop(0)` is O(n) because it shifts all remaining elements. Replacing with `collections.deque` makes each dequeue O(1), following the standard Python BFS pattern already used elsewhere in the package.

## Location

- **File**: `scripts/little_loops/issue_history/coupling.py`
- **Line(s)**: 125–134 (at scan commit: 96d74cda)
- **Anchor**: `in function _build_coupling_clusters`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/issue_history/coupling.py#L125-L134)
- **Code**:
```python
queue = [start]
while queue:
    node = queue.pop(0)   # O(n) — shifts all remaining elements
    for neighbor in adjacency.get(node, []):
        if neighbor not in visited:
            visited.add(neighbor)
            queue.append(neighbor)
```

## Current Behavior

For a coupling graph with many co-changed files, each BFS step performs an O(n) pop, resulting in O(n²) per connected component traversal. In practice, coupling graphs are sparse so this rarely matters, but the pattern is incorrect.

## Expected Behavior

`collections.deque.popleft()` provides O(1) dequeue. The `deque` import is already present in the package (e.g., `dependency_graph.py`).

## Motivation

Correctness of algorithmic patterns matters for maintainability and future scalability. Using `list.pop(0)` as a BFS queue is a well-known Python anti-pattern that will surprise contributors expecting idiomatic code.

## Proposed Solution

```python
from collections import deque

queue = deque([start])
while queue:
    node = queue.popleft()   # O(1)
    for neighbor in adjacency.get(node, []):
        if neighbor not in visited:
            visited.add(neighbor)
            queue.append(neighbor)
```

## Scope Boundaries

- Change only the queue data structure; no behavior change to clustering logic or thresholds

## Success Metrics

- `_build_coupling_clusters` uses `deque.popleft()` instead of `list.pop(0)`

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/coupling.py` — `_build_coupling_clusters`

### Dependent Files (Callers/Importers)
- `analyze_coupling` in the same file — calls `_build_coupling_clusters`

### Similar Patterns
- `scripts/little_loops/dependency_graph.py` — already imports and uses `deque`

### Tests
- `scripts/tests/test_issue_history_advanced_analytics.py` — existing tests should pass unchanged

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `from collections import deque` import (or verify it already exists in `coupling.py`)
2. Replace `queue = [start]` with `queue = deque([start])`
3. Replace `queue.pop(0)` with `queue.popleft()`
4. Run existing coupling tests to confirm no behavior change

## Impact

- **Priority**: P4 — Performance correctness; negligible impact in practice but wrong pattern
- **Effort**: Small — 2-line change
- **Risk**: Low — Pure data structure swap; identical behavior
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-04-11T19:02:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4
