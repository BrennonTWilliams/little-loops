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

## Summary

Add `--log-to <file>` CLI argument to `ll-loop run` and `ll-loop resume` that tees all loop output to a plain-text file (ANSI-stripped), enabling users to `tail -f` in a second pane for full scrollback when running with `--clear` or `--show-diagrams`.

## Current Behavior

When running `ll-loop run` with `--clear` (or `--show-diagrams`), output is sent to the alternate screen buffer only. Users cannot scroll back to see earlier state transitions during an active run because the alt-screen hides scrollback by design.

## Expected Behavior

With `--log-to <file>`, all loop output is simultaneously written to the specified file with ANSI escape codes stripped. Users can run `tail -f <file>` in a second terminal pane to access full scrollback history without disrupting the live TUI view.

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

## API/Interface Changes

```
ll-loop run <loop> [--log-to <file>] ...
ll-loop resume <loop> [--log-to <file>] ...
```

The log file is created (or truncated) at run start. ANSI codes are stripped so the
file is grep-friendly.

## Scope Boundaries

- Does not redesign the `--clear` / alternate-screen model
- Does not add log rotation, file size limits, or compression
- Does not support structured/JSON log format (plain text only)
- Does not apply to `ll-loop simulate` or other subcommands — only `run` and `resume`
- Does not add remote or syslog sinks

## Acceptance Criteria

- `ll-loop run general-task --clear --show-diagrams --log-to /tmp/loop.log` writes
  plain-text progress lines to `/tmp/loop.log` while the TUI displays normally
- `tail -f /tmp/loop.log` in a second pane shows all state transitions and action output
- Log file is closed cleanly on normal exit, SIGTERM, and loop error
- No ANSI escape sequences in the log file

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — add `--log-to` argument to `cmd_run()` arg parser; plumb `args.log_to` through to `run_foreground()`
- `scripts/little_loops/cli/loop/lifecycle.py` — add `--log-to` argument to `cmd_resume()` (line ~415); same plumbing pattern
- `scripts/little_loops/cli/loop/_helpers.py` — implement tee wrapper in `run_foreground()` (line ~608); add ANSI-stripping util; hook file close into existing `atexit`/`finally`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__main__.py` — entry point; no changes expected if subparsers are defined in their own modules

### Similar Patterns
- Follow the same arg-plumbing pattern as `args.dry_run`, `args.no_llm`, `args.llm_model` in `run.py`

### Tests
- `scripts/tests/` — check for existing `ll-loop run` integration tests; add test asserting `--log-to` file is created, contains state-transition lines, and has no ANSI codes

### Documentation
- N/A — `--help` output auto-documents the new flag

### Configuration
- N/A — no config file changes

## Impact

- **Priority**: P4 — Low-priority UX improvement; does not block any critical path but meaningfully improves debuggability for `--clear` / `--show-diagrams` runs
- **Effort**: Small — Additive CLI flag plus tee wrapper around existing print calls; no architectural changes required
- **Risk**: Low — Purely additive; tee is only activated when `--log-to` is explicitly passed; zero impact on existing runs
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `ll-loop`, `ux`

## Status

**Open** | Created: 2026-05-24 | Priority: P4

## Session Log
- `/ll:format-issue` - 2026-05-24T17:49:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a0e276a3-13b8-43b1-8581-1cb2cbdbf771.jsonl`
- `/ll:capture-issue` - 2026-05-24T17:45:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a60b27f-22df-41ea-82fa-1f0c281994dd.jsonl`
