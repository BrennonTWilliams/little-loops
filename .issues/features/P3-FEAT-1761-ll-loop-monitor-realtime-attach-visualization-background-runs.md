---
id: FEAT-1761
title: "ll-loop monitor: realtime attach and visualization for background loop runs"
type: FEAT
status: open
priority: P3
size: Medium
captured_at: "2026-05-28T03:46:53Z"
discovered_date: "2026-05-28"
discovered_by: capture-issue
testable: true
---

# FEAT-1761: `ll-loop monitor` — Realtime Attach and Visualization for Background Loop Runs

## Summary

Add an `ll-loop monitor <loop_name>` subcommand (or `--attach` flag on `ll-loop run`) that lets users view the same rich realtime visual display — FSM state diagrams, iteration progress, log streaming — for a loop that is already running in background mode, matching the UX of foreground runs with `--clear` and `--show-diagrams [MODE]`.

## Motivation

`ll-loop run <loop> --clear --show-diagrams [MODE]` provides a rich TUI-like display for foreground runs: live FSM state diagrams rendered in the terminal, per-iteration status, color-coded transitions, and streaming logs. When a loop is started with `--background` (or detached via `&`), all of that visibility is lost — the user can only poll `.loops/.running/<loop>.state.json` or `tail` a log file manually. There is no first-class way to "attach" the visual layer to an already-running background process.

## Expected Behavior

```
ll-loop monitor <loop_name>          # attach and display with default diagram mode
ll-loop monitor <loop_name> --show-diagrams ascii
ll-loop monitor <loop_name> --no-clear   # stream without clearing screen
```

- Discovers the running loop via its PID file at `.loops/.running/<loop_name>.pid`.
- If the loop is not currently running, exits with a helpful message showing last known state.
- Attaches to the loop's state feed (file-watch on `.loops/.running/<loop_name>.state.json` + log tail) and renders the same display pipeline that `ll-loop run --clear --show-diagrams` uses.
- Supports all existing `--show-diagrams [MODE]` values (`ascii`, `unicode`, `mermaid`).
- Ctrl-C detaches the monitor without stopping the background loop (unlike foreground runs where Ctrl-C signals the loop itself).
- On natural loop completion, the monitor detects the terminal state and exits cleanly, printing the final summary.

## Current Behavior

Background loops can only be observed by manually reading `.loops/.running/<loop>.state.json`, tailing a log file, or running `ll-loop status <loop>` (which gives a one-shot snapshot, not realtime updates).

## Implementation Notes

- The display/rendering pipeline already exists in the foreground run path (likely `_display.py` or similar). Extract it behind an interface that accepts a state feed rather than being coupled to the running loop subprocess.
- State feed abstraction: a generator/iterator that yields `LoopState` snapshots — foreground runs push states directly; monitor mode polls `.state.json` with `inotify`/`FSEvents`/fallback polling (100ms interval).
- Log streaming: `ll-loop monitor` should tail the loop's log file if one exists (configurable via `--log-file`), rendering it in the same panel as the foreground run.
- Diagram rendering is already conditional on `--show-diagrams`; the monitor reuses this flag with the same default.
- PID file location: `.loops/.running/<loop_name>.pid` (already written by `run_background()`).
- State file location: `.loops/.running/<loop_name>.state.json` (already written on each state transition).

## API / Interface Changes

New subcommand:
```
ll-loop monitor <loop_name> [--show-diagrams [MODE]] [--no-clear] [--log-file PATH]
```

Alternatively surfaced as a flag on `ll-loop status`:
```
ll-loop status <loop_name> --watch [--show-diagrams [MODE]]
```

Decision: prefer a dedicated `monitor` subcommand for discoverability; `status --watch` can be a documented alias.

## Acceptance Criteria

- [ ] `ll-loop monitor <name>` attaches to a running background loop and renders FSM state changes in realtime.
- [ ] `--show-diagrams [MODE]` works identically to the foreground run path.
- [ ] Ctrl-C detaches without stopping the loop; loop continues running in background.
- [ ] If the loop is not running, prints last known state from `.state.json` and exits 0.
- [ ] On loop completion, monitor exits with the loop's exit code.
- [ ] Works on macOS (FSEvents or polling) and Linux (inotify or polling).

## Related Issues

- FEAT-1232: `ll-loop parallel` subcommand (deferred) — background group launcher
- FEAT-047: `ll-loop` CLI tool (core runner)

## Session Log
- `/ll:capture-issue` - 2026-05-28T03:46:53Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2bcb218-a171-4a8f-92ee-aeaf8000e6a2.jsonl`
