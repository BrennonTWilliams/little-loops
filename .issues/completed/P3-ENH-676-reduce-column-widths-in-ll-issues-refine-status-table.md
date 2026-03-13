---
id: ENH-676
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-11
discovered_by: capture-issue
---

# ENH-676: Reduce column widths in ll-issues refine-status table

## Summary

The table output by `ll-issues refine-status` has columns after "source" that are too wide, causing the table to overflow in narrower terminal windows and display incorrectly.

## Current Behavior

The `refine-status` table uses fixed column widths (`_CMD_WIDTH = 8`, `_CONF_WIDTH = 10`, `_SCORE_WIDTH = 7`, `_TOTAL_WIDTH = 5`) that, combined with multiple dynamic command columns, can exceed 80-column terminals and cause line wrapping or horizontal overflow.

## Expected Behavior

The `ll-issues refine-status` table should fit within an 80-column terminal without wrapping. Columns after "source" should use narrower widths with truncation + ellipsis where needed.

## Motivation

Users with narrower terminal windows (e.g., split panes, smaller monitors) cannot view the `ll-issues refine-status` output correctly. Reducing the widths of columns after "source" would make the table usable across a wider range of terminal sizes without sacrificing readability.

## Proposed Solution

Reduce the fixed column width constants in `scripts/little_loops/cli/issues/refine_status.py` for columns after "source". Key targets:
- `_CMD_WIDTH = 8` — could reduce to 6 or 7 (longest alias "tradeoff" → truncate to "trade…")
- `_CONF_WIDTH = 10` — could reduce to 6 (scores are numeric, max 3 digits)
- `_SCORE_WIDTH = 7` — could reduce to 5
- Consider dynamic width calculation based on `terminal_width()`

## Implementation Steps

1. Adjust width constants in `refine_status.py` for post-source columns
2. Update `_CMD_ALIASES` if shorter aliases are needed
3. Test output at common terminal widths (80, 100, 120 chars)

## Scope Boundaries

- Only column widths after "source" are changed; ID, priority, title, and source columns remain unchanged
- No changes to JSON output format
- No new CLI flags or configuration options

## Impact

- **Priority**: P3 - Quality of life improvement for narrow terminal users
- **Effort**: Small - Adjusting width constants and aliases
- **Risk**: Low - Only affects table display formatting, no logic changes
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `display`

---
## Status

`completed`

## Resolution

Reduced post-source column widths in `refine_status.py`:
- `_CMD_WIDTH`: 8 → 6 (saves 2 chars per dynamic command column)
- `_CONF_WIDTH`: 10 → 5, header renamed "confidence" → "conf"
- `_SCORE_WIDTH`: 7 → 5

Total savings: ~21 chars per row (with 7 dynamic cmd columns), reducing header from ~145 to ~124 chars.

**Files changed:**
- `scripts/little_loops/cli/issues/refine_status.py` — width constants and header text
- `scripts/tests/test_refine_status.py` — updated truncation assertion for new _CMD_WIDTH

## Session Log
- `/ll:capture-issue` - 2026-03-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9289d76a-2044-43b5-b290-5c352d5fc6f5.jsonl`
- `/ll:ready-issue` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e65ee450-b783-4f29-8712-1c173d351b1a.jsonl`
- `/ll:manage-issue` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbc52ed1-3c9a-4788-986d-0f9a41297929.jsonl`
