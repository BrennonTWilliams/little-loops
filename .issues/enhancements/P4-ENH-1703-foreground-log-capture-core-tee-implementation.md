---
id: ENH-1703
priority: P4
type: ENH
status: open
parent: ENH-1670
---

# ENH-1703: Foreground log capture — core tee implementation and test wiring

## Summary

Make `run_foreground()` always tee stdout/stderr to `{instance_id}.log`, matching the behaviour of `run_background()`. No flag, no config key — capture is unconditional for all foreground runs, giving operators a recoverable artifact without sacrificing the live-terminal experience.

Absorbs ENH-1682 (cancelled): adds ANSI-stripping on log writes so the file is plain-text / grep-friendly while the terminal stream is left unchanged.

## Parent Issue

Decomposed from ENH-1670: Automatic log capture parity for foreground runs

## Design Decision

The original opt-in design (`--log`/`--capture` flag, `capture_foreground_logs` config key) was dropped. Background runs always capture; foreground parity means always-on as well. Users who want manual control already have `tee(1)`. The flag adds friction and a default that defeats the purpose.

## Proposed Solution

### Implementation steps

1. **`run_foreground()` tee logic** — In `scripts/little_loops/cli/loop/_helpers.py` `run_foreground()` (line 640), add `instance_id: str` and `log_path: Path | None = None` parameters. Resolve the log file path as `log_path or running_dir / f"{instance_id}.log"`, matching `run_background()`'s convention at line 560. Implement tee via `subprocess.PIPE` on child stdout/stderr + a line-by-line loop writing each line to both `sys.stdout` and the open log file handle — modeled on `DefaultActionRunner.run()` at `scripts/little_loops/fsm/runners.py:125`. Add a `_strip_ansi(text: str) -> str` helper (regex `re.sub(r'\x1b\[[0-9;]*[mABCDEFGHJKSTfhilmnprsu]', '', text)`) and apply it before each write to the log file — terminal stream is written as-is.

2. **Flag propagation in `run.py`** — In `scripts/little_loops/cli/loop/run.py` `cmd_run()`, pass `instance_id` into `run_foreground()` (already in scope at line 356).

3. **Flag propagation in `lifecycle.py`** — In `scripts/little_loops/cli/loop/lifecycle.py` `cmd_resume()` (line 426), thread `instance_id` through to `run_foreground(mode="resume")` the same way.

### Test infrastructure updates

4. **Regression guard update** — `test_cli_loop_lifecycle.py:TestCmdStatusLogFile.test_status_foreground_run_no_pid_no_log` (line 1103) was the "default off" guard. With always-on capture, update it to assert a log file IS created for foreground runs (rename or replace the test as appropriate).

5. **New feature tests** — In `scripts/tests/test_ll_loop_display.py`, add a new class `TestRunForegroundCapture` with:
   - Log file is always written for foreground runs
   - Log file contains no ANSI escape sequences (`\x1b[` must not appear)
   - Terminal output is not suppressed (streams are independent)

6. **Background forwarding tests** — In `scripts/tests/test_cli_loop_background.py`, verify that `run_background()` re-exec'd foreground children inherit `instance_id` so the log path is consistent.

### Do NOT touch

- `lifecycle.py:_format_log_label()` (line 33) — already checks `.log` existence; will automatically render `Log: <path>` for foreground runs once a log file exists — no change needed.

## Acceptance Criteria

- `ll-loop run <loop>` always produces `{instance_id}.log` in the running dir with full stdout/stderr captured
- Log file contains no ANSI escape sequences (plain text, grep-friendly)
- Terminal output is identical to a run before this change (no suppression, no ANSI loss)
- `ll-loop resume <id>` also produces a log file
- All existing tests pass (regression guard test updated, not deleted)

## Files to Modify

- `scripts/little_loops/cli/loop/_helpers.py` — tee logic in `run_foreground()`
- `scripts/little_loops/cli/loop/run.py` — `instance_id` propagation
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` propagation
- `scripts/tests/test_ll_loop_display.py` — new `TestRunForegroundCapture`
- `scripts/tests/test_cli_loop_lifecycle.py` — update regression guard test
- `scripts/tests/test_cli_loop_background.py` — forwarding verification

## Related Issues

- ENH-1682 (cancelled) — absorbed into this issue; ANSI-strip addition above
- ENH-1704 — docs-only follow-up (depends on this issue)

## Session Log
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49c875d1-35f0-42f5-a121-41c0c7663183.jsonl`
- Design revised to always-on (dropped flag/config) - 2026-05-26
