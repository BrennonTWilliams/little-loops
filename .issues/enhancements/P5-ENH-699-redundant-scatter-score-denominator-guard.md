---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-699: Redundant scatter score denominator guard in `detect_cross_cutting_smells`

## Summary

In `detect_cross_cutting_smells`, line 109 sets `total_dirs = 1` when `all_directories` is empty, making the `total_dirs > 0` guard on line 114 always true by construction.

## Motivation

A guard that can never be reached is dead code that misleads readers into thinking `total_dirs` could be zero at that point. Removing it clarifies the invariant and tests document the empty-directories behavior explicitly. The redundant check is untested and obscures the invariant.

## Location

- **File**: `scripts/little_loops/issue_history/debt.py`
- **Line(s)**: 109-114 (at scan commit: 3e9beea)
- **Anchor**: `in function detect_cross_cutting_smells()`

## Current Behavior

Redundant `if total_dirs > 0 else 0.0` guard that can never reach the `0.0` branch because `total_dirs` is guaranteed >= 1 by the line above.

## Expected Behavior

Simplify line 114 to `scatter_score = len(dirs) / total_dirs` and add a test documenting the empty-directories case.

## Implementation Steps

1. In `debt.py`, locate `detect_cross_cutting_smells` at line 109
2. Replace `scatter_score = len(dirs) / total_dirs if total_dirs > 0 else 0.0` with `scatter_score = len(dirs) / total_dirs`
3. Add a test case to the existing test file documenting the empty-directories case

## Integration Map

- **Modified**: `scripts/little_loops/issue_history/debt.py` — `detect_cross_cutting_smells()` (lines 109-114)
- **Test file**: `scripts/tests/` — existing debt/smell tests

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
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P5

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_history/debt.py` lines 109 and 114 confirm: line 109 sets `total_dirs = len(all_directories) if all_directories else 1` (guarantees total_dirs >= 1), and line 114 still has `scatter_score = len(dirs) / total_dirs if total_dirs > 0 else 0.0` (the else branch is unreachable by construction). Enhancement not yet applied.
