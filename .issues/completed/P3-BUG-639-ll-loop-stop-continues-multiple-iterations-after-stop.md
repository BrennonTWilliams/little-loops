---
discovered_date: 2026-03-07T00:00:00Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 90
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

1. **Confirm foreground PID gap** — `run.py:70–81`: verify `foreground_pid_file` is `None` for plain `ll-loop run <name> -v`. Fix: write a PID file for foreground runs (same path as background) so `cmd_stop` can send SIGTERM.
2. **Fix `cmd_stop` foreground path** — `lifecycle.py:136–140`: the no-PID branch currently only writes state. Fix: either (a) look up the PID via `os.getpid()` equivalent (not applicable from another process) — the real fix is step 1 above (write PID file), or (b) add a state-file-based polling mechanism checked between iterations.
3. **Verify `_shutdown_requested` check placement** — `executor.py:403–404`: confirm the flag is checked at top of `while True` (it is). Consider adding a check at the start of `PersistentExecutor`'s per-iteration wrapper in `persistence.py` if there is one, to ensure it's caught without entering `_execute_state`.
4. **Verify `_loop_signal_handler` is registered** — `run.py:112`: `register_loop_signal_handlers(executor, pid_file=foreground_pid_file)` is called before `run_foreground`. Confirm that with the PID file fix in step 1, the SIGTERM delivery → `_current_process.kill()` path in `_helpers.py:52–59` will unblock the blocking stdout read at `executor.py:179`.
5. **Add regression test** — in `test_cli_loop_lifecycle.py`: simulate `cmd_stop` sending SIGTERM to a foreground process PID; verify loop halts within 1 iteration. Use `MockActionRunner` with call-count guard from `test_fsm_persistence.py:1286–1340` as the iteration-bound assertion pattern.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — `run.py:70–81`: write foreground PID file unconditionally (not just under `--foreground-internal`) so `cmd_stop` can locate and signal the process
- `scripts/little_loops/cli/loop/lifecycle.py` — `lifecycle.py:136–140`: the no-PID branch currently writes state only; once foreground PID file is written (run.py fix), this branch should be revisited; also verify `cmd_stop` SIGTERM path at `lifecycle.py:116`
- `scripts/little_loops/cli/loop/_helpers.py` — `_helpers.py:52–59`: verify `_current_process.kill()` path in `_loop_signal_handler` is reachable and the `_current_process` reference is not `None` at signal delivery time
- `scripts/little_loops/fsm/persistence.py` — verify `PersistentExecutor` delegates `request_shutdown()` to inner `FSMExecutor` correctly; `executor.py:387`

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
- `scripts/tests/test_cli_loop_lifecycle.py` — existing `cmd_stop` tests with `_process_alive` mock; `_loop_signal_handler` registration assertions; SIGTERM/SIGKILL path coverage — add foreground no-PID regression here
- `scripts/tests/test_cli_loop_background.py` — `TestLoopSignalHandler` class with `setup_method`/`teardown_method` global state reset (`_loop_shutdown_requested`, `_loop_executor`, `_loop_pid_file`); BUG-592 regression for `_current_process.kill()` — add foreground signal handler delivery test here
- `scripts/tests/test_fsm_persistence.py:1080–1340` — `PersistentExecutor` shutdown tests: `request_shutdown()` delegation (`1105–1116`), bounded-iteration assertion (`1286–1340`) — follow these patterns for the ≤1 iteration acceptance criterion
- `scripts/tests/test_fsm_executor.py:1723–1813` — `TestSignalHandling` class: pre-run shutdown (`1741–1763`), shutdown from inside runner (`1783–1813`) — closest unit-level model for iteration-count assertions
- New test needed: simulate `cmd_stop` writing state-file only (no PID), verify foreground loop detects it within 1 iteration (currently impossible — this is the bug)

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
- `/ll:refine-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8a0f657-a512-4e80-9946-68695952f105.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9538dd1-f957-415d-b790-afa66f18ac32.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d11c154b-ec01-40ba-bc51-c1eb3dd6ae2f.jsonl`

---

## Resolution

Root cause confirmed: plain foreground runs (`ll-loop run <name> -v`) never wrote a PID file, so `cmd_stop` fell into the no-PID branch and only wrote `state.status = "interrupted"` — no SIGTERM was sent, `_shutdown_requested` was never set, and the loop ran until natural termination.

**Changes**:
- `run.py`: Write PID file (`os.getpid()`) unconditionally for all foreground runs; background-spawned processes (`foreground_internal=True`) skip the write since their parent already wrote the PID via `run_background()`.
- `lifecycle.py` (`cmd_resume`): Same fix; also pass `pid_file` to `register_loop_signal_handlers` so the force-exit path cleans up the PID file.
- Tests: Updated `test_resume_registers_signal_handlers` assertion; added 4 regression tests.

## Status

**State**: Resolved
**Priority**: P3
