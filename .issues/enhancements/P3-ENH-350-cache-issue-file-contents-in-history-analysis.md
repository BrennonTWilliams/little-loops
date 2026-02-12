---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# ENH-350: Cache issue file contents in issue_history analysis pipeline

## Summary

The `calculate_analysis()` pipeline calls 5+ analysis functions sequentially, each independently reading every issue file from disk via `issue.path.read_text()`. For N completed issues, this results in ~5N file reads for the same files.

## Location

- **File**: `scripts/little_loops/issue_history.py`
- **Line(s)**: 1388-1391, 1434-1437, 1548-1551, 1684-1686, 1897-1899 (at scan commit: be30013)
- **Anchor**: `_analyze_subsystems`, `analyze_hotspots`, `analyze_coupling`, `analyze_regression_clustering`, `analyze_rejection_rates`

## Current Behavior

Each analysis function independently reads every issue file from disk. With 5 analysis functions and N issues, this is ~5N file reads.

## Expected Behavior

Issue file contents are read once and passed to each analysis function, reducing I/O to N reads.

## Motivation

Performance improvement for projects with many completed issues. Reading the same files 5 times is wasteful.

## Proposed Solution

Add a `_load_issue_contents(issues: list[CompletedIssue]) -> dict[str, str]` helper. Modify each analysis function to accept an optional `contents` parameter. Update `calculate_analysis()` to pre-load and pass through.

## Scope Boundaries

- Only cache within a single `calculate_analysis()` call, not across calls
- Do not change the public API of individual analysis functions

## Success Metrics

- File reads reduced from ~5N to N
- All existing tests pass

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history.py`

### Tests
- `scripts/tests/test_issue_history.py`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add content loading helper function
2. Update analysis functions to accept cached contents
3. Wire through `calculate_analysis()`

## Impact

- **Priority**: P3 - Performance improvement
- **Effort**: Medium - Touch multiple functions in large module
- **Risk**: Low - Read-only optimization
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`


---

**Open** | Created: 2026-02-12 | Priority: P3
