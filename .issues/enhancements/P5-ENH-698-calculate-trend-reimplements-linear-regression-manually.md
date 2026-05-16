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

1. In `summary.py:183-192`, replace the `sum_x/sum_y/sum_xy/sum_x2` OLS accumulation and `denominator` guard with `statistics.linear_regression(range(n), values).slope`
2. Preserve the existing `len(values) < 3` guard at line 179 — the current code returns `"stable"` for fewer than 3 points (stricter than stdlib's minimum of 2), and both callers in `analysis.py` already pre-guard with `>= 3`. Do **not** relax to `< 2`.
3. Preserve the normalization block at lines 196-199: `avg = sum_y / n`, clamp `avg` to `1` if zero, then `normalized_slope = slope / avg` — the stdlib only replaces the slope computation, not this scale-invariant normalization.
4. Remove the now-unreachable `denominator == 0` guard (lines 189-191) — it guards against all-identical x-values which is structurally impossible for `range(n)` with `n >= 3`.
5. Add `import statistics` at the top of `summary.py` (no other file in the codebase currently imports `statistics`).
6. Run `python -m pytest scripts/tests/test_issue_history_summary.py scripts/tests/test_issue_history_analysis.py -v` to verify identical output.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/summary.py` — `_calculate_trend()` (lines 170-205): replace OLS block with `statistics.linear_regression(range(n), values).slope`; add `import statistics`

### Dependent Files (Callers)
- `scripts/little_loops/issue_history/analysis.py:36` — imports `_calculate_trend` from `summary`
- `scripts/little_loops/issue_history/analysis.py:99-103` — calls `_calculate_trend(velocities)` for velocity trend (pre-guarded with `len >= 3`)
- `scripts/little_loops/issue_history/analysis.py:106-111` — calls `_calculate_trend(bug_ratios)` for bug ratio trend (pre-guarded with `len >= 3`)

### Tests
- `scripts/tests/test_issue_history_summary.py` — no direct tests for `_calculate_trend` (private function, tested indirectly via `calculate_summary`); see related ENH-696 for adding direct unit tests
- `scripts/tests/test_issue_history_analysis.py` — integration coverage via `HistoryAnalysis` consumers

### Related Issues
- `ENH-696` — adds missing unit tests for `_calculate_trend` and related subsystem functions; consider implementing ENH-696 alongside or after this change

### Stdlib Dependency
- `statistics.linear_regression` — Python 3.11+, the project's minimum version; not currently imported anywhere in the codebase

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
- `/ll:ready-issue` - 2026-03-18T02:05:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6618b8a4-13a3-47ea-9b53-ed66c3a5df37.jsonl`
- `/ll:refine-issue` - 2026-03-18T01:39:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad925013-dacd-4dcc-85ed-4adc51ee8ed9.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

## Resolution

- Replaced manual OLS accumulation (`sum_x`, `sum_y`, `sum_xy`, `sum_x2`) with `statistics.linear_regression(range(n), values).slope`
- Added `import statistics` at top of `summary.py`
- Removed now-unreachable `denominator == 0` guard
- Preserved `len(values) < 3` short-circuit and normalization block unchanged
- All 50 tests pass (`test_issue_history_summary.py` + `test_issue_history_analysis.py`)

---

**Completed** | Created: 2026-03-13 | Completed: 2026-03-17 | Priority: P5

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_history/summary.py` lines 183-192 confirm the manual OLS computation using `sum_x`, `sum_y`, `sum_xy`, `sum_x2` is present in `_calculate_trend`. `statistics.linear_regression` is not imported or used. Python 3.11+ is the project minimum. Enhancement not yet applied.
