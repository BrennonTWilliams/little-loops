---
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
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

## Success Metrics

- `ll-loop run <loop> --clear --show-diagrams` renders the FSM diagram at the top of the screen each iteration with no scroll accumulation
- `ll-loop run <loop> --clear > output.log` produces no ANSI escape sequences in the log file (isatty() guard confirmed)
- Existing behavior without `--clear` is unchanged (no regression)

## API/Interface

```
ll-loop run <name> [--clear] [--show-diagrams] [...]
```

New flag: `--clear` (boolean, default false). No changes to existing flags or programmatic API.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--clear` argument to `run` subparser (after `--show-diagrams` at line 113) and `resume` subparser (after `--show-diagrams` at line 175)
- `scripts/little_loops/cli/loop/_helpers.py` — read `clear_screen` flag at line 278 (next to `show_diagrams`); emit ANSI clear at line 293 inside `state_enter` branch of `display_progress()` closure, before the `if show_diagrams:` check at line 301

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:113` — calls `run_foreground(executor, fsm, args, highlight_color=...)`, `args` passed through; no change needed
- `scripts/little_loops/cli/loop/lifecycle.py:198` — `cmd_resume()` calls `executor.resume()` directly, **not** `run_foreground()`. The `--show-diagrams` argument on the resume subparser is currently dead code for foreground resume. Adding `--clear` to the resume subparser will have no effect unless `cmd_resume()` is also wired to call `run_foreground()` (out of scope for this issue; file the gap separately if needed).

### Similar Patterns
- `--show-diagrams` flag (`__init__.py:113–117`, `__init__.py:175–179`): exact same subparser pattern to follow
- `show_diagrams = getattr(args, "show_diagrams", False)` at `_helpers.py:278`: exact read pattern for the new `clear_screen` variable
- `display_progress()` nested closure at `_helpers.py:287`: `state_enter` branch at lines 293–312; `if show_diagrams:` check at line 301 is the insertion point

### Tests
- `scripts/tests/test_ll_loop_display.py` — existing tests import and call `run_foreground()` directly using a `MockExecutor` that emits events; add a test here that emits a `state_enter` event with `--clear` set and asserts `\033[2J\033[H` is printed when `sys.stdout.isatty()` returns `True`, and is suppressed when it returns `False`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/cli/loop/__init__.py`, add `--clear` argument to `run` subparser after `--show-diagrams` (currently lines 113–117); add same argument to `resume` subparser after `--show-diagrams` (currently lines 175–179)
2. In `scripts/little_loops/cli/loop/_helpers.py`, add `clear_screen = getattr(args, "clear", False)` at line 279 (immediately after `show_diagrams = getattr(args, "show_diagrams", False)` at line 278)
3. In `_helpers.py`, insert ANSI clear at the top of the `state_enter` branch (line 293), before the `if show_diagrams:` check at line 301:
   ```python
   if clear_screen and sys.stdout.isatty():
       print("\033[2J\033[H", end="", flush=True)
   ```
4. Add test to `scripts/tests/test_ll_loop_display.py` using the existing `MockExecutor` pattern: call `run_foreground()` with `--clear` set, patch `sys.stdout.isatty`, assert escape sequence presence/absence
5. Verify manually: `ll-loop run <loop> --clear --show-diagrams`

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
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c86a5056-7391-48c4-89c7-a1ee90c46ccb.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f350e6bc-336a-44c3-8a3b-81c0c9c69795.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f27e2da-59cc-4ccf-a9a7-f55ce3418ad1.jsonl`
- `/ll:ready-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e85f17e-3bf6-49c7-a987-8bcc25562c84.jsonl`
- `/ll:manage-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/manage-issue.jsonl`

## Resolution

- **Date**: 2026-03-13
- **Status**: Completed
- **Changes**:
  - `scripts/little_loops/cli/loop/__init__.py`: Added `--clear` argument to `run` and `resume` subparsers
  - `scripts/little_loops/cli/loop/_helpers.py`: Read `clear_screen` flag; emit `\033[2J\033[H` at top of `state_enter` branch when stdout is a tty
  - `scripts/tests/test_ll_loop_display.py`: Added two tests (`test_clear_flag_emits_ansi_clear_when_tty`, `test_clear_flag_suppressed_when_not_tty`) and updated `_make_args` to include `clear` param

---

**Completed** | Created: 2026-03-13 | Priority: P4

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/cli/loop/__init__.py` has no `--clear` argument on the `run` or `resume` subparsers. `scripts/little_loops/cli/loop/_helpers.py` has no `clear_screen` flag or ANSI clear-screen escape emit in `display_progress()`. Feature not yet implemented.
