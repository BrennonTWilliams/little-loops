---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# ENH-309: Sprint execution plan should show file contention warnings

## Summary

When `ll-sprint run` displays the execution plan (waves), it should warn about potential file contention within each wave. If ENH-306 (wave splitting) is implemented, it should show the refined sub-waves. If not, it should still warn about overlapping issues in the same wave during `--dry-run` or the pre-execution plan display.

## Context

Identified from root cause analysis of a sprint failure. The execution plan showed 3 issues in the same wave with no indication that they all modified the same file. A dry-run warning would have caught the problem before execution.

## Current Pain Point

The execution plan display gives no indication of file contention between issues in the same wave. Users must discover merge conflicts at runtime rather than seeing warnings upfront. This was the root cause of a sprint failure where 3 issues in the same wave all modified the same file.

## Current Behavior

1. `_cmd_sprint_run()` displays waves with issue IDs and dependency info
2. `_render_execution_plan()` at `cli.py:1520` shows wave structure
3. ENH-306 (wave splitting) is implemented, so waves are refined for contention — but the plan display does not show *why* waves were split or what contention was detected
4. No file contention information is shown in the plan

## Expected Behavior

The execution plan should:
1. Run `extract_file_hints()` on each issue in multi-issue waves
2. Check for pairwise overlaps using `FileHints.overlaps_with()`
3. Display warnings for overlapping issues, showing which files/directories are contended
4. Since ENH-306 (wave splitting) is implemented, show sub-wave splits and the contention reason in the plan display

Example output:
```
Wave 2 (after Wave 1) parallel:
  ├── FEAT-031: Add priority starring (P2)
  ├── ENH-032: Add empty state placeholder (P3)
  └── ENH-033: Add duration tracking (P3)
  ⚠️  File contention: FEAT-031, ENH-032, ENH-033 all touch src/app/projects/[id]/activities/page.tsx
  → Will be split into sub-waves to avoid merge conflicts
```

## Proposed Solution

Enhance `_render_execution_plan()` to include file contention analysis. Use existing `extract_file_hints()` and `FileHints.overlaps_with()` from `parallel/file_hints.py`.

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Low — display-only change, no execution impact

## Files

- `scripts/little_loops/cli.py` — Enhance `_render_execution_plan()`

## Scope Boundaries

- **In scope**: Adding contention warnings and sub-wave annotations to `_render_execution_plan()` output
- **Out of scope**: Changing wave splitting logic (already handled by ENH-306), modifying runtime overlap detection (BUG-305), or adding interactive prompts

## Related Issues

- ENH-306: File-contention-aware wave splitting — completed (this issue displays what ENH-306 computes)
- BUG-305: Sprint overlap detection (runtime layer) — completed

## Labels

`enhancement`, `captured`, `sprint`, `ux`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/file_hints.py`: Added `get_overlapping_paths()` method to `FileHints` for extracting specific overlapping paths
- `scripts/little_loops/dependency_graph.py`: Added `WaveContentionNote` dataclass; modified `refine_waves_for_contention()` to return contention metadata alongside refined waves
- `scripts/little_loops/cli.py`: Updated `_render_execution_plan()` to display contention warnings with sub-wave index and contended file paths; updated both `_cmd_sprint_show()` and `_cmd_sprint_run()` callers
- `scripts/tests/test_file_hints.py`: Added 8 tests for `get_overlapping_paths()`
- `scripts/tests/test_dependency_graph.py`: Updated 9 existing tests for tuple return; added 2 new contention note tests
- `scripts/tests/test_cli.py`: Added 4 new tests for contention display in execution plan

### Verification Results
- Tests: PASS (2674 passed)
- Lint: PASS
- Types: PASS
