---
id: ENH-288
type: ENH
title: Thread config-sourced exclude_patterns into get_untracked_files()
status: open
priority: P3
testable: false
program_design_not_applicable: true
behavior_parity_not_applicable: true
---

# ENH-288: Thread config-sourced exclude_patterns into get_untracked_files()

## Summary

`get_untracked_files()` currently has no way to exclude paths a caller wants filtered
out before the gitignore suggestion is generated. Thread a config-sourced
`exclude_patterns` list into `get_untracked_files()` so callers can supply their own
exclusion set instead of relying on the default untracked-file scan.

## Current Behavior

`get_untracked_files()` takes no exclusion argument and returns every untracked path
in the repository.

## Expected Behavior

`get_untracked_files()` accepts an `exclude_patterns` list and omits any untracked path
matching one of those patterns from its result.

## Proposed Solution

Add an `exclude_patterns: list[str] | None = None` parameter to `get_untracked_files()`
and filter the returned paths against it before the result is handed back to the
caller.

## Integration Map

### Files to Modify
- `scripts/little_loops/git_operations.py` — add the `exclude_patterns` parameter to
  `get_untracked_files()` and apply the filter.

### Tests
- `scripts/tests/test_git_operations.py` — add coverage for the new
  `exclude_patterns` parameter.

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Status

**Open** | Created: 2026-08-20 | Priority: P3
