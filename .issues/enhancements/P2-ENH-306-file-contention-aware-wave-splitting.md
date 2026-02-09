---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# ENH-306: Add file-contention-aware wave splitting to dependency graph

## Summary

`DependencyGraph.get_execution_waves()` computes waves purely from `blocked_by` relationships. It does not consider file contention — issues that modify the same files can be placed in the same parallel wave. Add a post-processing step that refines waves by splitting overlapping issues into sub-waves.

## Context

Identified from root cause analysis of a sprint failure. Three issues with no dependency relationship were placed in the same wave because `get_execution_waves()` only considers `blocked_by` edges. All three modified `page.tsx`, causing merge conflicts when dispatched in parallel.

While BUG-305 enables the runtime `OverlapDetector` as a safety net, this enhancement provides static prevention — contention is detected and resolved before any work begins. This is defense-in-depth: wave splitting prevents the problem; overlap detection catches edge cases at runtime.

## Current Behavior

1. `get_execution_waves()` at `dependency_graph.py:119-166` uses only `blocked_by` relationships
2. Issues with no dependency relationship but touching the same files are grouped in the same wave
3. Parallel dispatch of these issues causes merge conflicts

## Expected Behavior

After computing dependency-based waves, refine each wave by:
1. For each wave with >1 issue, extract `FileHints` for each issue using existing `extract_file_hints()` from `parallel/file_hints.py`
2. Build an overlap graph within the wave using `FileHints.overlaps_with()`
3. If overlaps exist, split the wave into sub-waves where no two issues in the same sub-wave overlap (greedy graph coloring)
4. Display the refined plan showing any sub-waves created due to file contention

## Proposed Solution

Add a function `refine_waves_for_contention(waves, issue_infos)` to `dependency_graph.py` that:
1. Takes the output of `get_execution_waves()` and the list of `IssueInfo` objects
2. For each wave with >1 issue, reads issue file content to extract `FileHints`
3. Checks pairwise overlaps within the wave
4. Uses greedy coloring to assign issues to sub-waves (minimizing total sub-waves)
5. Returns the refined wave list

Wire this into `_cmd_sprint_run()` after the call to `dep_graph.get_execution_waves()`.

## Impact

- **Priority**: P2
- **Effort**: Medium (new function + tests + wiring in CLI)
- **Risk**: Low — post-processing step, doesn't change existing wave logic

## Files

- `scripts/little_loops/dependency_graph.py` — Add `refine_waves_for_contention()`
- `scripts/little_loops/cli.py` — Wire into `_cmd_sprint_run()` after `get_execution_waves()`
- `scripts/tests/test_dependency_graph.py` — Tests for wave refinement

## Reuse

- `scripts/little_loops/parallel/file_hints.py` — `extract_file_hints()`, `FileHints.overlaps_with()`

## Related Issues

- BUG-305: Sprint runner doesn't enable overlap detection (runtime safety net)
- ENH-301: Integrate dependency mapper into sprint (related but broader scope)

## Labels

`enhancement`, `captured`, `sprint`, `parallel`, `dependency-graph`

---

## Status

**Open** | Created: 2026-02-09 | Priority: P2
