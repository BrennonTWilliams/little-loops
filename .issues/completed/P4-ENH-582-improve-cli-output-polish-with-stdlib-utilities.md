---
id: ENH-582
type: ENH
priority: P4
status: completed
discovered_date: 2026-03-04
discovered_by: capture-issue
---

# ENH-582: Improve CLI Output Polish with Stdlib Utilities

## Summary

Improve the visual quality and consistency of non-interactive CLI outputs across `ll-loop show`, `ll-issues list`, `ll-sprint show`, `ll-loop history`, and other commands using Python stdlib utilities — no new runtime dependencies required.

Four targeted improvements:
1. **`shutil.get_terminal_size()`** — responsive column widths instead of hardcoded `52` in separator lines
2. **`textwrap.fill()` / `textwrap.indent()`** — wrap long action previews and description text at terminal width
3. **ANSI escape codes** — color highlighting (bold headers, type/priority color coding) with `NO_COLOR` guard
4. **`datetime.fromisoformat()` + `.strftime()`** — human-readable timestamps in `ll-loop history`

## Current Behavior

- `ll-loop show`: separator line width is hardcoded to `52 - len(loop_name)` (`info.py:551`)
- `ll-loop show`: action preview text wraps based on raw `\n` splits, not terminal width
- `ll-issues list`: issues displayed as flat monochrome text — BUG, FEAT, ENH indistinguishable at a glance
- `ll-loop history`: timestamps printed as raw ISO strings (`{ts} {event_type}: {details}`)
- All outputs: no color, no bold/emphasis, no visual grouping cues

## Expected Behavior

- Separator and column widths adapt to the actual terminal width (fallback: 80)
- Long action/description text wraps cleanly at terminal width with proper indentation
- Issue types and priorities use consistent color coding: BUG=red, FEAT=green, ENH=blue, P0/P1=red, P4/P5=dim
- History timestamps display as `YYYY-MM-DD HH:MM:SS` instead of full ISO format
- All color is suppressed when `NO_COLOR=1` is set or stdout is not a TTY

## Motivation

These four changes are high-leverage, zero-dependency improvements. The `shutil` and `textwrap` modules are already in stdlib and used elsewhere in the Python ecosystem. The ANSI color guard pattern is idiomatic and well-understood. Together they close a noticeable visual quality gap that shows up daily when using these commands — especially `ll-issues list` (scanned frequently) and `ll-loop show` (used during loop authoring).

## Proposed Solution

### 1. Terminal width utility (shared)

```python
import shutil

def terminal_width(default: int = 80) -> int:
    return shutil.get_terminal_size((default, 24)).columns
```

Use in `info.py:cmd_show` to replace `52` in `separator_dashes = "─" * max(0, 52 - len(loop_name))`.

### 2. Text wrapping

```python
import textwrap

def wrap_text(text: str, indent: str = "  ", width: int | None = None) -> str:
    w = width or terminal_width()
    return textwrap.fill(text, width=w, initial_indent=indent, subsequent_indent=indent)
```

Use in `cmd_show` for description and action preview sections.

### 3. ANSI color with NO_COLOR guard

```python
import os, sys

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

# Usage:
PRIORITY_COLOR = {"P0": "31;1", "P1": "31", "P2": "33", "P3": "0", "P4": "2", "P5": "2"}
TYPE_COLOR = {"BUG": "31", "FEAT": "32", "ENH": "34"}
```

Apply in `list_cmd.py:cmd_list` when printing issue lines.

### 4. Timestamp formatting in history

