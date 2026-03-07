---
discovered_date: 2026-03-07T00:00:00Z
discovered_by: capture-issue
---

# BUG-639: `ll-loop stop` Continues for Several More Iterations After Stop Command

## Summary

After running `ll-loop run issue-refinement -v` and issuing `ll-loop stop issue-refinement` at iteration 74, the loop did not stop — it continued running for several more iterations before halting.

## Current Behavior

1. User runs `ll-loop run issue-refinement -v` (verbose/foreground mode)
2. At iteration 74, user runs `ll-loop stop issue-refinement` from another terminal
3. Loop continues executing for several more iterations instead of stopping promptly

## Expected Behavior

After `ll-loop stop`, the loop should halt within at most 1 additional iteration — either immediately if between iterations, or by completing the in-flight iteration and then stopping. No more than 1 full iteration should execute after the stop command is issued. Continuing for multiple iterations after stop is a failure of the shutdown mechanism.

## Acceptance Criteria

- [ ] In verbose/foreground mode (`ll-loop run <name> -v`): after `ll-loop stop <name>` is issued, no more than 1 additional iteration completes before the loop exits
- [ ] In background mode (`ll-loop run <name>`): after `ll-loop stop <name>` is issued, no more than 1 additional iteration completes before the loop exits

## Motivation

Users rely on `ll-loop stop` to control loop execution. If stop is ignored for multiple iterations, the loop may cause unintended side effects (e.g., modifying files, consuming API quota, changing issue state). This is especially problematic for refinement loops that mutate issue files.

## Root Cause

Unknown — investigation needed. BUG-592 (fixed 2026-03-05) addressed `ll-loop stop` not stopping promptly due to blocking subprocess I/O. That fix added `_current_process` tracking in `DefaultActionRunner` and an escalating SIGKILL backstop in `cmd_stop`. Possible causes for this regression/variant:

- **Verbose mode code path**: `ll-loop run -v` may use a different executor or signal handler path that bypasses the BUG-592 fix
- **Shutdown flag not propagated**: `_shutdown_requested` flag may not be checked between every iteration in the persistent execution loop (`PersistentExecutor`)
- **Stop state file not read**: `cmd_stop` writes a stop signal via the state file; if the running loop reads the file infrequently or only at certain checkpoints, several iterations may complete before the flag is noticed
- **Regression**: A recent change may have broken the SIGTERM → process kill path introduced in BUG-592

**Key difference from BUG-592**: BUG-592 reported the loop continuing for one long-running iteration (blocked in subprocess I/O). This issue reports *several more iterations*, suggesting the shutdown flag is either not being set or not being checked between iterations.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Most likely root cause — foreground mode has no PID file, so `cmd_stop` never sends SIGTERM:**

- `run.py:70` — in `cmd_run`, `foreground_pid_file` is set to `None` by default. It is only set to a real path when the `--foreground-internal` flag is present (`run.py:71`), which is only used when re-exec'd from `run_background()`.
- Plain `ll-loop run issue-refinement -v` (without `--background`) never writes a `.pid` file.
- `lifecycle.py:111–112` — `cmd_stop` reads the PID file at `loops_dir / ".running" / f"{loop_name}.pid"`. For a foreground run, this file does not exist, so `pid` is `None`.
- `lifecycle.py:136–140` — the no-PID branch only writes `state.status = "interrupted"` to the JSON state file and logs a success message. **No SIGTERM is sent.** The foreground process has no way of knowing stop was requested.
- The `_shutdown_requested` flag on `FSMExecutor` (`executor.py:373`) is therefore never set by an external `cmd_stop` call in foreground mode. The loop continues until it naturally terminates.

**Secondary issue — even in background mode, `_shutdown_requested` is only checked at top of `while True`:**

- `executor.py:403–404` — the only check of `_shutdown_requested` in the main iteration loop is at the very top of `while True`. There is no check inside `_execute_state`, `_run_action`, `_evaluate`, or `_route` (`executor.py:488–602`).
- `executor.py:481–482` — a second check exists only during the optional backoff sleep (interruptible at 100 ms granularity).
- Once the loop enters `_run_action`, it blocks in `DefaultActionRunner.run()` at `executor.py:179` (`for line in process.stdout`), which is a blocking line-by-line read until the child process exits. The signal handler at `_helpers.py:53–59` calls `proc.kill()` on `_current_process` to unblock this, but only if SIGTERM was actually delivered.

