# BUG-002: ll-auto No Validation of ready_issue Target - Management Plan

## Issue Reference
- **File**: .issues/bugs/P1-BUG-002-ll-auto-no-validation-of-ready-issue-target.md
- **Type**: bug
- **Priority**: P1
- **Action**: fix

## Problem Analysis

The `ll-auto` automation has a critical data integrity issue:

1. `ll-auto` calls `find_highest_priority_issue()` which returns an `IssueInfo` with a specific file `path`
2. `ll-auto` then runs `/ll:ready-issue {issue_id}` passing only the issue ID
3. If `ready_issue` matches a **different file** (due to loose matching), it validates that different file
4. When `ready_issue` returns CLOSE verdict, `ll-auto` calls `close_issue(info, ...)` using the **original** `info.path`
5. The **wrong file** gets moved to `completed/`

Note: BUG-001 (now fixed) addressed the loose glob matching in `ready_issue`. However, as a defense-in-depth measure, we should still validate that `ready_issue` validated the expected file.

## Solution Approach

Add a `VALIDATED_FILE` section to the `ready_issue` output format that contains the absolute path of the file that was actually validated. Then:

1. Parse this path in `parse_ready_issue_output()`
2. Compare it against the expected path in `_process_issue()`
3. If they don't match, log an error and skip the issue (mark as failed)

This provides defense-in-depth even with BUG-001 fixed.

## Implementation Phases

### Phase 1: Update ready_issue Command Output Format

**Files**: `commands/ready_issue.md`

**Changes**:
- Add `## VALIDATED_FILE` section to output format
- Document that this section must contain the absolute path of the validated issue file
- Add this after the VERDICT section since it's metadata about what was validated

### Phase 2: Update Output Parser

**Files**: `scripts/little_loops/parallel/output_parsing.py`

**Changes**:
- Add parsing for `VALIDATED_FILE` section in `parse_ready_issue_output()`
- Return `validated_file_path` in the result dict
- Handle case where section is missing (backwards compatibility)

### Phase 3: Add Validation to Issue Manager

**Files**: `scripts/little_loops/issue_manager.py`

**Changes**:
- After parsing `ready_issue` output, extract `validated_file_path`
- Compare with `str(info.path)` (resolving to absolute paths)
- If mismatch detected:
  - Log an error with both paths
  - Mark issue as failed with descriptive reason
  - Return False to skip processing

### Phase 4: Add Tests

**Files**: `scripts/tests/test_output_parsing.py`

**Changes**:
- Add test for parsing VALIDATED_FILE section
- Add test for missing section (backwards compat)
- Add test for path extraction

## Verification Plan

1. Run existing tests to ensure no regressions
2. Add unit tests for new parsing logic
3. Run linting and type checking
4. Manual verification with dry-run

## Risks

- **Low risk**: Changes are additive and don't break existing functionality
- **Backwards compatible**: Missing VALIDATED_FILE section is handled gracefully
