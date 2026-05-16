---
captured_at: "2026-05-03T00:00:00Z"
completed_at: "2026-05-03T00:00:00Z"
discovered_date: 2026-05-03
discovered_by: user-report
status: done
---

# BUG-1521: `ll-loop run --background` drops the positional `input` argument, causing "Missing required context variable" on spawn

## Summary

When `ll-loop run <loop> <input> --background` is invoked, the background subprocess starts without the positional `input` value. The re-exec command built in `run_background()` includes the loop name and all option flags, but never appends `args.input`. The spawned process runs its own `cmd_run()` with `args.input = None`, so the FSM context key is never populated. Pre-run validation finds the required context variable missing, logs the error, and exits 1 before the loop executes a single state.

Observed in an external project:
```
ll-loop run recursive-refine ENH-571 -v -b
# Loop appears to start...
ll-loop status recursive-refine
# Last event: Missing required context variable: 'input'. Run with: ll-loop run recursive-refine --context input=VALUE
```

## Current Behavior

`run_background()` (`scripts/little_loops/cli/loop/_helpers.py:254`) builds:
```
python -m little_loops.cli.loop run <loop_name> --foreground-internal [flags...]
```
The positional `input` token is never appended, so the background process receives no input value.

## Expected Behavior

The re-exec command includes the positional input value immediately after the loop name when `args.input` is set:
```
python -m little_loops.cli.loop run <loop_name> <input_value> --foreground-internal [flags...]
```

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Function**: `run_background()` (line 232)
- **Cause**: The function explicitly forwards every named arg (`max_iterations`, `no_llm`, `llm_model`, `verbose`, `context`, `program_md`, `delay`, `handoff_threshold`, `context_limit`) but has no code path for `getattr(args, "input", None)`.

The pre-run validation (`cmd_run()` lines 177-194) runs in the parent process where `args.input` is already set, so it passes; the background subprocess repeats the validation without the value and fails.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `run_background()` command-building block, lines 254–261

## Resolution

Inserted the positional `input` value into the re-exec command right after `loop_name` when set:

```python
# Before:
cmd = [
    sys.executable, "-m", "little_loops.cli.loop",
    subcommand, loop_name, "--foreground-internal",
]

# After:
cmd = [
    sys.executable, "-m", "little_loops.cli.loop",
    subcommand, loop_name,
]
input_val = getattr(args, "input", None)
if input_val is not None:
    cmd.append(input_val)
cmd.append("--foreground-internal")
```

Added two regression tests to `scripts/tests/test_cli_loop_background.py`:
- `TestRunBackground::test_forwards_positional_input` — asserts the value appears in the command immediately after the loop name.
- `TestRunBackground::test_input_not_forwarded_when_none` — asserts nothing is injected between the loop name and the first flag when `input=None`.

## Impact

- **Severity**: High for loops with a required `input` context variable (e.g. `recursive-refine`, any loop using `${context.input}`).
- **Scope**: Every `ll-loop run <loop> <input> --background` invocation. Foreground runs are unaffected.
- **Failure mode**: Silent — the loop appears to start (PID logged, log file created) but exits immediately with an error logged only to `.loops/.running/<name>.log`.

## Session Log

- Manual fix - 2026-05-03T00:00:00Z
