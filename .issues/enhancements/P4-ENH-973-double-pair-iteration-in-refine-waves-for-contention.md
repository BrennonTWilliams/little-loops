---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# ENH-973: `refine_waves_for_contention` iterates all pairs twice when conflicts exist

## Summary

`refine_waves_for_contention` performs two separate O(n²) passes over the same set of issue pairs: one to detect conflicts via `overlaps_with`, and a second to collect contended paths via `get_overlapping_paths`. When conflicts exist, every conflicting pair is processed twice. Both checks can be combined into a single pass since `get_overlapping_paths` is a superset of `overlaps_with`.

## Location

- **File**: `scripts/little_loops/dependency_graph.py`
- **Line(s)**: 380–398 (at scan commit: 96d74cda)
- **Anchor**: `in function refine_waves_for_contention`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/dependency_graph.py#L380-L398)
- **Code**:
```python
# First pass — detect conflicts:
for a, b in combinations(wave, 2):
    if hints[a].overlaps_with(hints[b]):
        conflicts.add(a); conflicts.add(b)

# Second pass — collect contended paths (identical pair iteration):
for a, b in combinations(wave, 2):
    paths = hints[a].get_overlapping_paths(hints[b])
    if paths:
        contended |= paths
```

## Current Behavior

When a wave has conflicts, the full `combinations(wave, 2)` set is iterated twice. `overlaps_with` and `get_overlapping_paths` operate on the same underlying data; `get_overlapping_paths` returns the paths when there is overlap (equivalent to `overlaps_with` returning `True`).

## Expected Behavior

A single pass over pairs collects both the conflict adjacency set and the contended paths, halving the pair comparison work.

## Motivation

`refine_waves_for_contention` is called per wave during sprint and parallel planning. For large waves, the quadratic pair count makes double-iteration a meaningful overhead.

## Proposed Solution

```python
for a, b in combinations(wave, 2):
    paths = hints[a].get_overlapping_paths(hints[b])
    if paths:
        conflicts.add(a); conflicts.add(b)
        contended |= paths
# Remove the second loop entirely
```

This works because `get_overlapping_paths` returns a non-empty set exactly when `overlaps_with` would return `True`.

## Scope Boundaries

- Only merge the two loops; do not change the conflict/contention threshold logic or return structure

## Success Metrics

- `refine_waves_for_contention` contains a single `combinations` loop for conflict detection

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_graph.py` — `refine_waves_for_contention`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sprint_manager.py` — calls `refine_waves_for_contention`
- `scripts/little_loops/parallel/orchestrator.py` — may call via wave planning

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_dependency_graph.py` — existing tests should pass; add a test asserting `get_overlapping_paths` is called only once per pair

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Replace the two `combinations` loops with a single loop using `get_overlapping_paths`
2. Confirm `get_overlapping_paths` returns empty set when `overlaps_with` would return `False` (verify in tests)
3. Run existing dependency graph tests to confirm no behavior change

## Impact

- **Priority**: P4 — Minor optimization for an already fast path; worth doing for correctness of the pattern
- **Effort**: Small — Remove one loop, add two lines to the other
- **Risk**: Low — Pure algorithmic refactor with identical semantics
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4
