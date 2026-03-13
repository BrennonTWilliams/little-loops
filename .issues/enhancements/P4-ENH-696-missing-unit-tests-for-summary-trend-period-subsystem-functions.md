---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-696: Missing unit tests for `_group_by_period`, `_calculate_trend`, and `_analyze_subsystems`

## Summary

Three internal functions in `issue_history/summary.py` have no direct unit tests: `_group_by_period` (quarterly month-wrap logic), `_calculate_trend` (linear regression with edge cases), and `_analyze_subsystems` (trend thresholds). They are only exercised indirectly through integration tests with small fixtures that don't cover edge cases.

## Location

- **File**: `scripts/little_loops/issue_history/summary.py`
- **Line(s)**: 83-259 (at scan commit: 3e9beea)
- **Anchor**: Functions `_group_by_period`, `_calculate_trend`, `_analyze_subsystems`

## Current Behavior

These functions are only tested indirectly via `calculate_summary` and `calculate_analysis` integration tests. Edge cases not covered:
- `_group_by_period`: Dec-to-Jan quarterly wrap
- `_calculate_trend`: zero denominator, all-equal values, two-element list
- `_analyze_subsystems`: "degrading" trend (recent_ratio > 0.5), "improving" trend (< 0.2)

## Expected Behavior

Dedicated unit tests for each function covering boundary conditions and edge cases.

## Scope Boundaries

- Add tests to `test_issue_history_summary.py` only
- Do not modify the functions themselves

## Impact

- **Priority**: P4 - Improves confidence in correctness of date and trend calculations
- **Effort**: Small - Add 3 test classes with targeted test cases
- **Risk**: Low - Test-only change
- **Breaking Change**: No

## Labels

`enhancement`, `testing`, `issue-history`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
