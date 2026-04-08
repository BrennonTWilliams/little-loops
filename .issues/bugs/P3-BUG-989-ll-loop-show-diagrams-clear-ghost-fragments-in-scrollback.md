---
discovered_date: 2026-04-07
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 78
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
- `scripts/little_loops/cli/loop/__init__.py` — update `--clear` help text in **both** `run_parser` (line ~137) and `resume_parser` (line ~237) to note alternate screen is used when combined with `--show-diagrams` [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:211` — only caller of `run_foreground()`; wraps it in a `try/finally` for lock release (lines 149–220)
- `scripts/little_loops/cli/loop/lifecycle.py:262` — `cmd_resume` calls `executor.resume()` directly, NOT `run_foreground()` — the `--show-diagrams`/`--clear` flags on the `resume` subcommand are declared but never wired to `display_progress`

### Similar Patterns
- No existing alt-screen usage in the codebase — this would be the first
- Existing cleanup patterns to follow:
  - `atexit.register(_cleanup_pid)` at `run.py:122` for PID file teardown
  - `try/finally` lock release at `run.py:149–220` wrapping `run_foreground()` — the alt-screen exit can go in this same `finally` block
  - Signal handler at `_helpers.py:35–82` (`_loop_signal_handler`) handles SIGINT/SIGTERM — first SIGINT sets `_loop_shutdown_requested`, second calls `sys.exit(1)`; no terminal restore currently

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary test file; `TestDisplayProgress` class
  - `test_clear_flag_emits_ansi_clear_when_tty` (line ~1691) — asserts `\033[2J\033[H` is emitted; will need updating to also assert `\033[?1049h` appears before `\033[2J` in output
  - `test_clear_flag_suppressed_when_not_tty` (line ~1703) — asserts no ANSI when `isatty()` is False; needs to also assert `\033[?1049h` not in out
  - `test_clear_flag_suppressed_for_sub_loop_state_enter` (line ~1716) — asserts depth>0 suppresses clear; unaffected
  - Uses `patch("sys.stdout.isatty", return_value=True/False)` and `capsys.readouterr().out` — follow this exact pattern for new alt-screen assertions
  - No existing test uses `_make_args(show_diagrams=True, clear=True)` together — this is the exact condition that gates the fix
- `scripts/tests/test_cli_loop_background.py:13–111` — pattern for resetting module-level globals (`_loop_shutdown_requested` etc.) in `setup_method`/`teardown_method`; a new `_using_alt_screen` global follows this pattern
  - `setup_method` at line 23–33 resets 3 globals; must add reset for new `_using_alt_screen` global
  - `test_second_signal_forces_exit` (line ~50) — does not capture stderr; add `capsys` to verify `\033[?1049l` is emitted before `sys.exit(1)` [Wiring pass added by `/ll:wire-issue`]
  - `test_second_signal_cleans_pid_file` (line ~100) — same gap; add stderr capture to verify alt-screen exit [Wiring pass added by `/ll:wire-issue`]
- `scripts/tests/test_cli_loop_lifecycle.py:460–475` — tests `cmd_resume` and `_loop_signal_handler`; manually resets 3 `_helpers` globals at lines 466–470; must add reset for new `_using_alt_screen` global [Wiring pass added by `/ll:wire-issue`]

_New tests to write (add to `test_ll_loop_display.py`, follow `_make_args` + `MockExecutor` + `capsys` + `patch("sys.stdout.isatty")` pattern at lines 34–52, 1691–1724):_ [Wiring pass added by `/ll:wire-issue`]
- `test_show_diagrams_and_clear_enters_alt_screen` — `_make_args(show_diagrams=True, clear=True)` + `isatty=True`; assert `\033[?1049h` is in out and precedes `\033[2J`
- `test_clear_only_no_alt_screen` — `_make_args(clear=True, show_diagrams=False)` + `isatty=True`; assert `\033[?1049h` not in out
- `test_show_diagrams_only_no_alt_screen` — `_make_args(show_diagrams=True, clear=False)` + `isatty=True`; assert `\033[?1049h` not in out
- `test_alt_screen_exited_on_normal_completion` — assert `\033[?1049l` in out after executor returns normally
- `test_alt_screen_exited_on_executor_exception` — `MockExecutor` raises; `pytest.raises`; assert `\033[?1049l` still in stderr/stdout (from `finally`)
- `test_signal_handler_second_signal_emits_alt_screen_exit` — add to `TestLoopSignalHandler` in `test_cli_loop_background.py`; set `_using_alt_screen=True`; trigger second SIGINT; assert `\033[?1049l` in captured stderr

### Documentation
- `docs/reference/CLI.md:253–254,297–298` — `--clear` and `--show-diagrams` flag descriptions for `run` and `resume` subcommands
- `docs/guides/LOOPS_GUIDE.md:1298–1299` — flag reference table rows for `--show-diagrams` and `--clear`; update to note alt-screen behavior [Wiring pass added by `/ll:wire-issue`]
- `docs/guides/LOOPS_GUIDE.md:1443` — prose describing `--show-diagrams` behavior with sub-loops; mention alternate screen buffer [Wiring pass added by `/ll:wire-issue`]
- `README.md:287–288` — example invocations showing `--clear --show-diagrams` described as "live in-place dashboard"; update prose to note alternate screen is used [Wiring pass added by `/ll:wire-issue`]

### Configuration
- N/A

## Implementation Steps

1. In `_helpers.py:run_foreground()` (line 282), after reading `clear_screen` (line 303) and `show_diagrams` (line 302), emit `\033[?1049h\033[H` (enter alt screen + cursor home) when all three conditions hold: `show_diagrams and clear_screen and sys.stdout.isatty()`. Set a local flag `_using_alt_screen = True`.
2. Register cleanup to emit `\033[?1049l` (exit alt screen):
   - The `try/finally` at `run.py:149–220` already wraps `run_foreground()` — add the alt-screen exit in `run_foreground()` itself via its own internal `try/finally` around `executor.run()` (line 497); this ensures cleanup on both normal exit and `KeyboardInterrupt`.
   - Also update `_loop_signal_handler` at `_helpers.py:35–82` to emit `\033[?1049l` before `sys.exit(1)` on second SIGINT (line 47) so force-kill restores the screen.
3. On each `state_enter` at `display_progress` (line 331–332), the existing `\033[2J\033[H` works correctly on the alt screen — no change needed for the per-render clear.
4. Update `--clear` flag help text in **both** `run_parser` (~line 137) and `resume_parser` (~line 237) in `scripts/little_loops/cli/loop/__init__.py`; update `docs/reference/CLI.md:253–254,297–298`, `docs/guides/LOOPS_GUIDE.md:1298–1299,1443`, and `README.md:287–288` to note that alt screen is used when combined with `--show-diagrams`. [Wiring pass: resume_parser and LOOPS_GUIDE/README were missing from original step]
5. Update tests in `scripts/tests/test_ll_loop_display.py`:
   - Modify `test_clear_flag_emits_ansi_clear_when_tty` (~line 1691) to also assert `\033[?1049h` appears in output before the first `\033[2J\033[H`
   - Modify `test_clear_flag_suppressed_when_not_tty` (~line 1703) to also assert `\033[?1049h` not in out
   - Add the 5 new tests enumerated in the Tests section above (`test_show_diagrams_and_clear_enters_alt_screen`, `test_clear_only_no_alt_screen`, `test_show_diagrams_only_no_alt_screen`, `test_alt_screen_exited_on_normal_completion`, `test_alt_screen_exited_on_executor_exception`)
6. Add reset of new `_using_alt_screen` global to `setup_method` in `scripts/tests/test_cli_loop_background.py:23-33` and to the manual reset block in `scripts/tests/test_cli_loop_lifecycle.py:466–470`; add `test_signal_handler_second_signal_emits_alt_screen_exit` to `TestLoopSignalHandler`. [Wiring pass added by `/ll:wire-issue`]

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
- `/ll:confidence-check` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef7b723c-c390-4334-9fd7-55a84a05e0a7.jsonl`
- `/ll:wire-issue` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/memory/`
- `/ll:refine-issue` - 2026-04-08T17:49:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee0b01ff-f8a6-41e9-8b8b-e90bc50cd8f2.jsonl`
- `/ll:format-issue` - 2026-04-08T17:45:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37027bb9-1fa6-406a-80cc-0e6d8670eb16.jsonl`
- `/ll:capture-issue` - 2026-04-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ad0cbea-3b2e-43a7-b77a-e86e33d332e2.jsonl`
