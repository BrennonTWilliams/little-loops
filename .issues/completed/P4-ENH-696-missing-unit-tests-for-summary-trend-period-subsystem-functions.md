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
- `_calculate_trend`: zero denominator (defensive guard at line 191), all-equal values (slope=0 → stable), two-element list (< 3 guard returns "stable")
- `_analyze_subsystems`: "degrading" trend (recent_ratio > 0.5), "improving" trend (< 0.2) — **only triggered when `total_issues >= 5`; entries with fewer issues always return `trend="stable"`**

Note: the existing `TestCalculateAnalysis` in `test_issue_history_analysis.py` uses only 2 issues in one period so `_calculate_trend` is never reached (guard: `len(period_metrics) >= 3`), and `_analyze_subsystems` is always bypassed because test issue files don't exist on disk.

## Expected Behavior

Dedicated unit tests for each function covering boundary conditions and edge cases.

## Implementation Steps

1. In `test_issue_history_summary.py`, add import: `from little_loops.issue_history.summary import _group_by_period, _calculate_trend, _analyze_subsystems` (functions are private and not re-exported from `__init__`)
2. Add `TestGroupByPeriod` with cases:
   - Normal quarter (e.g., `date(2026, 7, 15)` → Q3 period start `date(2026, 7, 1)`)
   - Dec-to-Jan quarterly wrap: issue in December → Q4 start `date(2026, 10, 1)`, end `date(2026, 12, 31)`
   - Single monthly period with no dates (empty list → returns `[]`)
3. Add `TestCalculateTrend` with cases:
   - Ascending trend: `[1.0, 2.0, 3.0]` → `"increasing"` (normalized slope ≈ 0.33 > 0.05 threshold)
   - Descending trend: `[3.0, 2.0, 1.0]` → `"decreasing"`
   - Flat / all-equal: `[2.0, 2.0, 2.0]` → `"stable"` (slope = 0)
   - Two-element list: `[1.0, 2.0]` → `"stable"` (short-series guard at line 179)
   - Near-zero normalized slope (within ±0.05): `[1.0, 1.02, 1.01]` → `"stable"`
4. Add `TestAnalyzeSubsystems` with cases:
   - Use the `contents=` dict shortcut to avoid filesystem I/O: `contents={issue.path: "**File**: `scripts/foo/`\n..."}`
   - Degrading (>0.5 recent, ≥5 issues): `recent_issues=4, total_issues=6` → `trend="degrading"`
   - Improving (<0.2 recent, ≥5 issues): `recent_issues=0, total_issues=5` → `trend="improving"`
   - Below minimum-sample gate: 4 issues → `trend="stable"` regardless of ratio
5. Run `python -m pytest scripts/tests/test_issue_history_summary.py -v` to confirm all pass

## Integration Map

### Files to Modify
- `scripts/tests/test_issue_history_summary.py` — add three new test classes after existing `TestSubsystemHealth` (line 284)

### Files Under Test
- `scripts/little_loops/issue_history/summary.py:84` — `_group_by_period(issues, period_type="monthly") -> list[PeriodMetrics]`
- `scripts/little_loops/issue_history/summary.py:170` — `_calculate_trend(values: list[float]) -> str`
- `scripts/little_loops/issue_history/summary.py:208` — `_analyze_subsystems(issues, recent_days=30, contents=None) -> list[SubsystemHealth]`

### Dependent Files (Sole Caller)
- `scripts/little_loops/issue_history/analysis.py:34–37` — imports and calls all three functions; `_calculate_trend` called at lines 101 and 109; `_group_by_period` at line 96; `_analyze_subsystems` at line 114

### Similar Patterns (Test File Conventions)
- `scripts/tests/test_issue_history_summary.py:104` — `TestCalculateSummary` class: inline `CompletedIssue` construction, no shared fixtures, no filesystem
- `scripts/tests/test_issue_history_advanced_analytics.py:9` — import pattern for private functions: import directly from the defining module
- Float assertions use direct `==` equality (not `pytest.approx`) — see `test_issue_history_summary.py:72`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`_group_by_period` quarterly logic** (`summary.py:112–114`): `quarter = (month - 1) // 3`; period start = `date(year, quarter * 3 + 1, 1)`. December → quarter 3 → start Oct 1. Period end wraps: `month + 3 = 13 > 12` → `month=1, year+=1`, giving `date(year+1,1,1) - 1 day = Dec 31`.
- **`_calculate_trend` thresholds** (`summary.py:201–205`): `±0.05` applied to `slope / mean` (normalized). Zero denominator (line 191) is a defensive guard; for n≥3 with distinct x-indices it can't occur in practice.
- **`_analyze_subsystems` minimum gate** (`summary.py:247`): `if health.total_issues >= 5` — entries with fewer issues keep the default `trend="stable"` without ratio check.
- **`contents=` dict shortcut**: pass `contents={issue.path: "**File**: \`path/to/dir/\`\n..."}` to avoid filesystem I/O in tests. `get_issue_content()` (`_utils.py:10`) reads from the dict first.
- **`SubsystemHealth` subsystem extraction**: uses `_extract_subsystem(content)` from `parsing.py:240` — regex matches `**File**: path/to/` or backtick inline code paths.

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
- `/ll:ready-issue` - 2026-03-18T01:55:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/563cdf30-9834-4792-8bfb-d565756ce86d.jsonl`
- `/ll:refine-issue` - 2026-03-18T01:38:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad925013-dacd-4dcc-85ed-4adc51ee8ed9.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Completed** | Created: 2026-03-13 | Priority: P4

## Resolution

- Added `TestGroupByPeriod` (6 cases): empty list, undated issues, monthly period start, quarterly period start, Dec→Q4 quarterly wrap (period_end=Dec 31), Dec monthly wrap
- Added `TestCalculateTrend` (7 cases): ascending/descending/flat values, short series (<3), single element, empty, near-zero normalized slope within ±0.05 threshold
- Added `TestAnalyzeSubsystems` (4 cases): degrading trend (recent_ratio>0.5, ≥5 issues), improving trend (recent_ratio<0.2, ≥5 issues), below-minimum gate stays stable, missing content skips issue
- All 41 tests in `test_issue_history_summary.py` pass

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_history/summary.py` lines 183-192 confirm the manual OLS regression in `_calculate_trend` (sum_x, sum_y, sum_xy, sum_x2). The referenced functions `_group_by_period`, `_calculate_trend`, and `_analyze_subsystems` exist. Checking test coverage is infeasible without running the test suite, but the functions are internal helpers with no dedicated test class names found in search. Enhancement is valid as described.
