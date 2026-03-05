---
discovered_date: 2026-03-05
discovered_by: manual
completed_date: 2026-03-05
---

# ENH-596: Colorize ll-issues refine-status output

## Summary

Applied ANSI color to `ll-issues refine-status` table output, bringing it in line with `ll-issues list` color conventions. Issue IDs, priority labels, norm/fmt checkmarks, and command hit/miss marks are now colored consistently.

## Context

`ll-issues list` already colorized issue IDs (`TYPE_COLOR`) and priority labels (`PRIORITY_COLOR`) via `colorize()` from `output.py`. `refine-status` only imported `terminal_width` — its table output was entirely plain text. The goal was visual consistency between the two commands.

## Changes Made

### Single file modified: `scripts/little_loops/cli/issues/refine_status.py`

**Import** (line 9):
- Extended from `terminal_width` only to `PRIORITY_COLOR, TYPE_COLOR, colorize, terminal_width`

**`_apply_cell_color()` helper** (new function after `_rcol`):
- Colorizes the visible content of a padded cell while preserving surrounding whitespace so column alignment is unaffected by ANSI escape sequences
- `id` column: `TYPE_COLOR` (BUG=orange, FEAT=green, ENH=blue)
- `priority` column: `PRIORITY_COLOR` (P0–P5 scale)
- `norm`/`fmt` columns: ✓ green (`"32"`), ✗ red (`"31"`)
- All other columns: returned unchanged

**`_build_row()` — pre_cmd and post_cmd loops**:
- Extract plain value first via `_cell_value()`, then pass through `_apply_cell_color()` before appending

**`_build_row()` — all_cmds loop** (dynamic command columns):
- ✓ hits colorized green (`"32"`) with trailing padding preserved
- `—` misses dimmed (`"2"`) with trailing padding preserved
- `/ll:refine-issue` count column left as plain text (unchanged)

## Verification

- All 56 tests pass (`test_cli_output.py` + `test_issues_cli.py`)
- Color suppressed automatically when piped or `NO_COLOR` set (via existing `_USE_COLOR` guard in `output.py`)
- JSON output path (`--format json`) unaffected
- Header and separator rows remain uncolored
- Column alignment preserved (ANSI codes injected only into visible content, padding kept outside)

## Files Modified

- `scripts/little_loops/cli/issues/refine_status.py`
