# BUG-001: ready_issue Glob Matching Finds Wrong Files - Management Plan

## Issue Reference
- **File**: .issues/bugs/P0-BUG-001-ready-issue-glob-matching-wrong-files.md
- **Type**: bug
- **Priority**: P0
- **Action**: fix

## Problem Analysis

### Root Cause
The issue ID search uses loose substring matching with glob patterns:
- `ready_issue.md:32`: `FILE=$(ls "$dir"*"$ISSUE_ID"*.md 2>/dev/null | head -1)`
- `manage_issue.md:50`: `ISSUE_FILE=$(find "$SEARCH_DIR" -name "*$ISSUE_ID*.md" | head -1)`

This means `BUG-1` matches `BUG-10`, `BUG-100`, etc. and `ENH-1` matches `issue-enh-01-...`.

### Impact
- Wrong issues get validated/closed
- Automation processes incorrect files
- Data integrity compromised

## Solution Approach

Use stricter pattern matching that respects word boundaries. The issue ID format is:
- Pattern: `{PREFIX}-{NUMBER}` (e.g., `BUG-001`, `ENH-1`, `FEAT-42`)
- Issue files typically have format: `P{N}-{ID}-{title}.md`

The fix should ensure that when searching for `BUG-1`, it doesn't match `BUG-10` or `BUG-100`.

### Solution: Word-boundary matching with grep

Instead of glob-based substring matching, use grep with regex word boundaries:
```bash
# Match ID followed by non-digit or end of name
FILE=$(find "$dir" -name "*.md" 2>/dev/null | grep -E "[-_]${ISSUE_ID}[-_.]" | head -1)
```

This ensures the ID is surrounded by delimiters (-, _, or .) rather than being a substring of a larger number.

## Implementation Phases

### Phase 1: Fix ready_issue.md
**File**: commands/ready_issue.md
**Line**: 32
**Change**: Replace loose glob with strict boundary matching

### Phase 2: Fix manage_issue.md
**File**: commands/manage_issue.md
**Line**: 50
**Change**: Replace loose find pattern with strict boundary matching

## Verification Plan

1. The fix is in markdown command files (documentation/templates), not executable code
2. Verify the pattern logic is correct by testing with example filenames
3. Ensure both files have consistent patterns
