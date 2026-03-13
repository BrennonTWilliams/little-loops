---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-698: `_calculate_trend` reimplements linear regression when `statistics.linear_regression` available

## Summary

`_calculate_trend` manually computes the OLS slope using four intermediate sums. Python 3.11+ (the project's minimum version) provides `statistics.linear_regression()` which returns a `LinearRegression(slope, intercept)` named tuple and handles the zero-denominator case internally.

## Location

- **File**: `scripts/little_loops/issue_history/summary.py`
- **Line(s)**: 169-204 (at scan commit: 3e9beea)
- **Anchor**: `in function _calculate_trend()`

## Current Behavior

Manual summation of `sum_x`, `sum_y`, `sum_xy`, `sum_x2` to compute OLS slope. Works correctly but duplicates stdlib logic.

## Expected Behavior

Delegate slope computation to `statistics.linear_regression(range(n), values).slope`.

## Scope Boundaries

- Replace manual computation only; keep the same normalization and threshold logic

## Impact

- **Priority**: P5 - Code simplification, no correctness issue
- **Effort**: Small - Replace ~10 lines with stdlib call
- **Risk**: Low - stdlib implementation is well-tested
- **Breaking Change**: No

## Labels

`enhancement`, `code-quality`, `issue-history`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P5
