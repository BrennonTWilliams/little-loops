---
discovered_date: 2026-03-07
discovered_by: capture-issue
---

# BUG-647: ll-issues refine-status ID column truncates 4-digit FEAT IDs

## Summary

The `ll-issues refine-status` output table has a character cutoff in the `ID` column that truncates issue IDs with 4-digit numbers, e.g. showing `FEAT-888` instead of `FEAT-8885`.

## Current Behavior

When displaying the `refine-status` table, the `ID` column is too narrow to display 4-digit issue numbers for FEAT-type issues. The ID is cut off, resulting in truncated output like `FEAT-888` instead of the correct `FEAT-8885`.

## Expected Behavior

The `ID` column should be wide enough to display the full issue ID regardless of the number of digits (e.g., `FEAT-8885`, `BUG-1234`).

## Root Cause

- **File**: `scripts/little_loops/cli/issues/refine_status.py`
- **Anchor**: `_ID_WIDTH = 8` constant (line 18)
- **Cause**: `_ID_WIDTH` is hardcoded to 8 characters, sized for 3-digit IDs like `BUG-525` (7 chars + 1 space). 4-digit IDs like `FEAT-8885` require 9+ characters and are silently truncated by `_col()`/`_rcol()`, which call `str.ljust(width)[:width]`.

## Proposed Solution

Change `_ID_WIDTH` in `scripts/little_loops/cli/issues/refine_status.py` to compute dynamically based on the longest ID in the dataset. In `render_refine_status()` (or its table-building helper), replace the hardcoded constant with:

```python
# Dynamic: size to longest ID in dataset
id_width = max((len(issue.id) for issue in issues), default=8) + 1
```

Alternatively, raise the constant to safely cover 4-digit IDs:

```python
_ID_WIDTH = 10  # "FEAT-8885 " (9 chars + 1 space buffer)
```

Dynamic computation is preferred to satisfy the Acceptance Criterion that column width adapts to the longest ID present.

## Steps to Reproduce

1. Have issues with 4-digit IDs (e.g., `FEAT-8885`)
2. Run `ll-issues refine-status`
3. Observe the `ID` column shows `FEAT-888` instead of `FEAT-8885`

## Implementation Steps

1. Locate the `refine-status` table rendering code in `scripts/little_loops/`
2. Find the column width definition for the `ID` column
3. Change to dynamic width based on the longest ID in the dataset, or set a minimum width of 9+ characters
4. Add a test with a 4-digit ID to verify the fix

## Acceptance Criteria

- [x] `ll-issues refine-status` displays full 4-digit IDs without truncation
- [x] No regression on 3-digit IDs
- [x] Column width adapts dynamically to the longest ID present

## Impact

- **Priority**: P4 — Minor display defect; affects usability when issue IDs reach 4 digits but no data is lost
- **Effort**: Small — Single constant change or ~5 lines for dynamic width computation
- **Risk**: Low — Isolated to display/rendering code in `refine_status.py`; no business logic affected
- **Breaking Change**: No

## Labels

`bug`, `cli`, `display`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | ll-issues CLI module reference |

---

**Resolved** | Created: 2026-03-07 | Completed: 2026-03-07 | Priority: P4

## Resolution

Replaced the hardcoded `_ID_WIDTH = 8` constant with a dynamic `id_width` computed after loading issues (`max(len(issue.issue_id) for issue in sorted_issues, default=7) + 1`). Updated `_get_col_display_width` and `non_title_sum` to use the dynamic value for the "id" column. Added `test_four_digit_id_not_truncated` to verify 4-digit IDs render without truncation.

## Session Log
- `/ll:capture-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/69a8a736-8424-4274-aa7b-653c573032d9.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/586bf7cd-9211-4392-9982-c36e05d1d906.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e340dabc-5139-4758-9790-7ea74b66074f.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fca1aa28-f7da-4572-b504-68da169949a5.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
