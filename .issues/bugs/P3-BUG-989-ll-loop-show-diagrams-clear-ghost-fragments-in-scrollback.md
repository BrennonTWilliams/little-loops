---
discovered_date: 2026-04-07
discovered_by: capture-issue
---

# BUG-989: ll-loop --show-diagrams --clear produces ghost diagram fragments in scrollback

## Summary

When running `ll-loop run ... --show-diagrams --clear` with a loop whose FSM diagram is taller than the current terminal height, partial "ghost" diagram fragments accumulate in the scrollback buffer above the real diagram on each state transition. The visible output appears to contain multiple chopped copies of the diagram stacked above the full final render.

## Current Behavior

Each time a state transition fires, the screen-clear sequence `\033[2J\033[H` (ANSI ED2) erases the visible viewport and moves the cursor to row 1, column 1. The full diagram is then printed linearly from that position. When the diagram exceeds the terminal height, the top lines of the diagram are pushed into the scrollback buffer before the next clear fires. ED2 only clears the visible viewport — scrollback is untouched — so the overflow lines from iteration N are permanently visible in scrollback. After N state transitions there are N−1 partial fragments stacked in the scrollback above the current full diagram.

## Expected Behavior

The screen should be cleanly replaced on each state transition with only the current diagram — no ghost fragments in scrollback regardless of diagram height.

## Motivation

The `--show-diagrams --clear` flags are intended to provide a live-updating view of the FSM execution. For any non-trivial loop (e.g. `refine-to-ready-issue`) the diagram exceeds 30 rows, making the current behavior the default for most real-world usage. The artifact output is visually confusing and undermines confidence in the tool.

## Steps to Reproduce

1. Run a loop whose FSM diagram renders taller than the terminal: `ll-loop run refine-to-ready-issue --show-diagrams --clear`
2. Make the terminal window shorter than the diagram height (or use a default 24-row terminal)
3. Observe that after the first state transition, partial diagram fragments appear in the scrollback above the full diagram
4. Each subsequent transition adds another fragment

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `in display_progress(), lines 331-332`
- **Cause**: `print("\033[2J\033[H", end="", flush=True)` uses ANSI ED2 which clears only the visible terminal viewport. When the diagram (built by `_render_fsm_diagram` in `layout.py:1434`) is taller than the terminal, lines that overflowed the bottom in the previous render are already in scrollback and survive the ED2 clear. Terminal height is never queried — only `terminal_width()` (`output.py:16-18`) is called.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Line(s)**: 331-332
- **Anchor**: `in run_foreground() > display_progress() closure`
- **Code**:
```python
if clear_screen and sys.stdout.isatty() and depth == 0:
    print("\033[2J\033[H", end="", flush=True)
```

## Proposed Solution

Use the **alternate screen buffer** to avoid scrollback contamination entirely. Enter the alt screen once before the first render and exit when the loop completes:

- Enter: `\033[?1049h` (switch to alternate screen, cursor to top-left)
- Exit: `\033[?1049l` (restore primary screen)

The alternate screen has no scrollback by design — ED2 clears everything. This is the standard approach used by `vim`, `less`, and `htop`. Per-render logic at line 332 can remain unchanged (or simplify to just `\033[H` + `\033[J` once on the alt screen).

Alternative (no alt-screen): track the line count printed in the previous render and emit `\033[{n}A\033[J` (cursor up N, erase to end) to overwrite in place — but this requires storing last-render line count and breaks if the diagram changes height between states.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — enter alt screen before first diagram render, exit on loop completion/interrupt

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — calls `run_foreground()` at line 211
- `scripts/little_loops/cli/loop/__init__.py` — `resume` subcommand also calls `run_foreground()` (line ~229)

### Similar Patterns
- No existing alt-screen usage in the codebase — this would be the first

### Tests
- `scripts/tests/` — search for `show_diagrams` or `display_progress` tests to extend

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `_helpers.py:run_foreground()`, detect when `show_diagrams and clear_screen and sys.stdout.isatty()` and emit `\033[?1049h` once before the executor starts (store a flag like `_using_alt_screen`)
2. Register a cleanup (try/finally or `atexit`) to emit `\033[?1049l` and restore the primary screen when the loop ends or is interrupted
3. On each `state_enter` in `display_progress`, replace the current `\033[2J\033[H` with `\033[H\033[2J` (cursor home then erase) — functionally the same on alt screen but avoids redundant sequence
4. Add a note in `--clear` help text that alt screen is used when combined with `--show-diagrams`

## Impact

- **Priority**: P3 - Affects UX of `--show-diagrams --clear` for all non-trivial loops; no data loss
- **Effort**: Small - 10–20 line change in `_helpers.py`, plus cleanup handler
- **Risk**: Low - alt screen is universally supported in xterm-compatible terminals; fallback is existing behaviour when `not isatty()`
- **Breaking Change**: No

## Related Key Documentation

| Document | Description | Relevance |
|----------|-------------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | System design and technical decisions | Low |

## Labels

`bug`, `ll-loop`, `tui`, `captured`

## Status

**Open** | Created: 2026-04-07 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-04-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ad0cbea-3b2e-43a7-b77a-e86e33d332e2.jsonl`
