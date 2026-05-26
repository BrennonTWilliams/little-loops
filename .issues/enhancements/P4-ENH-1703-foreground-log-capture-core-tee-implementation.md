---
id: ENH-1703
priority: P4
type: ENH
status: open
parent: ENH-1670
---

# ENH-1703: Foreground log capture — core tee implementation and test wiring

## Summary

Implement the tee logic that allows `run_foreground()` to optionally write stdout/stderr to `{instance_id}.log` alongside the terminal, controlled by a `--log`/`--capture` CLI flag and a `loop.capture_foreground_logs` config key. Includes all wiring (flag registration, config field, arg propagation) and all test infrastructure updates required to keep the test suite green.

Absorbs ENH-1682 (cancelled): adds ANSI-stripping on log writes and an optional `--log-to <path>` override for users who want a predictable log location (e.g. `/tmp/loop.log` for `tail -f`).

## Parent Issue

Decomposed from ENH-1670: Optional log capture for foreground runs (tee to `{instance_id}.log`)

## Proposed Solution

### Implementation steps (from parent ENH-1670)

1. **Flag registration** — In `scripts/little_loops/cli/loop/__init__.py` `main_loop()` (lines 103–219):
   - Add `run_parser.add_argument("--log", "--capture", action="store_true", help="Tee foreground output to {instance_id}.log")` and the same to `resume_parser`.
   - Add `run_parser.add_argument("--log-to", metavar="PATH", help="Tee foreground output to this path (implies --log); ANSI codes stripped")` and the same to `resume_parser`. When `--log-to` is set, capture is implicitly enabled regardless of `--log`.

2. **Flag propagation in `run.py`** — In `scripts/little_loops/cli/loop/run.py` `cmd_run()`, pass `instance_id` and the log flag into `run_foreground()` (both already in scope before the call at line 356).

3. **Flag propagation in `lifecycle.py`** — In `scripts/little_loops/cli/loop/lifecycle.py` `cmd_resume()` (line 426), thread the flag through to `run_foreground(mode="resume")` the same way.

4. **Config field** — In `scripts/little_loops/config/features.py` `LoopsConfig`, add `capture_foreground_logs: bool = False` dataclass field and `capture_foreground_logs=data.get("capture_foreground_logs", False)` in `from_dict()`. Do NOT use `feature_enabled()` — that helper is for hook handlers only; `BRConfig.loops.*` attributes are plain Python dataclass fields.

5. **Namespace fix** — In `scripts/little_loops/cli/loop/next_loop.py` `cmd_next_loop()`, add `log=False, log_to=None` to the hardcoded `argparse.Namespace` (~lines 306–331) so `cmd_run()` can read `args.log` / `args.log_to` without `AttributeError`.

