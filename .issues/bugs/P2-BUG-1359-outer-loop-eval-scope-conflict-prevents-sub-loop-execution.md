---
id: BUG-1359
title: outer-loop-eval scope conflict prevents sub-loop execution on every invocation
priority: P2
type: BUG
status: done
completed_at: 2026-05-03T00:00:00Z
---

## Problem

`outer-loop-eval` always failed to run its sub-loop. The `run_sub_loop` state shelled out to
`ll-loop run "${context.loop_name}"` as a subprocess, which went through the full CLI lock path.
Since `outer-loop-eval` was itself launched via `ll-loop run` and already held the project-root
scope lock (`"."`), the subprocess immediately hit `LockManager.acquire()`, found the conflict,
and exited with code 1 — every single invocation, not situationally.

The `--queue` flag would have deadlocked: the child waits for the parent's lock, the parent waits
for the child to finish.

Because `on_error: analyze_execution` routed correctly, the FSM terminated cleanly and the
evaluator passed the report. The failure was silent — the loop produced "improvement reports"
based only on static definition analysis and an error message, never real execution data.

## Root Cause

Three compounding issues:

1. **Shell approach used CLI lock path**: `action_type: shell` + `ll-loop run` spawns a subprocess
   that calls `cmd_run()` → `LockManager.acquire()`. The native in-process path
   (`FSMExecutor._execute_sub_loop()`) never touches `LockManager` and is immune to scope
   conflicts. `outer-loop-eval` should have used the native path from the start.

2. **`state.loop` field was not interpolated**: In `_execute_sub_loop`, `state.loop` was passed
   directly to `resolve_loop_path()` without context interpolation. Writing
   `loop: "${context.loop_name}"` in a YAML state would pass the literal string, not the resolved
   value. This was why the shell workaround existed in the first place — the native loop action
   had no way to accept a dynamic loop name.

3. **Native sub-loop had no event capture mechanism**: `_execute_sub_loop` forwarded child events
   to the parent's log via `_sub_event_callback` but did not buffer them. There was no way to
   reference the sub-loop's execution trace (state transitions, evaluator verdicts, retry counts)
   from downstream states. `analyze_execution` had no real data to work with even if the native
   path were used.

## Fix

**`scripts/little_loops/fsm/executor.py` — `_execute_sub_loop()`**:

- Added `loop_name = interpolate(state.loop, ctx)` before `resolve_loop_path()` so that
  `loop: "${context.loop_name}"` resolves at runtime.
- Added `child_events: list[dict] = []` buffer in `_sub_event_callback` to collect all child
  events during execution.
- After `child_executor.run()`, when `state.capture` is set, stores the child event stream as
  a JSON-lines string under `self.captured[state.capture]` — the same structure as shell action
  captures (`{"output": str, "exit_code": None}`).

**`scripts/little_loops/loops/outer-loop-eval.yaml`** — `run_sub_loop` state:

- Changed from `action_type: shell` + `ll-loop run` to native `loop: "${context.loop_name}"`.
- Added `with: {input: "${context.input}"}` for parameter passing.
- Routing changed from `next/on_error` to `on_yes/on_no/on_error` (all three route to
  `analyze_execution`) — native sub-loop states use yes/no/error routing, not next.
- `capture: sub_loop_output` preserved; now populated with real child event JSON-lines.

**`scripts/tests/test_outer_loop_eval.py`**:

- Updated `test_run_sub_loop_is_shell` → `test_run_sub_loop_is_native_loop` to assert the
  `loop:` field, `with:` binding, and `on_yes/on_no/on_error` routing.
- Updated `test_run_sub_loop_uses_quoted_context_vars` → `test_run_sub_loop_input_binding_uses_context_var`
  to verify `with.input` references `context.input`.

## Impact

`outer-loop-eval` now runs the target loop in-process (no scope conflict) and captures its full
event stream into `sub_loop_output`. `analyze_execution` receives real state-transition data,
retry counts, and evaluator verdicts — the analysis the loop was always designed to produce.

The `interpolate(state.loop, ctx)` fix is a general improvement: any loop using
`loop: "${context.some_var}"` now resolves correctly, not just `outer-loop-eval`.
