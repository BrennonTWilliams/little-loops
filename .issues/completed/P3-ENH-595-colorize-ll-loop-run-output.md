---
discovered_date: 2026-03-05
discovered_by: manual
completed_date: 2026-03-05
---

# ENH-595: Colorize ll-loop run output

## Summary

Applied ANSI color, dynamic terminal-width truncation, and structured visual polish to `ll-loop run` output, bringing it to the same quality level as `ll-issues`, `ll-sprint`, and `ll-loop show`.

## Context

`ll-loop run` used raw `print()` with plain strings, ASCII symbols, and hardcoded 100/120-char truncation limits. The project already had a `cli/output.py` module with `colorize()` and `terminal_width()` utilities used by other commands. This change applied those utilities consistently across all `ll-loop run` output.

## Changes Made

### Single file modified: `scripts/little_loops/cli/loop/_helpers.py`

**Import** (line 12):
- Added `from little_loops.cli.output import colorize, terminal_width`

**`print_execution_plan()`**:
- Plan header bold via `colorize(..., "1")`
- State names bold, `[TERMINAL]` marker in green (`"32"`)
- Shell action truncation uses `terminal_width() - 16` instead of hardcoded `70`
- All transition targets (`->`) dimmed via `colorize(..., "2")`

**`run_background()`**:
- Loop name bold, PID/log path/commands dimmed

**`run_foreground()` header**:
- Loop name bold, max iterations dimmed

**`display_progress()` — all event types**:
- `state_enter`: state name bold, elapsed time dimmed; line truncation uses `terminal_width() - 8` (replaces hardcoded `100`/`120`)
- `action_start`: `[prompt]` badge and line count dimmed; shell command text dimmed; truncation uses dynamic `max_line`
- `action_output`: truncation uses dynamic `max_line`
- `action_complete`: duration dimmed; "timed out" and non-zero exit in orange (`"38;5;208"`); output preview truncation uses dynamic `max_line`
- `evaluate`: `✓` green, `✗` orange; verdict word green for success/target/progress, orange for fail/error, dim for other; confidence dimmed
- `route`: `->` dimmed, target state bold

**`run_foreground()` footer**:
- Final state green when `terminated_by == "terminal"`, orange otherwise (interrupted/max-iter reached)

## Verification

- `from little_loops.cli.loop._helpers import print_execution_plan, run_background, run_foreground` imports successfully
- 369 loop-related tests pass (4 pre-existing `TestHistoryTail` failures unrelated to this change — those test `ll-loop history` output format)
- `NO_COLOR=1` suppresses all color (via existing `_USE_COLOR` guard in `output.py`)
- Quiet mode (`--quiet`) unchanged — no output path

## Files Modified

- `scripts/little_loops/cli/loop/_helpers.py`
