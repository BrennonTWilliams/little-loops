---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# ENH-309: Sprint execution plan should show file contention warnings

## Summary

When `ll-sprint run` displays the execution plan (waves), it should warn about potential file contention within each wave. If ENH-306 (wave splitting) is implemented, it should show the refined sub-waves. If not, it should still warn about overlapping issues in the same wave during `--dry-run` or the pre-execution plan display.

## Context

Identified from root cause analysis of a sprint failure. The execution plan showed 3 issues in the same wave with no indication that they all modified the same file. A dry-run warning would have caught the problem before execution.

## Current Behavior

1. `_cmd_sprint_run()` displays waves with issue IDs and dependency info
2. `_render_execution_plan()` at `cli.py:1517` shows wave structure
3. No file contention information is shown in the plan

## Expected Behavior

The execution plan should:
1. Run `extract_file_hints()` on each issue in multi-issue waves
2. Check for pairwise overlaps using `FileHints.overlaps_with()`
3. Display warnings for overlapping issues, showing which files/directories are contended
4. If ENH-306 is implemented, show sub-wave splits in the plan display

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

## Related Issues

- ENH-306: File-contention-aware wave splitting (this issue displays what ENH-306 computes)
- BUG-305: Sprint overlap detection (runtime layer)

## Labels

`enhancement`, `captured`, `sprint`, `ux`

---

## Status

**Open** | Created: 2026-02-09 | Priority: P3