6. **`run_foreground()` tee logic** — In `scripts/little_loops/cli/loop/_helpers.py` `run_foreground()` (line 640), add `capture_log: bool = False` and `log_path: str | None = None` parameters. Resolve the log file path as `Path(log_path) if log_path else running_dir / f"{instance_id}.log"`, matching `run_background()`'s convention at line 560. Implement tee via `subprocess.PIPE` on child stdout/stderr + a line-by-line loop writing each line to both `sys.stdout` and the open log file handle — modeled on `DefaultActionRunner.run()` at `scripts/little_loops/fsm/runners.py:125`. Add a `_strip_ansi(text: str) -> str` helper (regex `re.sub(r'\x1b\[[0-9;]*[mABCDEFGHJKSTfhilmnprsu]', '', text)`) and apply it before each write to the log file — terminal stream is written as-is (no ANSI loss), log file is plain text for `tail -f` / grep.

7. **Background flag forwarding** — In `run_background()` flag-forwarding block (`_helpers.py` lines 576–619), add `if getattr(args, "log", False): cmd.append("--log")` and `if getattr(args, "log_to", None): cmd.extend(["--log-to", args.log_to])` so re-exec'd foreground children also capture.

### Test infrastructure updates (must accompany steps above)

8. **Existing `_make_args()` helpers** — Add `log=False` to all helpers and inline `argparse.Namespace(...)` calls that will receive `args.log` from `cmd_run()` / `run_foreground()`:
   - `test_ll_loop_display.py`: `TestDisplayProgressEvents._make_args()` (line 1648), `TestRunForegroundExitCodes._make_args()` (line 2600), `TestRunForegroundResumeMode._make_args()` (line 2661), `TestFollowMode._args()` (line 3902), plus ~15 inline `argparse.Namespace(...)` calls in individual test methods
   - `test_cli_loop_queue.py`: module-level `_make_args()` (line 12) — add `"log": False`
   - `test_cli_loop_worktree.py`: class-level `_make_args()` (line 562) — add `"log": False`
   - `test_cli_loop_lifecycle.py`: `TestCmdRunHandoffThreshold._make_args()` (line 841) and `TestCmdRunYAMLConfigOverrides._make_args()` (line 932) — add `"log": False`

9. **Config tests** — In `scripts/tests/test_config.py`:
   - `TestLoopsConfig.test_from_dict_with_all_fields` (line 565) — add `"capture_foreground_logs": True` to data dict and assertion
   - `TestLoopsConfig.test_from_dict_with_defaults` (line 577) — add `assert config.capture_foreground_logs is False`

10. **Config schema sentinel test** — In `scripts/tests/test_config_schema.py`, add a sentinel test asserting `loops.capture_foreground_logs` exists in schema with type boolean, following the `test_loops_glyphs_parallel_in_schema` pattern.

11. **New feature tests** — In `scripts/tests/test_cli_loop_background.py`, modeled on `TestRunBackground.test_creates_log_file()` (line 182):
    - Assert `--log` produces `{instance_id}.log` with captured content
    - Assert `--log-to /tmp/x.log` writes to the specified path (not `{instance_id}.log`)
    - Assert log file contains no ANSI escape sequences (`\x1b[` must not appear)
    - Assert terminal output is not suppressed when `--log` is on
    - Assert no file is written without the flag
    - Add test in `scripts/tests/test_cli_loop_lifecycle.py` asserting `cmd_resume()` forwards `log` and `log_to` flags to `run_foreground()`
    - Add test in `scripts/tests/test_cli_loop_background.py` pairs `test_forwards_log_flag` / `test_forwards_log_to_flag` / `test_log_flag_not_forwarded_when_false` following the `test_forwards_verbose` pattern (line ~280)
    - Write new class `TestRunForegroundCapture` in `scripts/tests/test_ll_loop_display.py` with: log file written when `log=True`, custom path used when `log_to` set, ANSI stripped in log file, terminal unaffected, not written when `log=False`

### Do NOT touch

- `test_cli_loop_lifecycle.py:TestCmdStatusLogFile.test_status_foreground_run_no_pid_no_log` (line 1103) — this is the "default off" regression guard; leave unchanged.
- `lifecycle.py:_format_log_label()` (line 33) — already checks `.log` existence; will automatically render `Log: <path>` for foreground runs once a log file exists — no change needed.

## Acceptance Criteria

- `ll-loop run <loop> --log` produces `{instance_id}.log` in the running dir with full stdout/stderr captured
- `ll-loop run <loop> --log-to /tmp/loop.log` writes to the specified path instead; `--log` is not required alongside it
- Log file contains no ANSI escape sequences (plain text, grep-friendly)
- Terminal output is identical to a run without `--log` (no suppression, no ANSI loss)
- `ll-loop run <loop>` without `--log` or `--log-to` produces no `.log` file (default-off contract)
- `config.loops.capture_foreground_logs: true` in `.ll/ll-config.json` activates capture; CLI flag overrides config
- All existing tests pass without modification beyond the explicit list above
- `ll-loop resume <id> --log` and `ll-loop resume <id> --log-to <path>` also capture

## Files to Modify

- `scripts/little_loops/cli/loop/_helpers.py` — tee logic in `run_foreground()`, flag forwarding in `run_background()`
- `scripts/little_loops/cli/loop/__init__.py` — flag registration
- `scripts/little_loops/cli/loop/run.py` — flag propagation
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` propagation
- `scripts/little_loops/cli/loop/next_loop.py` — Namespace fix
- `scripts/little_loops/config/features.py` — `capture_foreground_logs` field
- `scripts/tests/test_ll_loop_display.py` — 4 helpers + ~15 inline + new `TestRunForegroundCapture`
- `scripts/tests/test_cli_loop_queue.py` — `_make_args()` update
- `scripts/tests/test_cli_loop_worktree.py` — `_make_args()` update
- `scripts/tests/test_cli_loop_lifecycle.py` — 2 helpers + new resume test
- `scripts/tests/test_cli_loop_background.py` — new log capture tests + forward flag tests
- `scripts/tests/test_config.py` — `TestLoopsConfig` updates
- `scripts/tests/test_config_schema.py` — sentinel test

## Related Issues

- ENH-1682 (cancelled) — absorbed into this issue; see ANSI-strip and `--log-to` additions above

## Session Log
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49c875d1-35f0-42f5-a121-41c0c7663183.jsonl`
