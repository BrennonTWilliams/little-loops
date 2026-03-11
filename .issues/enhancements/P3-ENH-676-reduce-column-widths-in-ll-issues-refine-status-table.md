---
id: ENH-676
type: ENH
priority: P3
status: backlog
discovered_date: 2026-03-11
discovered_by: capture-issue
---

# ENH-676: Reduce column widths in ll-issues refine-status table

## Problem Statement

The table output by `ll-issues refine-status` has columns after "source" that are too wide, causing the table to overflow in narrower terminal windows and display incorrectly.

## Motivation

Users with narrower terminal windows (e.g., split panes, smaller monitors) cannot view the `ll-issues refine-status` output correctly. Reducing the widths of columns after "source" would make the table usable across a wider range of terminal sizes without sacrificing readability.

## Proposed Solution

Reduce the maximum column widths for the columns that appear after "source" in the `refine-status` table output. This likely involves adjusting column width constants or truncation logic in the relevant rendering code.

## Implementation Steps

1. Locate the `refine-status` command implementation in `scripts/little_loops/`
2. Identify the column definitions/widths for columns after "source"
3. Reduce the max widths for those columns (with truncation + ellipsis if needed)
4. Test the output at common terminal widths (80, 100, 120 chars)

## Acceptance Criteria

- The `ll-issues refine-status` table fits within an 80-column terminal without wrapping
- Columns after "source" display truncated content with ellipsis when values exceed the new limits
- No data is lost — full values accessible via other means (e.g., `ll-issues show`)

---
## Status

`backlog`

## Session Log
- `/ll:capture-issue` - 2026-03-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9289d76a-2044-43b5-b290-5c352d5fc6f5.jsonl`
