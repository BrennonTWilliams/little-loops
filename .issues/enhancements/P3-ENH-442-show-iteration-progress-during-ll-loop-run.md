---
discovered_date: 2026-02-19
discovered_by: capture-issue
---

# ENH-442: Show Iteration Progress During ll-loop Run

## Summary

When running `ll-loop run <loop-name>`, no per-iteration output is shown between the start message and final summary. Users have no visibility into which state/iteration the loop is executing.

## Current Behavior

The terminal shows only a start message and a final summary — nothing is printed between iterations. The `run_foreground` function in `scripts/little_loops/cli/loop/_helpers.py` contains a `display_progress` callback and a `combined_handler` that are intended to intercept events, but the event wiring is broken: `object.__setattr__(executor, "_handle_event", combined_handler)` replaces the instance attribute, but `FSMExecutor` already holds a bound method reference to the original `PersistentExecutor._handle_event` and never calls the combined handler.

**Current output:**
```
ll-loop run tests-until-passing
Running loop: tests-until-passing
Max iterations: 20


Loop completed: evaluate (20 iterations, 18m 12s)
```

## Expected Behavior

Each iteration prints a summary line including iteration number, current state, elapsed time, and any evaluator status.

**Example output:**
```
ll-loop run tests-until-passing
Running loop: tests-until-passing
Max iterations: 20

[iter  1] state: evaluate  (0s)
[iter  2] state: fix       (12s)
[iter  3] state: evaluate  (45s)
...
[iter  8] state: evaluate  (3m 02s)

Loop completed: evaluate (8 iterations, 3m 14s)
```

## Motivation

Iteration-level output gives users:
- Confidence the loop is still running (not hung)
- Awareness of which state/transition is executing
- Ability to spot runaway or stuck loops early
- A natural audit trail without needing to dig into logs

## Proposed Solution

Fix the event callback wiring in `run_foreground` (anchor: `run_foreground` in `scripts/little_loops/cli/loop/_helpers.py`) so that per-iteration output is actually emitted. The `FSMExecutor` must receive the progress-aware callback at init time, not via post-hoc instance attribute replacement.

Options:
1. Pass a callback chain to `PersistentExecutor.__init__` so `FSMExecutor` is initialized with it directly
2. Refactor `PersistentExecutor._handle_event` to delegate to a configurable secondary callback
3. Add an `on_event` parameter to `PersistentExecutor` constructor

Then add elapsed-time tracking per iteration using `time.monotonic()` at the `state_enter` event, and format it consistently with the final summary format.

A `--quiet` / `-q` flag stub already exists in `run_foreground` (the `quiet` variable is read from `args`), so quiet suppression is structurally in place once wiring is fixed.

## Implementation Steps

1. Fix event wiring: add `on_event` callback parameter to `PersistentExecutor.__init__` in `scripts/little_loops/fsm/persistence.py` and pass it through to `FSMExecutor`
2. Update `run_foreground` in `scripts/little_loops/cli/loop/_helpers.py` to pass `display_progress` as `on_event` instead of using `object.__setattr__`
3. Add per-iteration elapsed time: capture `time.monotonic()` at `state_enter` events and format as `(Ns)` or `(Nm Ss)`
4. Ensure `print(..., flush=True)` on each iteration line so output appears immediately
5. Update tests in `scripts/tests/test_ll_loop_execution.py` to verify per-iteration output appears (and is suppressed with `--quiet`)

## Acceptance Criteria

- Each iteration prints at least: iteration number, current state, elapsed time
- Output is flushed immediately (not buffered until loop end)
- A `--quiet` flag suppresses per-iteration output
- Existing tests pass; new test covers iteration output format
- The broken `object.__setattr__` approach is removed

## Scope Boundaries

- Out of scope: changing the log file format or JSONL event schema
- Out of scope: adding color/ANSI formatting (keep plain text)
- Out of scope: CI/structured output mode (only `--quiet` suppression)
- Out of scope: progress bars or cursor manipulation

## Impact

- **Priority**: P3 - Nice-to-have UX improvement; long-running loops feel like a black box
- **Effort**: Small - event wiring fix is surgical; display logic already drafted in `_helpers.py`
- **Risk**: Low - only affects stdout display output, not execution logic
- **Breaking Change**: No

## Labels

`enhancement`, `ux`, `ll-loop`, `display`, `cli`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM execution model |
| `docs/API.md` | ll-loop CLI interface |

## Session Log
- `/ll:capture-issue` - 2026-02-19T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/666e6476-c463-40da-8d36-80a83167d17e.jsonl`
- `/ll:manage-issue` - 2026-02-19T00:00:00Z - implemented

---
## Resolution

**Completed**: 2026-02-19

### Changes Made

1. **`scripts/little_loops/fsm/persistence.py`**
   - Imported `EventCallback` from `executor`
   - Added `self._on_event: EventCallback | None = None` slot to `PersistentExecutor.__init__`
   - Added delegation call `if self._on_event is not None: self._on_event(event)` at end of `_handle_event`

2. **`scripts/little_loops/cli/loop/_helpers.py`**
   - Added `import time`
   - Added `loop_start_time = time.monotonic()` before progress callback definition
   - Updated `state_enter` handler in `display_progress` to compute and print elapsed time as `(Xs)` / `(Xm Xs)`, with `flush=True`
   - Added `flush=True` to all other `print()` calls in `display_progress`
   - Replaced broken `object.__setattr__(executor, "_handle_event", combined_handler)` with `executor._on_event = display_progress` set directly on the proper observer slot

3. **`scripts/tests/test_ll_loop_execution.py`**
   - Added `test_per_iteration_progress_shows_state_and_elapsed`: verifies `[1/3] check` and `(0s)` appear in output
   - Added `test_per_iteration_progress_suppressed_by_quiet`: verifies `--quiet` suppresses per-iteration lines

### Root Cause

`FSMExecutor` stores `event_callback` as a direct bound-method reference at construction time. The `object.__setattr__` patch in `run_foreground` only updated `PersistentExecutor.__dict__["_handle_event"]` — `FSMExecutor.event_callback` was never affected and always called the original handler.

---
## Status

**State**: completed
