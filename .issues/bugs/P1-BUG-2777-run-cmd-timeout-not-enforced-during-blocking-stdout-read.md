---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
status: done
completed_at: '2026-07-25T02:55:02Z'
parent: EPIC-2790
confidence_score: 96
outcome_confidence: 71
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 18
priority: P1
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

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/harness.py` — `cmd_cmd()` (already known caller of `run_action`), but its tests (see Tests below) directly patch `subprocess.Popen`, so they are coupled to `_run_cmd`'s internal drain implementation, not just its public contract.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_harness.py::TestCmdCmd` — **6 tests will break** if `_run_cmd` moves from a blocking `for line in process.stdout` loop to a selector-based drain (mirroring `fsm/runners.py`). All 6 use the class helper `_make_popen_mock()` (line ~314), which sets `mock_proc.stdout = iter(stdout_lines)` / `mock_proc.stderr = iter(stderr_lines)` — plain iterators with no `.fileno()`, which `selectors.DefaultSelector().register(...)` requires. Confirmed by reading the file directly:
  - `test_cmd_captures_stdout` (~line 325) — mocked Popen, would need a selector-compatible stand-in.
  - `test_cmd_exit_code_pass` / `test_cmd_exit_code_fail` (~line 337, ~348) — same mock helper.
  - `test_cmd_no_criteria_always_pass` (~line 359) — same mock helper.
  - `test_cmd_timeout_returns_2` (~line 369) — hard-codes the *current* call sequence via `mock_proc.wait.side_effect = [subprocess.TimeoutExpired(...), None]`; a selector/deadline-based rewrite checks wall-clock time instead of relying on `process.wait(timeout=N)` raising, so this test's premise needs to be rewritten to simulate a hang through the selector interface (mirroring `test_fsm_runners.py::test_hanging_process_timeout_fires_during_read`'s approach), not `Popen.wait`.
  - `test_cmd_json_output` (~line 385) — same mock helper.
  - Fix: update `_make_popen_mock()` (or add a selector-aware sibling helper) to match the `_make_selector_mock_process()` / `_make_ready_selector()` pattern already established in `scripts/tests/test_fsm_runners.py:42,62`.
- `scripts/tests/test_runner_spec.py::TestRunActionDispatch` — no CMD-timeout/hang test exists at this layer today (only `test_cmd_dispatch_matches_legacy_shape`, unmocked happy path). Add a new test mirroring `test_fsm_runners.py::test_hanging_process_timeout_fires_during_read` (line 327) and `test_timeout_returns_exit_code_124` (line 284), patching `little_loops.runner_spec.subprocess.Popen` / the selector primitive the fix introduces / `little_loops.runner_spec._kill_process_group` (if adopted), asserting the hang is caught without waiting for stdout EOF.
- `scripts/tests/test_cli_queue.py`, `scripts/tests/test_queue_store.py` — checked, **not affected**: both only assert `entries[0].action.runner == RunnerType.CMD` on stored/classified entries, never execute the command.
- `scripts/tests/test_cli_queue_run.py` — checked, **not affected**: patches `little_loops.runner_spec.run_action` directly, never exercises `_run_cmd`'s internals.

### Implementation Decision Flagged

_Wiring pass added by `/ll:wire-issue`:_
- The current `_run_cmd` timeout path returns `exit_code=2`; the `fsm/runners.py` precedent this fix is modeled on returns `exit_code=124`. This value is persisted verbatim into `.ll/queue.db` by `cli/queue.py`'s `run_action` result handler (exposed via `ll-queue status --json` / `ll-queue list --json`), though `cli/harness.py::_evaluate_and_report()` always normalizes the CLI exit code to `2` on `timed_out` regardless of the internal value. Decide whether to keep `2` (matching `_run_skill`/`_run_prompt` siblings in the same file) or switch to `124` (matching the `fsm/runners.py` precedent) before implementing, and note the choice in the fix's commit/PR description.

## Impact

- **Severity**: High
- Affects every CMD-runner consumer: `ll-action`, `ll-harness`, `ll-queue run`,
  and FSM states dispatched through `run_action()`. A single hung target stalls
  automation (ll-auto/autodev) indefinitely with no timeout signal.

## Resolution

Fixed `runner_spec._run_cmd` to enforce `spec.timeout` across the entire
command execution, not just the final `process.wait()`. Replaced the
blocking `for line in process.stdout` drain (with a separate stderr thread)
with a `selectors.DefaultSelector`-based bounded-poll loop mirroring
`fsm/runners.py`'s `DefaultActionRunner.run()` shell-command branch: both
stdout and stderr are registered on one selector, a wall-clock deadline is
computed up front, and `sel.select(timeout=min(1.0, remaining))` re-checks
the deadline at least once per second even when no data is ready. On expiry,
the process group is killed via `_kill_process_group` (added
`start_new_session=True` to the `Popen` call so process-group targeting
works). Kept `exit_code=2` on timeout (unchanged from prior behavior),
matching the `_run_skill`/`_run_prompt` siblings in the same file rather than
switching to `fsm/runners.py`'s `124` — `_run_cmd` is exposed as a distinct
public contract (`ll-harness cmd`, `ll-queue run`) with its own established
`exit_code=2` convention that predates this fix.

Updated the 6 `TestCmdCmd`/`TestSemanticEvaluator`/`TestMainHarness` tests in
`test_cli_harness.py` that mocked `Popen` with plain iterators (incompatible
with `selectors.DefaultSelector.register()`, which requires `.fileno()`) to
use a selector-compatible mock file object, and added a
`test_cmd_hang_before_stdout_eof_times_out` regression test in
`test_runner_spec.py` mirroring `test_fsm_runners.py`'s hang-scenario
coverage.

## Status

`done` — fixed by `/ll:manage-issue`.

## Session Log
- `/ll:confidence-check` - 2026-07-24T00:00:00 - `0a8aa66d-fe3d-4eb6-99f6-413c2318a962.jsonl`
- `/ll:wire-issue` - 2026-07-25T02:45:32 - `a5b701d1-3488-48e0-aa1d-c004d7ded01b.jsonl`
- `/ll:refine-issue` - 2026-07-25T02:40:30 - `3a8a63cc-0c0e-4123-b57d-508caf76f178.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:55 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
