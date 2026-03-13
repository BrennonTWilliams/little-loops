---
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# ENH-718: Add --clear Flag to ll-loop run for Per-Iteration Screen Refresh

## Summary

Add a `--clear` flag to `ll-loop run` that emits an ANSI clear-screen escape sequence before each iteration's output. Especially useful with `--show-diagrams`: the FSM diagram "updates in place" visually rather than scrolling, making it easy to see which state is currently highlighted as the loop progresses.

## Current Behavior

Each iteration appends output below the previous iteration's output. When `--show-diagrams` is passed, a new copy of the full FSM diagram is printed every iteration, causing significant scroll noise. There is no way to see the diagram updating in place.

## Expected Behavior

With `--clear`, the terminal is cleared before each iteration's output block. Combined with `--show-diagrams`, the diagram re-renders at the top of the screen each iteration with the current state highlighted, creating a live "dashboard" feel.

## Motivation

`--show-diagrams` is most useful as a visual tracker of FSM progress, but its value is undermined when each iteration prints a new copy that immediately scrolls off screen. A `--clear` flag would make the feature genuinely useful for monitoring long-running loops.

## Proposed Solution

Three small changes, no new abstractions needed:

**1. Add argument** (`scripts/little_loops/cli/loop/__init__.py`, in `run` subparser near `--show-diagrams`):
```python
run_parser.add_argument(
    "--clear", action="store_true",
    help="Clear terminal before each iteration (useful with --show-diagrams)"
)
```

**2. Read the flag** (`scripts/little_loops/cli/loop/_helpers.py`, in `run_foreground()` near `show_diagrams`):
```python
clear_screen = getattr(args, "clear", False)
```

**3. Emit clear at top of `state_enter` branch** (`_helpers.py`, in `display_progress()` at the `state_enter` event handler):
```python
if event_type == "state_enter":
    if clear_screen and sys.stdout.isatty():
        print("\033[2J\033[H", end="", flush=True)
    if show_diagrams:
        ...
```

`\033[2J` clears the screen; `\033[H` moves the cursor to the top-left. The `isatty()` guard prevents escape sequences from being written into log files when output is redirected (e.g. background mode or piped output).

## API/Interface

```
ll-loop run <name> [--clear] [--show-diagrams] [...]
```

New flag: `--clear` (boolean, default false). No changes to existing flags or programmatic API.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--clear` argument to `run` subparser (and `resume` subparser for consistency)
- `scripts/little_loops/cli/loop/_helpers.py` — read `clear_screen` flag, emit ANSI clear in `display_progress()` `state_enter` branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — calls `run_foreground(executor, fsm, args, ...)`, `args` passed through; no change needed
- `scripts/little_loops/cli/loop/resume.py` — same pattern; add `--clear` to its subparser too for consistency

### Similar Patterns
- `--show-diagrams` flag: same subparsers, same `getattr(args, ...)` read pattern in `run_foreground()`

### Tests
- `scripts/tests/` — check for existing `run_foreground` or `display_progress` tests; add a test that `--clear` emits `\033[2J` only when stdout is a TTY

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `--clear` argument to `run` and `resume` subparsers in `__init__.py`
2. Read `clear_screen = getattr(args, "clear", False)` in `run_foreground()` next to `show_diagrams`
3. Emit `\033[2J\033[H` at top of `state_enter` branch in `display_progress()`, gated on `sys.stdout.isatty()`
4. Verify behavior manually with `ll-loop run <loop> --clear --show-diagrams`
5. Add/update tests for the new flag

## Impact

- **Priority**: P4 - QoL improvement for interactive monitoring; not blocking anything
- **Effort**: Small - ~15 lines across 2 files, no new abstractions
- **Risk**: Low - gated behind a new opt-in flag; existing behavior unchanged; `isatty()` guard prevents log corruption
- **Breaking Change**: No

## Scope Boundaries

- Does not change any existing output behavior (opt-in flag only)
- Does not add "live refresh" / cursor positioning beyond the clear-screen approach (e.g. no ncurses)
- `resume` subparser should also get the flag for consistency, but is not the primary target

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `ux`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
