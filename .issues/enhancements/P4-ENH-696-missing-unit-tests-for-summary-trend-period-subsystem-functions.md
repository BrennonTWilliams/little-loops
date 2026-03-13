---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-696: Missing unit tests for `_group_by_period`, `_calculate_trend`, and `_analyze_subsystems`

## Summary

Three internal functions in `issue_history/summary.py` have no direct unit tests: `_group_by_period` (quarterly month-wrap logic), `_calculate_trend` (linear regression with edge cases), and `_analyze_subsystems` (trend thresholds).

## Motivation

These functions contain non-trivial logic (date math, floating-point regression, threshold comparisons) that is only exercised indirectly. Edge cases like Dec-to-Jan wrap and zero-denominator regression are invisible to the current test suite, making regressions possible without detection. They are only exercised indirectly through integration tests with small fixtures that don't cover edge cases.

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

## Implementation Steps

1. In `test_issue_history_summary.py`, add `TestGroupByPeriod` with cases: normal quarter, Dec-to-Jan wrap, single month
2. Add `TestCalculateTrend` with cases: ascending trend, descending, flat, two-element list, zero denominator (all equal values)
3. Add `TestAnalyzeSubsystems` with cases: "degrading" (recent_ratio > 0.5), "improving" (< 0.2), neutral
4. Run `python -m pytest scripts/tests/test_issue_history_summary.py` to confirm all pass

## Integration Map

- **Modified**: `scripts/tests/test_issue_history_summary.py` — add three new test classes
- **Under test**: `scripts/little_loops/issue_history/summary.py` — `_group_by_period()`, `_calculate_trend()`, `_analyze_subsystems()`

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
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_history/summary.py` lines 183-192 confirm the manual OLS regression in `_calculate_trend` (sum_x, sum_y, sum_xy, sum_x2). The referenced functions `_group_by_period`, `_calculate_trend`, and `_analyze_subsystems` exist. Checking test coverage is infeasible without running the test suite, but the functions are internal helpers with no dedicated test class names found in search. Enhancement is valid as described.