In `info.py:cmd_history`, replace:
```python
ts = event.get("ts", "")[:19]
```
With:
```python
from datetime import datetime
raw_ts = event.get("ts", "")
try:
    ts = datetime.fromisoformat(raw_ts).strftime("%Y-%m-%d %H:%M:%S")
except ValueError:
    ts = raw_ts[:19]
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_show`, `cmd_history`
- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list`
- `scripts/little_loops/cli/sprint/show.py` — `_cmd_sprint_show` separator width

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — routes to `info.py` functions
- `scripts/little_loops/cli/issues/__init__.py` — routes to `list_cmd.py`

### Similar Patterns
- `scripts/little_loops/cli/sprint/_helpers.py` — uses `"=" * 70` hardcoded widths, same fix applies
- `scripts/little_loops/logo.py` — may benefit from width awareness

### Tests
- `scripts/tests/test_cli.py` — test captured output for these commands; assert no ANSI codes when NO_COLOR set
- `scripts/tests/test_issue_history_cli.py` — test timestamp formatting in history output

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Create a small shared `scripts/little_loops/cli/output.py` module with `terminal_width()`, `wrap_text()`, and `_c()` color helpers
2. Update `info.py` (`cmd_show` separator, action/description wrapping, `cmd_history` timestamps)
3. Update `list_cmd.py` with type/priority color coding
4. Update `sprint/show.py` and `sprint/_helpers.py` hardcoded widths
5. Add/update tests: verify `NO_COLOR` suppression, verify timestamp format

## Success Metrics

- **Terminal width**: Separator and column widths adapt to actual TTY width; verified by setting `COLUMNS=120` and confirming output matches
- **Color suppression**: No ANSI codes in output when `NO_COLOR=1` is set or stdout is not a TTY; `test_cli.py` assertions cover both cases
- **Timestamp format**: `ll-loop history` output uses `YYYY-MM-DD HH:MM:SS` format; `test_issue_history_cli.py` asserts the new format and rejects raw ISO strings
- **Text wrapping**: Long action/description text wraps at terminal width with consistent indentation; no overflow beyond `terminal_width()` columns

## Scope Boundaries

- **Out of scope**: Adding `rich`, `tabulate`, or any non-stdlib library
- **Out of scope**: Interactive/TUI features (progress bars, spinners, live updates)
- **Out of scope**: Redesigning the FSM diagram renderer (`_render_2d_diagram`) — separate concern
- **Out of scope**: Color in log/error output (only CLI display commands)

## Impact

- **Priority**: P4 — quality-of-life improvement, no functional regression risk
- **Effort**: Small — all changes are localized to existing print-heavy CLI files, using only stdlib
- **Risk**: Low — ANSI codes are suppressed on non-TTY; all changes are purely cosmetic output
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | CLI module structure |
| `.claude/CLAUDE.md` | Code style and 100-char line limit |

## Labels

`enhancement`, `cli`, `dx`, `captured`

## Resolution

### Changes Made
1. Created `scripts/little_loops/cli/output.py` — shared `terminal_width()`, `wrap_text()`, and `colorize()` utilities with `NO_COLOR`/non-TTY guard
2. Updated `scripts/little_loops/cli/loop/info.py`:
   - Separator line in `cmd_show` now uses `terminal_width()` instead of hardcoded `52`
   - `cmd_history` timestamps formatted via `datetime.fromisoformat().strftime("%Y-%m-%d %H:%M:%S")`
3. Updated `scripts/little_loops/cli/issues/list_cmd.py` — type/priority color coding in `cmd_list` (BUG=red, FEAT=green, ENH=blue, P0/P1=red, P4/P5=dim)
4. Updated `scripts/little_loops/cli/sprint/_helpers.py` — `"=" * terminal_width()` in `_render_execution_plan`
5. Updated `scripts/little_loops/cli/sprint/show.py` — `"=" * terminal_width()` in `_render_dependency_graph`
6. Added `scripts/tests/test_cli_output.py` with 10 tests covering terminal_width, colorize, timestamp formatting, and NO_COLOR suppression

### Verification
- All 3230 tests pass (0 failures)
- Lint: all checks passed
- NO_COLOR guard confirmed by `sys.stdout.isatty()` check at import time

## Session Log

- `/ll:capture-issue` - 2026-03-04 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7d8e8d6d-db5b-43f2-a487-44ffa85ddfb7.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44683e3b-a335-4530-95b2-8a6c8506e507.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:manage-issue` - 2026-03-04T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1edc06fa-5b2e-4f5c-bf9e-95af499acdcc.jsonl`

---

**Completed** | Created: 2026-03-04 | Priority: P4
