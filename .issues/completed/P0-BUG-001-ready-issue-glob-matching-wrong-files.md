# BUG-001: ready_issue Glob Matching Finds Wrong Files

## Summary

The `ready_issue` command uses loose glob pattern matching (`*$ISSUE_ID*.md`) which can match unintended issue files when IDs have overlapping patterns.

## Current Behavior

When `ready_issue ENH-1` is called, the search pattern `*ENH-1*.md` may match:
- `issue-enh-01-conflicting-quality-scores.md` (contains "enh-0")
- Any other file with similar substring patterns

This leads to `ready_issue` validating and closing the **wrong issue file**, while the intended issue remains unprocessed.

### Evidence from Log

```
Processing: ENH-1 - O(n^2) Nested Loop in Anti-Pattern Detection
...
ready_issue verdict: CLOSE
Evidence: ENH-1 (issue-enh-01-conflicting-quality-scores.md) was already fixed
...
Used git mv to move P1-perf-antipattern-nested-loop
```

The queue intended to process "O(n^2) Nested Loop" but `ready_issue` found and closed "Conflicting Quality Scores" instead.

## Expected Behavior

`ready_issue` should:
1. Use strict ID matching, not substring matching
2. Match IDs exactly (e.g., `BUG-001` should not match `BUG-0010`)
3. Return an error if the exact ID cannot be found

## Root Cause

In `commands/ready_issue.md`, the file search uses:
```bash
FILE=$(ls "$dir"*"$ISSUE_ID"*.md 2>/dev/null | head -1)
```

This glob pattern is too loose and matches any file containing the ID as a substring.

## Affected Files

- `commands/ready_issue.md:32` - File search pattern

## Reproduction Steps

1. Have two issue files with similar ID patterns:
   - `.issues/bugs/P1-BUG-1-foo.md`
   - `.issues/bugs/P1-BUG-10-bar.md`
2. Run `/ll:ready-issue BUG-1`
3. Observe that BUG-10 may be matched and processed instead

## Proposed Fix

Use word-boundary or exact pattern matching:

```bash
# Option 1: Use regex with grep
FILE=$(find "$dir" -name "*.md" | grep -E "(^|[^0-9])$ISSUE_ID([^0-9]|$)" | head -1)

# Option 2: More strict glob with delimiter
FILE=$(ls "$dir"*"-${ISSUE_ID}-"*.md "$dir"*"-${ISSUE_ID}."*.md 2>/dev/null | head -1)
```

## Impact

- **Severity**: Critical (P0)
- **Effort**: Low
- **Risk**: Low
- **Breaking Change**: No

## Labels

`bug`, `critical`, `ready_issue`, `automation`

---

## Status

**Completed** | Created: 2026-01-04 | Priority: P0 | Completed: 2026-01-05

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-05
- **Status**: Completed

### Changes Made
- `commands/ready_issue.md:32-34`: Replaced loose glob pattern with strict boundary matching using `find` + `grep -E "[-_]${ISSUE_ID}[-_.]"`
- `commands/manage_issue.md:48-52`: Applied same fix for consistency

### Verification Results
- Tests: PASS (238/238)
- Lint: PASS (pre-existing unrelated warnings only)
- Pattern Testing: Confirmed BUG-1 no longer matches BUG-10 or BUG-100
