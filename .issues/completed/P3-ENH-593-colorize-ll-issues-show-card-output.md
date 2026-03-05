---
discovered_date: 2026-03-05
discovered_by: manual
completed_date: 2026-03-05
effort: S
---

# ENH-593: Colorize ll-issues show card output

## Summary

Added ANSI color to the `ll-issues show` summary card: issue type in the header, priority, status, and risk in the metadata row. Also capped card width to the terminal width to prevent overflow on narrow terminals.

## Context

`show.py` rendered a Unicode box-drawing card with no color, despite `output.py` providing `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR`, and `terminal_width`. The `list_cmd.py` already used all four utilities; `show.py` was the only card renderer that didn't. The card also had no terminal-width cap, so long titles could overflow narrow terminals.

## Changes Made

### 1. Added imports

**File:** `scripts/little_loops/cli/issues/show.py`

- Imported `PRIORITY_COLOR`, `TYPE_COLOR`, `colorize`, `terminal_width` from `little_loops.cli.output`

### 2. Added ANSI-aware padding helpers

**File:** `scripts/little_loops/cli/issues/show.py`

- `_ANSI_RE` — compiled regex matching ANSI escape sequences
- `_strip_ansi(text)` — strips escape codes for accurate `len()` measurement
- `_ljust(text, width)` — left-justifies text accounting for invisible ANSI bytes; used on the header and meta rows

### 3. Terminal width cap in `_render_card`

**File:** `scripts/little_loops/cli/issues/show.py`

- After computing `width` from content, applies `width = min(width, terminal_width() - 4)` to prevent card overflow on narrow terminals

### 4. Colorized header

**File:** `scripts/little_loops/cli/issues/show.py`

- Splits `issue_id` to extract the type token (`BUG`, `FEAT`, `ENH`)
- Wraps the ID in `colorize(issue_id, TYPE_COLOR.get(itype, "0"))` before rendering

### 5. Colorized metadata row

**File:** `scripts/little_loops/cli/issues/show.py`

- Priority → `colorize(priority, PRIORITY_COLOR.get(priority, "0"))`
- Status "Completed" → `colorize("Completed", "32")` (green); "Open" stays plain
- Risk "High" → orange (`38;5;208`), "Medium" → yellow (`33`), "Low" → dim (`2`)
- Plain `meta_line` retained for width calculation; `colored_meta_line` used for rendering

## Color Mapping

| Value | Code |
|-------|------|
| `FEAT` in issue ID | `32` (green) |
| `BUG` in issue ID | `38;5;208` (orange) |
| `ENH` in issue ID | `34` (blue) |
| P0 priority | `38;5;208;1` (bold orange) |
| P1 priority | `38;5;208` (orange) |
| P2 priority | `33` (yellow) |
| P3 priority | `0` (default) |
| P4–P5 priority | `2` (dim) |
| Status: Completed | `32` (green) |
| Risk: High | `38;5;208` (orange) |
| Risk: Medium | `33` (yellow) |
| Risk: Low | `2` (dim) |

## Verification

- All 17 existing `TestIssuesCLIShow` tests pass unchanged (color is suppressed when stdout is not a TTY, so no assertion updates were needed)

## Files Modified

- `scripts/little_loops/cli/issues/show.py`
