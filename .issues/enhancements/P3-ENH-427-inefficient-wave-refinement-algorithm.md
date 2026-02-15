---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# ENH-427: Inefficient O(N^2) wave refinement with synchronous file reads

## Summary

`refine_waves_for_contention()` reads issue files synchronously in a loop, then performs O(N^2) pairwise overlap checks. For large waves this is inefficient — file I/O is sequential and overlap detection has quadratic complexity.

## Current Behavior

For each wave, the function reads issue files one at a time in a `for` loop, then checks every pair of issues for file overlap with nested iteration. With N issues in a wave, this requires N file reads + N*(N-1)/2 comparisons.

## Expected Behavior

File reads should be parallelized (I/O-bound), and overlap detection should short-circuit when possible.

## Motivation

Sprint runs with large waves (10+ issues) spend unnecessary time on sequential file reads and redundant overlap checks. Parallelizing I/O and adding early termination would reduce wall-clock time for sprint planning and contention analysis.

## Scope Boundaries

- **In scope**: Parallelizing file reads, adding early termination to overlap detection
- **Out of scope**: Changing the overlap detection algorithm itself, caching across waves

## Proposed Solution

1. Use `concurrent.futures.ThreadPoolExecutor` for parallel file reads:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {
        pool.submit(extract_file_hints, issue.path.read_text(), issue.issue_id): issue
        for issue in wave if issue.path.exists()
    }
    for future in as_completed(futures):
        issue = futures[future]
        hints[issue.issue_id] = future.result()
```

2. Add early termination in overlap detection — if an issue already has enough conflicts to be deferred, skip further checks.

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_graph.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint.py` — calls wave refinement during sprint run

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_dependency_graph.py` — add performance test with larger wave

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Parallelize file reads with ThreadPoolExecutor
2. Add early termination in overlap loop
3. Benchmark before/after with 10+ issue waves

## Impact

- **Priority**: P3 - Improves sprint planning speed for large projects
- **Effort**: Small - Focused refactor of one function
- **Risk**: Low - Behavior unchanged, only faster
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `dependency-graph`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P3