## Steps to Reproduce

1. Start a loop in verbose mode: `ll-loop run issue-refinement -v`
2. Let it run until iteration ~74
3. In another terminal, run: `ll-loop stop issue-refinement`
4. Observe that the loop continues executing multiple more iterations

## Proposed Solution

1. Confirm whether BUG-592 fix is still intact (check `executor.py::DefaultActionRunner._current_process` tracking and `lifecycle.py::cmd_stop` SIGKILL backstop)
2. Check if `PersistentExecutor`'s iteration loop checks `_shutdown_requested` between every state transition, not just inside action runners
3. Verify the SIGTERM signal is actually delivered to the foreground process when `ll-loop stop` is called (the stop mechanism may differ for foreground vs background processes)
4. Add a test that verifies stop halts execution within one iteration in both foreground and background modes

## Implementation Steps

1. Check `scripts/little_loops/cli/loop/run.py` — does `_loop_signal_handler` get registered in verbose/foreground mode?
2. Check `scripts/little_loops/cli/loop/lifecycle.py::cmd_stop` — does it look up the PID differently for foreground processes?
3. Check `scripts/little_loops/fsm/persistence.py::PersistentExecutor` — where is `_shutdown_requested` checked in the iteration loop?
4. Review `ll-loop-issue-refinement.log` (user-provided) for the exact iterations that ran after stop was issued
5. Fix the gap and add regression test

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — check `_loop_signal_handler` registration in verbose/foreground mode
- `scripts/little_loops/cli/loop/lifecycle.py` — check `cmd_stop` PID lookup and SIGTERM/SIGKILL path for foreground processes
- `scripts/little_loops/fsm/persistence.py` — check `PersistentExecutor` iteration loop for `_shutdown_requested` check placement

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:35–78` — contains `_loop_signal_handler` (sets `_loop_shutdown_requested` and calls `executor.request_shutdown()`) and `register_loop_signal_handlers`; also contains the `_current_process.kill()` path (`_helpers.py:52–59`) that is the BUG-592 fix
- `scripts/little_loops/cli/loop/_helpers.py:62–78` — `register_loop_signal_handlers` called from `run.py:112` for both foreground and background modes
- `scripts/little_loops/fsm/executor.py:373` — `_shutdown_requested` declared on `FSMExecutor`
- `scripts/little_loops/fsm/executor.py:387` — `request_shutdown()` sets `_shutdown_requested = True`
- `scripts/little_loops/fsm/executor.py:599–600` — in-band stop via `signal_detector.detect_first(result.output)` (action output path)
- `scripts/little_loops/fsm/signal_detector.py` — stop signal detection from action stdout

### Similar Patterns
- `_helpers.py:52–59` — BUG-592 fix: `_current_process.kill()` in `_loop_signal_handler` to interrupt the blocking subprocess read; verify this is still intact and reachable for foreground mode
- `executor.py:481–482` — backoff sleep shutdown check (interruptible at 100 ms); the only existing mid-iteration shutdown check
- `lifecycle.py:116–130` — `cmd_stop` SIGTERM → poll → SIGKILL escalation path for background processes (PID file required); the foreground path at `lifecycle.py:136–140` only writes state
- BUG-600 (`completed/P2-BUG-600-cmd-resume-missing-signal-handlers.md`) — prior gap where signal handlers were not registered on `cmd_resume`; similar pattern of a foreground code path missing handler registration

### Tests
- TBD — add regression test verifying stop halts within 1 iteration in foreground and background modes

### Documentation
- N/A

### Configuration
- N/A

## Related Issues

- **BUG-592** (completed 2026-03-05): `ll-loop stop` only marks state "interrupted" without killing running processes — prior fix for related stop behavior; this may be a regression or a gap in that fix

## Labels

`bug`, `ll-loop`, `process-management`, `signal-handling`, `regression`

## Session Log
- `/ll:capture-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da7dc305-837f-4e45-9a7f-90e7eae114d2.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c428d45b-7ea7-4ea3-89cd-1ed4a2a48023.jsonl`

---

## Status

**State**: Open
**Priority**: P3
