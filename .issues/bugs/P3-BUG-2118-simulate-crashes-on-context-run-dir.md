---
id: BUG-2118
type: BUG
priority: P3
status: done
title: "ll-loop simulate crashes on ${context.run_dir} in init state"
created: 2026-06-13
closed: 2026-06-13
affects: ll-loop simulate
---

## Summary

`ll-loop simulate <loop>` terminates with verdict `error` at the initial state
for any loop that references `${context.run_dir}` in its first action.  The real
runner (`ll-loop run`) injects `run_dir` into `fsm.context` before creating the
executor; the simulator never did, so `InterpolationError` fired immediately.

## Root Cause

`cmd_simulate()` in `scripts/little_loops/cli/loop/testing.py` built the
`FSMExecutor` without first injecting the runner-managed context variable
`run_dir`.  `cmd_run()` in `scripts/little_loops/cli/loop/run.py:162-163` has
always performed this injection, creating a parity gap between the two entry
points.

The `${context.run_dir}` variable is listed in `validation.py:426` as a
`RUNNER_INJECTED` constant precisely because it is expected to be available at
execution time without the loop author declaring it — but only the real runner
honoured that contract.

## Fix

Added runner-managed context injection to `cmd_simulate()` before the executor
is created (`scripts/little_loops/cli/loop/testing.py:214-220`):

```python
# Inject runner-managed context variables so ${context.run_dir} resolves during
# simulation — the real runner does this in run.py before FSMExecutor is created.
if "run_dir" not in fsm.context:
    fsm.context["run_dir"] = str(loops_dir / "runs" / f"{loop_name}-simulate") + "/"
if "input_hash" not in fsm.context and isinstance(fsm.context.get("input"), str):
    import hashlib
    fsm.context["input_hash"] = hashlib.sha256(
        fsm.context["input"].encode()
    ).hexdigest()[:12]
```

The synthetic path uses a `-simulate` suffix so it is clearly distinct from
real run directories and does not collide with concurrent `ll-loop run`
instances.  Loops that declare `run_dir` in their own `context:` block keep
their value via the `if not in` guard.

## Tests

Added `TestCmdSimulateRunDir` class to
`scripts/tests/test_cli_loop_testing.py` with two cases:

- `test_run_dir_injected_when_referenced_in_init_state` — loop that calls
  `mkdir -p ${context.run_dir}` simulates without error
- `test_run_dir_not_overwritten_if_already_in_context` — loop with an explicit
  `run_dir` in its `context:` block retains that value

All 14 tests in the file pass.

## Files Changed

- `scripts/little_loops/cli/loop/testing.py` — inject `run_dir` / `input_hash`
- `scripts/tests/test_cli_loop_testing.py` — `TestCmdSimulateRunDir` regression tests


## Session Log
- `hook:posttooluse-status-done` - 2026-06-13T18:42:10 - `aa68867a-a48d-436c-bfa2-c625e339801a.jsonl`
