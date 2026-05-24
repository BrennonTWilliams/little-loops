---
id: ENH-1682
type: ENH
priority: P4
status: open
title: "Add --log-to <file> tee option to ll-loop run"
captured_at: "2026-05-24T17:45:05Z"
discovered_date: "2026-05-24"
discovered_by: capture-issue
---

# ENH-1682: Add --log-to <file> tee option to ll-loop run

## Motivation

When running `ll-loop run` with `--clear` (especially combined with `--show-diagrams`,
which enters the alternate screen buffer), users cannot scroll back to see earlier state
output during an active run. The alt-screen hides scrollback by design.

A `--log-to <file>` option would tee all loop output to a file, letting users run
`tail -f <file>` in a second pane to access full scrollback without disrupting the live
TUI view. This is a lower-cost win than redesigning the `--clear` model.

## Implementation Steps

1. Add `--log-to <path>` argument to the `ll-loop run` (and `resume`) arg parser
2. In `run_foreground` (`scripts/little_loops/cli/loop/_helpers.py`), when `args.log_to`
   is set, open the file for writing and wrap `sys.stdout` (or the print calls) with a
   tee that writes to both stdout and the log file
3. Strip ANSI escape codes before writing to the log file (plain text for readability
   with `tail -f` / grep)
4. Close the log file handle on exit (hook into the existing `atexit`/`finally` cleanup)
5. Print a one-line notice at startup: `Logging to: <path>` when `--log-to` is active

## API / Interface Changes

```
ll-loop run <loop> [--log-to <file>] ...
ll-loop resume <loop> [--log-to <file>] ...
```

The log file is created (or truncated) at run start. ANSI codes are stripped so the
file is grep-friendly.

## Acceptance Criteria

- `ll-loop run general-task --clear --show-diagrams --log-to /tmp/loop.log` writes
  plain-text progress lines to `/tmp/loop.log` while the TUI displays normally
- `tail -f /tmp/loop.log` in a second pane shows all state transitions and action output
- Log file is closed cleanly on normal exit, SIGTERM, and loop error
- No ANSI escape sequences in the log file

## Session Log
- `/ll:capture-issue` - 2026-05-24T17:45:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a60b27f-22df-41ea-82fa-1f0c281994dd.jsonl`
