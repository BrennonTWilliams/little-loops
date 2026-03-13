---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-699: Redundant scatter score denominator guard in `detect_cross_cutting_smells`

## Summary

In `detect_cross_cutting_smells`, line 109 sets `total_dirs = 1` when `all_directories` is empty, making the `total_dirs > 0` guard on line 114 always true by construction. The redundant check is untested and obscures the invariant.

## Location

- **File**: `scripts/little_loops/issue_history/debt.py`
- **Line(s)**: 109-114 (at scan commit: 3e9beea)
- **Anchor**: `in function detect_cross_cutting_smells()`

## Current Behavior

Redundant `if total_dirs > 0 else 0.0` guard that can never reach the `0.0` branch because `total_dirs` is guaranteed >= 1 by the line above.

## Expected Behavior

Simplify line 114 to `scatter_score = len(dirs) / total_dirs` and add a test documenting the empty-directories case.

## Scope Boundaries

- Remove the redundant guard; add one test case

## Impact

- **Priority**: P5 - Code clarity improvement
- **Effort**: Small - Remove one ternary, add one test
- **Risk**: Low - Guard was dead code
- **Breaking Change**: No

## Labels

`enhancement`, `code-quality`, `issue-history`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P5
