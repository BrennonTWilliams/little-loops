# BUG-002: ll-auto Does Not Validate ready_issue Target Matches Intended File

## Summary

The `ll-auto` automation moves issue files to `completed/` based on the **original queue entry's filename**, not the file that `ready_issue` actually validated. This causes incorrect files to be moved when `ready_issue` matches the wrong issue.

## Current Behavior

1. `ll-auto` calls `find_highest_priority_issue()` which returns an `IssueInfo` with `path` and `issue_id`
2. `ll-auto` runs `/ll:ready_issue {issue_id}`
3. `ready_issue` finds and validates a **potentially different file** due to loose glob matching (see BUG-001)
4. If `ready_issue` returns CLOSE verdict, `ll-auto` calls `close_issue(info, ...)` using the **original** `info.path`
5. The **original file** gets moved to `completed/`, not the file that `ready_issue` validated

### Evidence from Log

```
Processing: ENH-1 - O(n^2) Nested Loop in Anti-Pattern Detection
[ready_issue validates: issue-enh-01-conflicting-quality-scores.md]
ready_issue verdict: CLOSE (already_fixed)
Used git mv to move P1-perf-antipattern-nested-loop  <-- WRONG FILE
```

The automation moved `P1-perf-antipattern-nested-loop.md` (the original queue entry) instead of the file `ready_issue` actually validated.

## Expected Behavior

`ll-auto` should:
1. Parse `ready_issue` output to extract which file was actually validated
2. Compare with the intended file from the queue
3. If they differ, either:
   - Log an error and skip the issue
   - Or process the correct file

## Root Cause

In `scripts/little_loops/issue_manager.py:278-286`:
```python
if close_issue(
    info,  # <-- Uses original IssueInfo, not what ready_issue found
    config,
    logger,
    parsed.get("close_reason"),
    parsed.get("close_status"),
):
```

The `info` object is from the original queue, not from `ready_issue` output.

## Affected Files

- `scripts/little_loops/issue_manager.py:278-286` - close_issue call
- `scripts/little_loops/parallel/output_parsing.py` - May need to extract validated file path

## Reproduction Steps

1. Set up a project with issue files where IDs can be confused (see BUG-001)
2. Run `ll-auto`
3. Observe that wrong files get moved when ready_issue matches different files

## Proposed Fix

Option A: Add file path to ready_issue output and parse it:
```python
parsed = parse_ready_issue_output(result.stdout)
validated_path = parsed.get("validated_file_path")
if validated_path and validated_path != str(info.path):
    logger.error(f"ready_issue validated {validated_path}, expected {info.path}")
    continue
```

Option B: Have ready_issue return the issue ID it found and compare:
```python
if parsed.get("found_issue_id") != info.issue_id:
    logger.error(f"ID mismatch: found {parsed['found_issue_id']}, expected {info.issue_id}")
```

## Impact

- **Severity**: High (P1)
- **Effort**: Medium
- **Risk**: Low
- **Breaking Change**: No

## Labels

`bug`, `high-priority`, `ll-auto`, `automation`, `data-integrity`

---

## Status

**Open** | Created: 2026-01-04 | Priority: P1

## Related Issues

- [BUG-001](./P0-BUG-001-ready-issue-glob-matching-wrong-files.md) - Root cause of the mismatch

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-05
- **Status**: Completed

### Changes Made

- `commands/ready_issue.md`: Added `## VALIDATED_FILE` section to output format requiring the absolute path of the validated issue file
- `scripts/little_loops/parallel/output_parsing.py`: Added parsing for `VALIDATED_FILE` section, returning `validated_file_path` in results
- `scripts/little_loops/issue_manager.py`: Added path validation after parsing ready_issue output; if the validated file path doesn't match the expected path, logs an error and marks the issue as failed

### Solution Approach

Implemented Option A from the proposed fix: the ready_issue command now outputs a `## VALIDATED_FILE` section containing the absolute path of the file it validated. The issue_manager parses this path and compares it against the expected file path. If they don't match, the issue is marked as failed with a descriptive error message, preventing incorrect file operations.

This provides defense-in-depth alongside the BUG-001 fix (strict ID matching).

### Verification Results

- Tests: PASS (238 passed)
- Lint: PASS (modified source files)
- Types: PASS (no issues in 19 source files)
