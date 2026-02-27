---
discovered_commit: 325fd14
discovered_branch: main
discovered_date: 2026-02-26
discovered_by: manual-audit
focus_area: dependency-mapping
---

# ENH-512: Remove redundant runtime overlap detection layer in ParallelOrchestrator

## Summary

`ll-sprint run` applies file overlap detection twice using identical logic: once at wave-planning time (`refine_waves_for_contention` in `dependency_graph.py:339`) and again at dispatch time (`OverlapDetector` in `orchestrator.py:744`). The runtime layer is redundant when used from `ll-sprint` because wave splitting already guarantees no overlapping issues run concurrently.

## Current Behavior

**Layer 2 — Wave splitting** (`dependency_graph.py:339-424`):
After `get_execution_waves()` produces parallel waves, `refine_waves_for_contention()` reads each issue's content, calls `extract_file_hints()`, checks pairwise `overlaps_with()`, and splits waves using greedy graph coloring. Issues in different sub-waves run sequentially.

**Layer 3 — Runtime deferral** (`orchestrator.py:742-752`):
When `ParallelOrchestrator._process_parallel()` dispatches an issue, it calls `OverlapDetector.check_overlap()` which uses the exact same `FileHints.overlaps_with()`. If overlap is found and `serialize_overlapping=True`, the issue is deferred to `_deferred_issues` and re-checked when active issues complete (`_requeue_deferred_issues` at line 834).

Both layers use the identical `extract_file_hints()` + `overlaps_with()` pipeline from `parallel/file_hints.py`. When called from `ll-sprint run`, Layer 2 has already ensured no two overlapping issues are in the same wave, so Layer 3 will never find overlaps to defer.

**Sprint runner enables both** at `cli/sprint/run.py:306-307`:
```python
overlap_detection=True,
serialize_overlapping=True,
```

## Expected Behavior

One of the two layers should be removed or they should be consolidated:

**Option A (Recommended)**: Remove the `overlap_detection` / `serialize_overlapping` flags from the sprint runner's `ParallelOrchestrator` construction. Wave splitting already handles this. The runtime `OverlapDetector` remains available for `ll-parallel` (which doesn't do wave splitting).

**Option B**: Remove `refine_waves_for_contention()` from the sprint path and rely solely on the runtime `OverlapDetector`. This would allow more issues per wave but defer overlapping ones at dispatch time.

## Location

- `scripts/little_loops/cli/sprint/run.py:306-307` — enables both layers
- `scripts/little_loops/dependency_graph.py:339-424` — Layer 2 (wave splitting)
- `scripts/little_loops/parallel/orchestrator.py:742-752` — Layer 3 (runtime deferral)
- `scripts/little_loops/parallel/overlap_detector.py:97-135` — Layer 3 implementation

## Proposed Solution

Go with Option A:
1. Set `overlap_detection=False` in `cli/sprint/run.py` when constructing `parallel_config` for sprint execution
2. Keep `overlap_detection=True` as the default for `ll-parallel` standalone usage
3. Document the distinction: sprints use pre-planned wave splitting; standalone parallel uses runtime detection

### Suggested Approach

1. In `cli/sprint/run.py`, change line 306 to `overlap_detection=False`
2. Add a comment explaining that `refine_waves_for_contention()` already handles overlap for sprints
3. Verify `ll-parallel` still uses `overlap_detection=True` independently
4. Update any relevant documentation

## Scope Boundaries

- **In scope**: Removing redundant overlap detection from sprint path
- **Out of scope**: Changing `ll-parallel` behavior, modifying the OverlapDetector itself

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint/run.py` — disable runtime overlap detection for sprint context

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — respects the flag, no changes needed
- `scripts/little_loops/cli/parallel.py` — standalone parallel, keeps current behavior

### Tests
- `scripts/tests/test_sprint_run.py` (if exists) — verify sprint still works without runtime overlap
- `scripts/tests/test_orchestrator.py` — no changes needed (tests orchestrator independently)

## Impact

- **Priority**: P3 - Low (functionally redundant, not broken)
- **Effort**: Small - Single flag change in one file
- **Risk**: Low - No behavioral change for sprint path; standalone parallel unaffected
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `dependency-mapping`

---

## Resolution

**Implemented Option A**: Set `overlap_detection=False` in `cli/sprint/run.py` for sprint execution. Wave splitting via `refine_waves_for_contention()` already guarantees no overlapping issues run concurrently within the same wave, making the runtime `OverlapDetector` redundant in the sprint path. Standalone `ll-parallel` remains unaffected.

### Changes Made
- `scripts/little_loops/cli/sprint/run.py:302-311` — Changed `overlap_detection=True` to `overlap_detection=False` with explanatory comment
- `scripts/tests/test_sprint_integration.py:415-481` — Updated test to assert `overlap_detection is False`

## Status

**Completed** | Created: 2026-02-26 | Resolved: 2026-02-26 | Priority: P3

## Session Log
- manual audit - 2026-02-26 - Identified during exhaustive dependency mapping system audit
- manage-issue - 2026-02-26 - Implemented Option A: disabled runtime overlap detection in sprint runner
