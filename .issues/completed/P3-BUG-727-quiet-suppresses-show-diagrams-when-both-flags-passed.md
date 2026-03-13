---
id: BUG-727
priority: P3
type: BUG
status: completed
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# BUG-727: `--quiet` suppresses `--show-diagrams` when both flags passed

## Problem Statement

When running `ll-loop run` with both `--quiet` and `--show-diagrams`, the diagram is never displayed. The `--quiet` flag unconditionally skips wiring the `_on_event` observer, which suppresses all per-iteration output including the FSM diagram. The two flags should not be mutually exclusive — passing both should show only the FSM diagram each iteration, with all other progress output suppressed.

## Steps to Reproduce

1. Create or use any loop config
2. Run: `ll-loop run <loop-name> --quiet --show-diagrams`
3. Observe: no output is produced, not even the FSM diagram

## Expected Behavior

When `--quiet` and `--show-diagrams` are both passed, the FSM loop diagram should be printed each iteration (with the active state highlighted), and all other progress output (iteration counter, action lines, completion summary) should be suppressed.

## Actual Behavior

The FSM diagram is not shown. `--quiet` silences everything, including the diagram that `--show-diagrams` requests.

## Root Cause

In `scripts/little_loops/cli/loop/_helpers.py`:

- The `display_progress` callback (which handles diagram rendering and all other per-iteration output) is only wired via `executor._on_event = display_progress` when `not quiet` (line ~409).
- When `--quiet` is set, `_on_event` is never assigned, so the diagram code at lines ~304-310 never executes.

The fix should allow `_on_event` to be wired when `show_diagrams` is true, but the `display_progress` callback should skip all non-diagram output when `quiet=True`.

## Affected Files

- `scripts/little_loops/cli/loop/_helpers.py` — `run_loop_command` function, specifically the `display_progress` inner function and the `not quiet` guard at the end

## Implementation Steps

1. In `display_progress`, wrap all non-diagram output branches with `if not quiet:` guards:
   - `iteration_start` event: print diagram unconditionally (already conditional on `show_diagrams`), but wrap the iteration counter/elapsed line with `if not quiet:`
   - `action_start`, `action_output`, `action_complete`, `transition` events: wrap with `if not quiet:`
2. Change the `_on_event` wiring condition from `if not quiet:` to `if not quiet or show_diagrams:`
3. The startup prints (`Running loop: ...`, `Max iterations: ...`) remain gated on `not quiet`
4. The completion summary also remains gated on `not quiet`

## Acceptance Criteria

- [x] `ll-loop run <name> --quiet --show-diagrams` prints only the FSM diagram each iteration
- [x] `ll-loop run <name> --quiet` still produces no output
- [x] `ll-loop run <name> --show-diagrams` still produces diagram + full progress output
- [x] `ll-loop run <name>` unchanged behavior

## Impact

- **Priority**: P3 - Quality-of-life issue; `--quiet --show-diagrams` is a valid use case but not blocking
- **Effort**: Small - Isolated change in `display_progress` inner function and one wiring condition; no new patterns needed
- **Risk**: Low - Change is additive (expanding when `_on_event` fires), existing quiet behavior preserved by new guards
- **Breaking Change**: No

## Labels

`cli`, `loop`, `quiet`, `ux`, `show-diagrams`

## Resolution

Fixed in `scripts/little_loops/cli/loop/_helpers.py` (`run_foreground` function):

1. Changed `_on_event` wiring from `if not quiet:` to `if not quiet or show_diagrams:` so the observer fires when diagrams are requested.
2. Wrapped all non-diagram output in `display_progress` with `if not quiet:` guards (`action_start`, `action_output`, `action_complete`, `evaluate`, `route`, and the iteration counter in `state_enter`).
3. The `show_diagrams` rendering in `state_enter` remains unconditional (fires whenever `show_diagrams=True`).

## Session Log
- `/ll:capture-issue` - 2026-03-13T21:02:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/061c4027-a532-4555-8c34-f7d8243ccfa1.jsonl`
- `/ll:ready-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/84fb1cbd-f07a-49d2-b424-da370d4e2f3a.jsonl`
- `/ll:manage-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

**Completed** | Created: 2026-03-13 | Priority: P3
