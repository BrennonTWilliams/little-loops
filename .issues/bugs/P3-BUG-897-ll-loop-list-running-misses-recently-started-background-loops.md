---
discovered_date: 2026-03-30
discovered_by: capture-issue
---

# BUG-897: `ll-loop list --running` misses recently-started background loops

## Summary

When `ll-loop run <name> --background` launches a loop, the parent process writes a `.pid` file immediately, but the `.state.json` file is only created once the child process enters its first FSM state (several seconds later). Since `list_running_loops()` only globs for `*.state.json`, `ll-loop list --running` reports "No running loops" during this startup window.

## Context

User description: "When `ll-loop run <name> --background` launches a loop, the parent process immediately writes a `.pid` file to `.loops/.running/`. However, the state file (`.state.json`) is only written once the child process has fully initialized and entered its first FSM state — which can take several seconds. `list_running_loops()` only globs for `*.state.json` files, so `ll-loop list --running` shows 'No running loops' during this startup window."

## Root Cause

- `_helpers.py:272` — parent writes `.pid` file immediately after `Popen`
- `persistence.py:515` — `list_running_loops()` only globs `*.state.json`
- `persistence.py:363-364` — state file first written on `state_enter` event (after full init)

The gap between PID file creation and state file creation means loops are invisible to the list command during startup.

## Proposed Solution

Modify `list_running_loops()` in `scripts/little_loops/fsm/persistence.py` to also detect loops that have a `.pid` file but no `.state.json` yet. For each such orphan PID file:

1. Read the PID and check if the process is alive (using existing `_process_alive` from `concurrency.py`)
2. If alive, synthesize a `LoopState` with `status="starting"`, `current_state="(initializing)"`, `iteration=0`
3. If not alive, skip it (stale PID file from a crashed start)

## Implementation Steps

1. In `list_running_loops()` (~line 499 of `persistence.py`), after collecting states from `*.state.json` files, scan for `*.pid` files whose loop name isn't in the collected states
2. For each orphan PID file, verify the process is alive via `_process_alive()` from `concurrency.py`
3. If alive, append a synthetic `LoopState` with `status="starting"`
4. Add test cases for both live-PID and stale-PID scenarios

## Files to Modify

- `scripts/little_loops/fsm/persistence.py` — `list_running_loops()` function

## Existing Utilities to Reuse

- `little_loops.fsm.concurrency._process_alive()` — already used by `lifecycle.py` for PID checks
- `LoopState` dataclass — already supports all needed fields with defaults

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Documents FSM persistence module and `list_running_loops` API |
| architecture | docs/ARCHITECTURE.md | FSM system design context |

## Labels

`bug`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-30T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c781d736-a85e-47b1-9ef5-625122a2c2ae.jsonl`

---

## Status

**Open** | Created: 2026-03-30 | Priority: P3
