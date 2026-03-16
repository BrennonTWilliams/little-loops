---
discovered_date: 2026-03-15
discovered_by: analyze-loop
source_loop: general-task
source_state: execute
confidence_score: 95
outcome_confidence: 71
---

# BUG-770: general-task loop terminated with error in execute state

## Summary

The `general-task` loop failed immediately on its first iteration. After entering the `execute` state, the loop terminated with a `fatal_error` before any action could complete. The run duration was 1ms, indicating the failure occurred at startup or initialization rather than during execution of loop actions.

## Loop Context

- **Loop**: `general-task`
- **State**: `execute`
- **Signal type**: fatal_error
- **Occurrences**: 1
- **Last observed**: 2026-03-16T03:49:10.576296+00:00

## History Excerpt

Events leading to this signal:

```json
[
  {
    "event": "loop_start",
    "ts": "2026-03-16T03:49:10.575094+00:00",
    "loop": "general-task"
  },
  {
    "event": "state_enter",
    "ts": "2026-03-16T03:49:10.575191+00:00",
    "state": "execute",
    "iteration": 1
  },
  {
    "event": "loop_complete",
    "ts": "2026-03-16T03:49:10.576296+00:00",
    "final_state": "execute",
    "iterations": 1,
    "terminated_by": "error"
  }
]
```

## Expected Behavior

The `execute` state should run its configured action and either transition to the next state or retry. A `fatal_error` termination on the very first iteration (1ms duration) should not occur during normal operation.

## Root Cause

- **File**: `.loops/general-task.yaml:8`
- **Anchor**: `execute` state, `action: "${context.input}"`
- **Cause**: The `execute` state action is `"${context.input}"`, which requires `context.input` to be set at runtime. When `ll-loop run general-task` is invoked without a positional `input` argument or `--context input=...`, `fsm.context` remains `{}` and interpolation fails. `interpolate()` raises `InterpolationError("Path 'input' not found in context")` at `interpolation.py:123`. This propagates to the outer `except Exception` at `executor.py:548–549`, which immediately calls `_finish("error")` — no retry, no `on_error` routing.
- **Note on "fatal_error"**: The issue title uses `fatal_error`, which is the `analyze-loop` tool's classification label. The actual `terminated_by` value in the event log is `"error"` — this code path is `executor.py:548`, not the `FATAL_ERROR:` signal path in `signal_detector.py`.

## Proposed Fix

**Option A — Fix the YAML (preferred)**: Add `on_error` to the `execute` state and add a `required_context` declaration (if schema supports it), so a missing `input` triggers a clean failure message instead of an unhandled exception.

**Option B — Fix the executor**: Catch `InterpolationError` specifically before the outer `except Exception` in `executor.py` and surface a clear error message: `"Missing required context: 'input'. Run with: ll-loop run general-task <input>"`

**Option C — Fix the CLI**: In `run.py`, after loading the loop config, validate that all `${context.*}` references used in state actions are present in `fsm.context` before starting execution.

Recommended approach: B + C — make `InterpolationError` produce a user-friendly message at the executor level, and add pre-run validation in the CLI.

1. In `executor.py:548`, add a specific `except InterpolationError` clause above the bare `except Exception` that surfaces a clear "missing context" message.
2. In `run.py`, after the context injection block (line 64), validate that required interpolation variables are present before entering execution.
3. Update `.loops/general-task.yaml` to add `on_error: failed` to the `execute` state as a defensive measure.

## Integration Map

### Files to Modify
- `.loops/general-task.yaml:8` — add `on_error: failed` to `execute` state
- `scripts/little_loops/fsm/executor.py:548` — add specific `except InterpolationError` clause with user-friendly message before the bare `except Exception`
- `scripts/little_loops/cli/loop/run.py:64` — add pre-run validation of required context variables after context injection block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/interpolation.py:123` — `raise InterpolationError(...)` throw site; imported by `executor.py:620` via `interpolate()`
- `scripts/little_loops/fsm/executor.py:620` — `action = interpolate(action_template, ctx)` call in `_run_action()`
- `scripts/little_loops/fsm/executor.py:548–549` — outer `except Exception as exc: return self._finish("error", error=str(exc))`

### Similar Patterns
- `scripts/little_loops/fsm/validation.py` — existing loop validation; model new pre-run checks after this
- `scripts/tests/test_ll_loop_errors.py` — existing error test patterns to follow for new test cases
- `scripts/tests/test_fsm_executor.py` — executor unit tests

### Tests
- `scripts/tests/test_ll_loop_errors.py` — add test: `ll-loop run general-task` without input raises clear error
- `scripts/tests/test_fsm_executor.py` — add test: `InterpolationError` in action produces friendly message, not raw traceback
- `scripts/tests/test_ll_loop_execution.py` — add integration test: `general-task` runs successfully when input is provided. **Before writing this test**, verify the test harness supports positional `input` args for `ll-loop run` (check how other tests in this file invoke the CLI — if they only use `--context key=value`, use that form here rather than the positional form).

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — may need update documenting required `input` context for `general-task`

## Implementation Steps

1. **Fix executor error handling** — In `executor.py`, add `except InterpolationError as exc` above the bare `except Exception` at line 548, surfacing: `"Missing required context variable: {key}. Run with: ll-loop run general-task <input>"`. `InterpolationError` is already imported at line 33 and already caught at line 795 (evaluate path — `except InterpolationError: eval_input = raw_output`); confirm the new clause at line 548 does not change behavior for that existing catch site (it won't — they are in separate try blocks).
2. **Add pre-run CLI validation** — In `run.py`, after the context injection block (line 64), scan all state action templates for `${context.*}` references and verify each key is present in `fsm.context`. Fail early with a clear usage message.
3. **Patch YAML defensively** — In `.loops/general-task.yaml`, add `on_error: failed` to the `execute` state so that any future unhandled errors route to the terminal `failed` state rather than crashing the loop.
4. **Add tests** — In `test_ll_loop_errors.py`, add a test that `ll-loop run general-task` without input produces a clear error (not a raw traceback). In `test_fsm_executor.py`, add a unit test that `InterpolationError` in `_run_action` is caught and returned as a clean error message.

## Acceptance Criteria

- [ ] Root cause of the fatal error in `execute` state is identified (confirmed: missing `context.input`)
- [ ] `ll-loop run general-task <input>` completes at least one full iteration without error
- [ ] `ll-loop run general-task` without input argument prints a clear, actionable error message (not a raw `InterpolationError` traceback)
- [ ] `execute` state in `.loops/general-task.yaml` has `on_error: failed` as a defensive transition
- [ ] `.loops/general-task.yaml` is included in `test_builtin_loops.py` coverage (currently excluded because `BUILTIN_LOOPS_DIR` only scans `loops/`, not `.loops/`)

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-15 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-03-16T04:32:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0bcdd99a-efd4-491b-a30d-9c016b3f4d8b.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/003dda2e-ca3f-4e2f-90a7-91ad21760958.jsonl`
