---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-698: `_calculate_trend` reimplements linear regression when `statistics.linear_regression` available

## Summary

`_calculate_trend` manually computes the OLS slope using four intermediate sums. Python 3.11+ (the project's minimum version) provides `statistics.linear_regression()` which returns a `LinearRegression(slope, intercept)` named tuple and handles the zero-denominator case internally.

## Motivation

The manual OLS implementation adds 10 lines of boilerplate that must be maintained and tested separately. The stdlib function is well-tested, handles edge cases, and signals intent more clearly to readers unfamiliar with the formula.

## Location

- **File**: `scripts/little_loops/issue_history/summary.py`
- **Line(s)**: 169-204 (at scan commit: 3e9beea)
- **Anchor**: `in function _calculate_trend()`

## Current Behavior

Manual summation of `sum_x`, `sum_y`, `sum_xy`, `sum_x2` to compute OLS slope. Works correctly but duplicates stdlib logic.

## Expected Behavior

Delegate slope computation to `statistics.linear_regression(range(n), values).slope`.

## Implementation Steps

1. In `summary.py`, replace the `sum_x/sum_y/sum_xy/sum_x2` computation in `_calculate_trend` with `statistics.linear_regression(range(n), values).slope`
2. Handle the edge case where `n < 2` (stdlib requires at least 2 points) before calling
3. Run `python -m pytest` to verify identical slope values

## Integration Map

- **Modified**: `scripts/little_loops/issue_history/summary.py` — `_calculate_trend()` (lines 169-204)
- **Stdlib used**: `statistics.linear_regression` (Python 3.11+, already minimum version)

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
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P5

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_history/summary.py` lines 183-192 confirm the manual OLS computation using `sum_x`, `sum_y`, `sum_xy`, `sum_x2` is present in `_calculate_trend`. `statistics.linear_regression` is not imported or used. Python 3.11+ is the project minimum. Enhancement not yet applied.
