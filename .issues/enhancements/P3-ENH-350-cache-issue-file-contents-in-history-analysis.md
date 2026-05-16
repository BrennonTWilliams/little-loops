---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan-codebase
---

# ENH-350: Cache issue file contents in issue_history analysis pipeline

## Summary

The `calculate_analysis()` pipeline calls 9 analysis functions sequentially, each independently reading every issue file from disk via `issue.path.read_text()`. For N completed issues, this results in ~9N file reads for the same files.

## Location

- **File**: `scripts/little_loops/issue_history/analysis.py` (refactored from `issue_history.py` into package)
- **Line(s)**: 263, 309, 423, 558, 771, 950, 1038, 1272, 1383 (`read_text()` calls)
- **Anchor**: `_analyze_subsystems`, `analyze_hotspots`, `analyze_coupling`, `analyze_regression_clustering`, `analyze_rejection_rates`, `detect_manual_patterns`, `detect_cross_cutting_smells`, `analyze_agent_effectiveness`, `analyze_complexity_proxy`

## Current Behavior

Each analysis function independently reads every issue file from disk. With 9 analysis functions and N issues, this is ~9N file reads.

## Expected Behavior

Issue file contents are read once and passed to each analysis function, reducing I/O from ~9N to N reads.

## Motivation

Performance improvement for projects with many completed issues. Reading the same files 9 times is wasteful.

## Proposed Solution

Add a `_load_issue_contents(issues: list[CompletedIssue]) -> dict[str, str]` helper in `analysis.py`. Modify each of the 9 analysis functions (`_analyze_subsystems`, `analyze_hotspots`, `analyze_coupling`, `analyze_regression_clustering`, `analyze_rejection_rates`, `detect_manual_patterns`, `detect_cross_cutting_smells`, `analyze_agent_effectiveness`, `analyze_complexity_proxy`) to accept an optional `contents` parameter. Update `calculate_analysis()` to pre-load and pass through.

## Scope Boundaries

- Only cache within a single `calculate_analysis()` call, not across calls
- Do not change the public API of individual analysis functions

## Success Metrics

- File reads reduced from ~9N to N
- All existing tests pass

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/analysis.py`

### Tests
- `scripts/tests/test_issue_history_analysis.py`
- `scripts/tests/test_issue_history_advanced_analytics.py`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `_load_issue_contents()` helper in `analysis.py`
2. Update 9 analysis functions to accept optional `contents` parameter
3. Wire through `calculate_analysis()` to pre-load and pass contents

## Impact

- **Priority**: P3 - Performance improvement
- **Effort**: Medium - Touch multiple functions in large module
- **Risk**: Low - Read-only optimization
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `captured`

## Blocks

_None — ENH-351 closed (won't-fix)._

## Session Log
- `/ll:scan-codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`


## Verification Notes

- **Verified**: 2026-02-14
- **Verdict**: CORRECTED (ready-issue)
- **Module refactored**: `issue_history.py` was split into `issue_history/` package; analysis functions now in `analysis.py`
- **Line numbers updated**: `read_text()` calls at lines 263, 309, 423, 558, 771, 950, 1038, 1272, 1383 in `analysis.py`
- **Scope corrected**: 9 analysis functions read from disk (was "5+" in original)
- **Test files updated**: Multiple test files exist after refactor
- Core issue remains valid — 9 independent `issue.path.read_text()` calls for the same files in `calculate_analysis()`

## Resolution

- **Status**: Completed
- **Action**: improve
- **Date**: 2026-02-14

### Changes Made

- Added `_load_issue_contents()` helper function that pre-loads all issue file contents into a `dict[Path, str]` cache
- Updated 9 analysis functions to accept optional `contents: dict[Path, str] | None = None` parameter
- Wired `calculate_analysis()` to pre-load contents once and pass to all analysis functions
- File reads reduced from ~9N to N (where N = number of completed issues)
- No public API changes — all new parameters are optional with `None` defaults

### Files Modified

- `scripts/little_loops/issue_history/analysis.py` — Added `_load_issue_contents()`, updated 9 function signatures and their file-reading logic, updated `calculate_analysis()` orchestration

### Verification

- All 2743 tests pass
- mypy type checking passes
- ruff linting passes

---

**Completed** | Created: 2026-02-12 | Completed: 2026-02-14 | Priority: P3
