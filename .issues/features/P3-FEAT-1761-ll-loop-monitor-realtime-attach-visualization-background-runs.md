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

## Proposed Solution

- The display/rendering pipeline already exists in the foreground run path (likely `_display.py` or similar). Extract it behind an interface that accepts a state feed rather than being coupled to the running loop subprocess.
- State feed abstraction: a generator/iterator that yields `LoopState` snapshots — foreground runs push states directly; monitor mode polls `.state.json` with `inotify`/`FSEvents`/fallback polling (100ms interval).
- Log streaming: `ll-loop monitor` should tail the loop's log file if one exists (configurable via `--log-file`), rendering it in the same panel as the foreground run.
- Diagram rendering is already conditional on `--show-diagrams`; the monitor reuses this flag with the same default.
- PID file location: `.loops/.running/<loop_name>.pid` (already written by `run_background()`).
- State file location: `.loops/.running/<loop_name>.state.json` (already written on each state transition).

## API/Interface

New subcommand:
```
ll-loop monitor <loop_name> [--show-diagrams [MODE]] [--no-clear] [--log-file PATH]
```

Alternatively surfaced as a flag on `ll-loop status`:
```
ll-loop status <loop_name> --watch [--show-diagrams [MODE]]
```

Decision: prefer a dedicated `monitor` subcommand for discoverability; `status --watch` can be a documented alias.

## Use Case

**Who**: A developer running long `ll-loop` automation sessions on a codebase

**Context**: They start a loop with `--background` to keep the terminal free, then later want to observe its progress — FSM state transitions, current iteration, and live log output — without having to parse `.state.json` manually.

**Goal**: Attach the same rich visual display used by foreground `--clear --show-diagrams` runs to an already-running background process.

**Outcome**: Real-time FSM diagram and log stream appear in the terminal; Ctrl-C detaches without interrupting the loop; a clean final summary prints when the loop finishes naturally.

## Implementation Steps

1. Identify and extract the display/rendering pipeline from the foreground run path into a reusable `StateFeedRenderer` interface
2. Implement `StateFeedSource` abstraction: foreground pushes states directly; monitor mode polls `.loops/.running/<loop>.state.json` via `inotify`/`FSEvents`/fallback 100ms polling
3. Add log-tail support (read the loop's log file and render alongside the FSM diagram panel)
4. Add `ll-loop monitor <loop_name>` subcommand with `--show-diagrams [MODE]`, `--no-clear`, `--log-file PATH` flags
5. Wire Ctrl-C handling to detach the monitor only — must not send a signal to the background loop process
6. Add tests and update CLI help/docs

## Integration Map

### Files to Modify
- TBD — identify display pipeline module: `grep -r "show_diagrams\|_display\|run_background" scripts/little_loops/`
- `scripts/little_loops/cli/ll_loop.py` (or equivalent) — add `monitor` subcommand

### Dependent Files (Callers/Importers)
- TBD — `grep -r "run_background\|\.running\|state\.json" scripts/`

### Similar Patterns
- `ll-loop run --clear --show-diagrams` — existing rendering pipeline to extract and reuse

### Tests
- `scripts/tests/` — new tests for `monitor` subcommand, `StateFeedSource` abstraction, and Ctrl-C detach behavior

### Documentation
- `docs/` — update `ll-loop` CLI reference with `monitor` subcommand

### Configuration
- N/A

## Acceptance Criteria

- [ ] `ll-loop monitor <name>` attaches to a running background loop and renders FSM state changes in realtime.
- [ ] `--show-diagrams [MODE]` works identically to the foreground run path.
- [ ] Ctrl-C detaches without stopping the loop; loop continues running in background.
- [ ] If the loop is not running, prints last known state from `.state.json` and exits 0.
- [ ] On loop completion, monitor exits with the loop's exit code.
- [ ] Works on macOS (FSEvents or polling) and Linux (inotify or polling).

## Impact

- **Priority**: P3 — Quality-of-life improvement; background loops are functional, this adds live observability
- **Effort**: Medium — Display rendering pipeline exists; requires abstraction layer, new subcommand, and Ctrl-C signal handling
- **Risk**: Low — Monitor is read-only; main risk is Ctrl-C handling (must not propagate signal to the background loop process)
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-loop`, `ux`, `observability`

## Related Issues

- FEAT-1232: `ll-loop parallel` subcommand (deferred) — background group launcher
- FEAT-047: `ll-loop` CLI tool (core runner)

## Status

**Open** | Created: 2026-05-28 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-28T03:58:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34d7caed-10b0-415b-91c0-c8c95443f1f9.jsonl`
- `/ll:capture-issue` - 2026-05-28T03:46:53Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2bcb218-a171-4a8f-92ee-aeaf8000e6a2.jsonl`
