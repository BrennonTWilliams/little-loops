---
id: BUG-2137
captured_at: '2026-06-14T03:05:18Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
status: done
relates_to:
- ENH-1164
- FEAT-1654
confidence_score: 98
outcome_confidence: 81
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 20
---

# BUG-2137: `ll-loop simulate` is not sub-loop-aware — runs real child loops or errors on dynamic dispatch

## Summary

`FSMExecutor._execute_sub_loop()` ignores the active `SimulationActionRunner`.
During `ll-loop simulate`, a `loop:` (sub-loop dispatch) state does not get a
simulated verdict like every other action type — instead the executor tries to
**actually load and run the child FSM**. For a statically-named sub-loop this
means real execution with real side effects in simulation mode; for a
dynamically-named sub-loop (`loop: "${captured...}"`) it raises and aborts the
whole simulation.

This is the same bug class as ENH-1164 (`ll-loop simulate` silently bypassed
`parallel:` states by invoking the real `ParallelRunner`). ENH-1164 fixed the
`parallel:` path but the single-dispatch `_execute_sub_loop` path was never made
simulation-aware.

## Current Behavior

`_execute_sub_loop()` (`scripts/little_loops/fsm/executor.py:517`) unconditionally:

1. `interpolate(state.loop, ctx)` to resolve the child loop name,
2. `resolve_loop_path(...)` + `load_and_validate(...)`,
3. constructs a child `FSMExecutor` and calls `child_executor.run()`.

It never checks `isinstance(self.action_runner, SimulationActionRunner)`. So:

- **Static sub-loop** (`loop: deep-research`): simulate loads and *runs the real
  child loop*, including its real shell/prompt/MCP side effects — violating the
  simulate guarantee of "no side effects."
- **Dynamic sub-loop** (`loop: "${captured.chosen.output}"`, e.g. `loop-router`'s
  `dispatch` state): in simulation there are no real captures, so interpolation
  raises `InterpolationError` ("Path '...' not found", `interpolation.py:133`).
  The dispatch guard at `executor.py:854` only catches `(FileNotFoundError,
  ValueError)`, so `InterpolationError` escapes the declared `on_error` route and
  the executor terminates with `terminated_by="error"`.

Observed via `/ll:review-loop loop-router`:

```
States visited: ... → select_loop → dispatch
Iterations: 8  |  Terminated by: error (at dispatch)
```

The `dispatch` state declares `on_error: review`, but it never fires because the
raised exception type isn't caught.

## Expected Behavior

`ll-loop simulate` on a loop containing a `loop:` state should preview the
loop's logic with no real child execution, mirroring the ENH-1164 / FEAT-1076
treatment of `parallel:` states:

- In simulation mode, `_execute_sub_loop` routes the dispatch through the active
  `SimulationActionRunner` (emit a sim event, take a scenario/interactive
  verdict) instead of loading and running the real child FSM.
- The state routes via its declared `on_yes` / `on_no` / `on_error` so downstream
  flow (`dispatch → review → present_result`) is traceable.
- Simulate never aborts on an unresolved dynamic `loop:` name — a dynamic
  reference that can't resolve in simulation yields a simulated verdict, not a
  hard error.

## Impact

`simulate` is the primary safe-preview path for loop authoring and review
(`ll-loop simulate`, `/ll:review-loop`). Today it is either unsafe or broken for
**any** loop containing a `loop:` dispatch state:

- **Static sub-loops**: simulate loads and runs the real child FSM, producing real
  shell/prompt/MCP side effects (file writes, spawned sessions, worktrees) during a
  run that is contractually side-effect-free. Users cannot trust simulate to be a
  dry run.
- **Dynamic sub-loops** (e.g. `loop-router`'s `dispatch` state): simulate aborts
  with `Terminated by: error`, so the loop's flow past `dispatch` can never be
  previewed or reviewed — `/ll:review-loop loop-router` is effectively blocked.

Net effect: loop-router and every other dynamic-dispatch loop cannot be reviewed
via simulate, and statically-dispatching loops leak side effects in a mode that
promises none — eroding trust in simulate's core guarantee.

## Root Cause

`scripts/little_loops/fsm/executor.py:517` — `_execute_sub_loop()` has no
simulation-mode branch; it always performs real child-loop load + run. Secondary
contributor: `executor.py:854` dispatch guard `except (FileNotFoundError,
ValueError)` does not include `InterpolationError`, so even the existing
`on_error` route is unreachable for the dynamic-name failure mode.

## Steps to Reproduce

```bash
ll-loop simulate loop-router
# → traces through to `dispatch`, then `Terminated by: error`
```

Any loop with a `loop:` dispatch state reproduces the class:
- dynamic name → spurious `error` termination
- static name → real child loop execution during "simulation"

## Proposed Solution

Mirror the ENH-1164 fix shape. In `_execute_sub_loop()`, before resolving and
running the child:

```python
from little_loops.fsm.runners import SimulationActionRunner
if isinstance(self.action_runner, SimulationActionRunner):
    # Dry-run: take a simulated verdict instead of loading/running the child.
    # Emit a sub-loop sim event, get a verdict from the runner, and route via
    # on_yes / on_no / on_error like every other simulated state.
    return self._route_simulated_sub_loop(state, ctx)
```

Design decision (matches ENH-1164 rationale): **stub all sub-loop dispatch in
simulation** rather than recursively simulating into statically-named children —
keeps simulate scoped to the current loop's flow and avoids real side effects.
(Recursive simulation of static sub-loops can be a follow-up if desired.)

Secondary fix: widen the dispatch guard at `executor.py:854` to include
`InterpolationError` (import from `little_loops.fsm.interpolation`) so that even
outside simulation, an unresolved dynamic `loop:` name honors the state's
declared `on_error` route instead of crashing the parent loop. On `loop-router`'s
live path `chosen` is always written, so this is defense-in-depth — but other
dynamic-dispatch loops could hit it.

## Acceptance Criteria

- [ ] `ll-loop simulate loop-router` reaches a terminal state (e.g.
      `dispatch → review → present_result`) and reports `Terminated by: terminal`,
      not `error`.
- [ ] A static-name sub-loop dispatch in simulation does **not** execute the real
      child loop (no real shell/prompt/MCP side effects, no worktrees).
- [ ] The sub-loop state's `on_yes` / `on_no` / `on_error` routes are honored from
      the simulated verdict (scenario and interactive modes).
- [ ] `_execute_sub_loop` (or its dispatch guard) catches `InterpolationError` so
      an unresolved dynamic `loop:` name routes to `on_error` instead of
      terminating the parent with `error`.
- [ ] Regression test: simulate a fixture loop with both a static and a dynamic
      `loop:` dispatch state; assert no real child execution and correct routing.

## Labels
`bug`, `fsm`, `simulate`, `loop`, `executor`

## Session Log
- `/ll:ready-issue` - 2026-06-14T03:19:33 - `58c8bef7-a9e2-4ed7-ae26-35578f5ac021.jsonl`
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `499b430f-0ce7-4210-8d01-bbcbfc6376a5.jsonl`
- `/ll:format-issue` - 2026-06-14T03:08:26 - `4bd1cae0-db78-4e6f-ad33-68b306916879.jsonl`
- `/ll:capture-issue` - 2026-06-14T03:05:18Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be36bd17-64b3-426c-82dd-0410d90c2280.jsonl`

---

## Status

- **State**: open
- **Priority**: P2
