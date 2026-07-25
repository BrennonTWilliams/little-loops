---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
status: open
parent: EPIC-2790
---

# BUG-2777: `_run_cmd` per-command timeout not enforced while subprocess holds stdout open

## Summary

`runner_spec._run_cmd` advertises a "deadlock-safe" `spec.timeout` contract
(`timed_out=True`, exit code 2), but the timeout is only passed to
`process.wait(timeout=...)`, which runs *after* `for line in process.stdout:`
has fully drained to EOF. That read loop is a blocking read that returns only
when the child closes stdout — it does not respect `spec.timeout` at all. A
command that hangs while keeping stdout open blocks the whole call forever.

## Location

- **File**: `scripts/little_loops/runner_spec.py`
- **Line(s)**: 137-178 (blocking read loop at 158-160, at scan commit: fb567390)
- **Anchor**: `in function _run_cmd()`
- **Code**:
```python
    try:
        assert process.stdout is not None
        for line in process.stdout:
            stdout_chunks.append(line)
        process.wait(timeout=spec.timeout)
    except subprocess.TimeoutExpired:
```

## Current Behavior

`spec.timeout` only bounds the final `process.wait()`. If the child never
exits (blocked on a lock, hung network call, or idle but alive), the
`for line in process.stdout` loop never reaches EOF and the caller blocks
indefinitely; `timed_out=True` is never reported.

## Expected Behavior

The entire command execution — including the stdout drain — is bounded by
`spec.timeout`. On expiry the process is terminated/killed and
`RunnerResult(timed_out=True, exit_code=2)` is returned as documented.

## Steps to Reproduce

1. `run_action` (or the `ll-action`/`ll-harness` CMD runner) with
   `ActionSpec(runner=RunnerType.CMD, target="sleep 9999", timeout=1)`.
2. `bash -c "sleep 9999"` keeps stdout open without writing; the read loop
   blocks until process exit (never).
3. Observe the call hangs indefinitely instead of failing after 1 second.

## Proposed Solution

Enforce the deadline around the drain, e.g. run the stdout drain in a reader
thread (mirroring the existing stderr-drain thread) and use
`process.wait(timeout=remaining)` / a monotonic deadline, killing the process
group on expiry; or use `communicate(timeout=spec.timeout)` semantics with
explicit kill + final drain on `TimeoutExpired`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **A working fix for the identical defect already exists** in
  `scripts/little_loops/fsm/runners.py:218-306` (`DefaultActionRunner.run()`,
  shell-command branch). It replaced the same blocking
  `for line in process.stdout` pattern with a `selectors.DefaultSelector`
  bounded-poll loop: both `process.stdout` and `process.stderr` are
  registered on one selector, a wall-clock `deadline = time.time() + timeout`
  is computed up front, and `sel.select(timeout=min(1.0, remaining))` is
  polled so the deadline is re-checked at least once per second even when no
  data is ever ready. On expiry it calls `_kill_process_group(process)`
  (line 282) then a bounded `process.wait(timeout=5)` with a final
  `process.kill()` fallback. This is a stronger fix than the thread-mirroring
  approach the issue proposes — it also protects the `stderr` path (currently
  a plain blocking-iterator thread, not deadline-aware) and closes stdin
  deadlocks for both pipes with one mechanism, at the cost of switching
  `_run_cmd`'s drain style from thread-based to selector-based.
- **`_kill_process_group`** (`scripts/little_loops/subprocess_utils.py:286-296`)
  is the shared SIGKILL-the-process-group helper already imported by
  `fsm/runners.py:26` and `fsm/executor.py:1868`. `runner_spec.py` does not
  currently import it — the existing `_run_cmd` timeout branch
  (`runner_spec.py:163`) does a single-PID `process.kill()`, not a
  process-group kill. **Caveat**: `_kill_process_group`'s `os.getpgid`/
  `os.killpg` targeting requires the child be spawned with a new session
  (`start_new_session=True`); neither `_run_cmd`'s `Popen` call
  (`runner_spec.py:139-144`) nor `fsm/runners.py`'s shell-branch `Popen` call
  passes that flag today, so adopting `_kill_process_group` here should add
  `start_new_session=True` to the `Popen(...)` call as part of the same fix,
  or the process-group kill silently falls back to single-PID via the
  `except (ProcessLookupError, PermissionError, AttributeError)` clause.
- **Callers unaffected by this bug**: FSM `shell` states do **not** go
  through `runner_spec._run_cmd` — they use `fsm/runners.py`'s already-fixed
  selector-based path, a separate `ActionResult` type. Only direct
  `run_action(ActionSpec(runner=RunnerType.CMD, ...))` callers hit this
  dead-zone: `ll-harness cmd` (`scripts/little_loops/cli/harness.py:369-389`,
  `cmd_cmd()`, consumed by `_evaluate_and_report()` at lines 251-262) and
  `ll-queue run` (`scripts/little_loops/cli/queue.py:226-262`, `cmd_run()`,
  which gates queue-entry `status="done"` on
  `not result.timed_out and result.error is None and result.exit_code == 0`).
  `ll-action` (`scripts/little_loops/cli/action.py`) only dispatches
  `RunnerType.SKILL`, so it's not affected.
- **No existing test covers the hang scenario for `_run_cmd`.**
  `scripts/tests/test_runner_spec.py:125` (`test_cmd_dispatch_matches_legacy_shape`)
  is the only current CMD-runner test and only exercises the happy path
  (`echo hi`, `timeout=5`). `scripts/tests/test_fsm_runners.py` already has
  the precedent to follow for the fixed behavior:
  `test_timeout_returns_exit_code_124` (line 284, mocks
  `selectors.DefaultSelector` to always return no ready pipes, forcing the
  deadline check to fire), and `test_hanging_process_timeout_fires_during_read`
  (line 327, explicitly simulates a process that registers pipes but never
  produces output — the exact `sleep 9999` scenario from this issue's Steps
  to Reproduce). A new `_run_cmd` test should mirror one of these two shapes.

## Impact

- **Severity**: High
- Affects every CMD-runner consumer: `ll-action`, `ll-harness`, `ll-queue run`,
  and FSM states dispatched through `run_action()`. A single hung target stalls
  automation (ll-auto/autodev) indefinitely with no timeout signal.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:refine-issue` - 2026-07-25T02:40:30 - `3a8a63cc-0c0e-4123-b57d-508caf76f178.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:55 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
