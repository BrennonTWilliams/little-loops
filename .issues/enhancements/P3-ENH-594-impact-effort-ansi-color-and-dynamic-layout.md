---
discovered_date: 2026-03-05T00:00:00Z
discovered_by: manual
---

# ENH-594: Color, Dynamic Layout, and Summary Count for `ll-issues impact-effort`

## Summary

`impact_effort.py` was written without output styling integration. The grid used a hardcoded
`_COL_WIDTH = 20` that never adapted to the terminal and produced purely monochrome output.
This enhancement adds ANSI colorization, dynamic column widths, and a total-issues summary line
using the existing `little_loops.cli.output` infrastructure already used by `list_cmd.py`,
`show.py`, and `loop/info.py`.

## Problem

Before this change:
- Column width was hardcoded to 20 chars regardless of terminal size
- All text rendered in the default terminal color — no distinction between issue types or quadrant urgency
- No summary line — the user had to count issues manually
- ANSI-safe padding pattern was not followed (`.ljust()` on potentially-colorized strings)

## Solution

### Files Modified

1. **`scripts/little_loops/cli/issues/impact_effort.py`**
   - Removed `_COL_WIDTH = 20`; replaced with dynamic formula computed inside `_render_grid`:
     `col_width = max(18, min(38, (terminal_width() - 19) // 2))`
     → 80-col terminal → 30; 120-col → 38 (capped); 56-col → 18 (floor)
   - Added `from little_loops.cli.output import TYPE_COLOR, colorize, terminal_width`
   - Added `_QUADRANT_HEADER_COLOR` dict: bold-green (quick wins), yellow (major projects),
     dim (fill-ins), orange (thankless tasks)
   - Updated `_issue_slug(issue, col_width)` to accept `col_width` as parameter
   - Updated `_render_quadrant_lines(issues, header, header_color, col_width)`:
     - Header: `colorize(header, color) + " " * (col_width - len(header))` — ANSI-safe padding
     - Issue rows: compute `raw` length before colorizing the ID, append trailing spaces manually
   - Updated `_render_grid` to compute `col_width`, pass it to all helpers, and colorize axis labels:
     - "← EFFORT →" rendered bold (`"1"`) with manual centering to avoid `.center()` on ANSI strings
     - "High" column label rendered bold; "Low" stays plain
   - `cmd_impact_effort` now prints `\n  N issues plotted` after the grid

2. **`scripts/tests/test_issues_cli.py`** — Two new tests in `TestIssuesCLIImpactEffort`:
   - `test_impact_effort_no_ansi_when_no_color`: patches `output._USE_COLOR = False`, asserts
     `"\033["` not in captured output — verifies full NO_COLOR compliance
   - `test_impact_effort_shows_total_count`: asserts `"issue"` in output for the summary line

### Key Pattern: ANSI-safe padding

The standard pattern used throughout (matching `show.py` / `list_cmd.py`):
- Calculate padding using `len(plain_text)` — never the colorized string
- Append spaces manually: `colorize(text, code) + " " * (col_width - len(text))`
- Never call `.ljust()` on strings that already contain ANSI codes

## Impact

- **Priority**: P3 — Immediate UX improvement for the impact-effort visualization
- **Effort**: Small — ~40 lines changed in `impact_effort.py`; 2 new tests added
- **Risk**: Low — Purely presentation layer; no changes to quadrant logic or issue parsing
- **Breaking Change**: No — `NO_COLOR=1` and piped output continue to produce clean plain text

## Labels

`enhancement`, `ll-issues`, `ux`, `cli`, `output-styling`

## Session Log

- `manual` — 2026-03-05 — planned and implemented in a single session

---

## Resolution

Replaced hardcoded `_COL_WIDTH = 20` with a dynamic formula capped at `[18, 38]` based on
`terminal_width()`. Added per-quadrant header colors, issue-ID colorization via `TYPE_COLOR`,
bold axis labels, and a total-count summary line. All 6 `TestIssuesCLIImpactEffort` tests pass
including two new tests for NO_COLOR compliance and the summary line.

**Resolved**: 2026-03-05 | manual implementation

---

## Status

**Completed** | Created: 2026-03-05 | Resolved: 2026-03-05 | Priority: P3
