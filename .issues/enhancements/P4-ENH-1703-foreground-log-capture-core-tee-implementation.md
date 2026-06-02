---
id: ENH-1703
priority: P4
type: ENH
status: done
completed_at: 2026-05-27T21:13:47Z
parent: ENH-1670
decision_needed: false
confidence_score: 95
outcome_confidence: 64
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 0
---

# ENH-1703: Foreground log capture — core tee implementation and test wiring

## Summary

Make `run_foreground()` always tee stdout/stderr to `{instance_id}.log`, matching the behaviour of `run_background()`. No flag, no config key — capture is unconditional for all foreground runs, giving operators a recoverable artifact without sacrificing the live-terminal experience.

Absorbs ENH-1682 (cancelled): adds ANSI-stripping on log writes so the file is plain-text / grep-friendly while the terminal stream is left unchanged.

## Current Behavior

`run_foreground()` does not write any log file. When `ll-loop run <loop>` or `ll-loop resume <id>` runs in foreground mode, output streams to the terminal only — no file artifact is produced. Only `run_background()` captures a `{instance_id}.log` file. Operators have no recoverable artifact from foreground runs.

## Expected Behavior

`run_foreground()` always tees stdout/stderr to `{running_dir}/{instance_id}.log` while simultaneously streaming to the terminal unchanged (no ANSI loss, no suppression). The log file contains plain text (ANSI sequences stripped). Both `ll-loop run` and `ll-loop resume` produce a log file. The `ll-loop status` display automatically renders `Log: <path>` for foreground runs.

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

- `lifecycle.py:_format_log_label()` (line 39) — already checks `.log` existence; will automatically render `Log: <path>` for foreground runs once a log file exists — no change needed

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified line numbers (as of research pass):**
- `run_foreground()` is at line 653 in `_helpers.py` (issue text says 640)
- `run_background()` is at line 553 in `_helpers.py` (issue text says 560)
- `run_foreground()` call in `cmd_run()` is at line 385 in `run.py` (issue text says 356); `instance_id` is a two-step assignment — `_pre_instance_id = _make_instance_id(loop_name)` at line 157, aliased to `instance_id = _pre_instance_id` at line 244
- `run_foreground()` call in `cmd_resume()` is at line 503 in `lifecycle.py` (issue text says 426)
- `_format_log_label()` is at line 39 in `lifecycle.py` (issue text says 33)

**`_strip_ansi()` already exists in two places — avoid duplication:**
- `scripts/little_loops/cli/loop/info.py:259` — `_ANSI_RE = re.compile(r"\033\[[0-9;]*m")` + `_strip_ansi()`
- `scripts/little_loops/cli/issues/show.py:281` — identical narrower regex
- Both existing functions cover only SGR/color (`m`) sequences. The new `_helpers.py` version must use the **broader regex** specified in the issue (`\x1b\[[0-9;]*[mABCDEFGHJKSTfhilmnprsu]`) to cover cursor and erase sequences. Use a module-level `_ANSI_RE` compiled once to avoid per-call overhead.

**Critical: tee mechanism — `run_foreground()` uses `print()`, not subprocess:**
`run_foreground()` writes all output via `print()` calls in the `display_progress` inner function (lines 725–982) and the completion block (~lines 1043–1065). It does **not** spawn a subprocess internally. The `subprocess.PIPE` pattern referenced in the Proposed Solution describes `DefaultActionRunner.run()` (action-level subprocess execution) and is not directly applicable. The tee for `run_foreground()` must be implemented as a `sys.stdout`/`sys.stderr` wrapper — a `_TeeWriter` class that writes to both the original stream and the log file (with ANSI stripping on log writes), installed at the start of the function body and restored via `try/finally`.

**Background-spawned foreground runs — guard against double writes:**
When `run_background()` spawns a `--foreground-internal` child, it already redirects the child's `sys.stdout` and `sys.stderr` to the log file via `Popen(..., stdout=log_fh, stderr=log_fh)`. Inside that child, `run_foreground()` would receive `instance_id` from `args.instance_id`. Installing a tee unconditionally would cause double writes to the same log file. Guard the tee setup:
```python
if not getattr(args, "foreground_internal", False):
    # install sys.stdout/_TeeWriter here
```

**Test class reference:**
- `TestRunForegroundExitCodes` at `test_ll_loop_display.py:2663` and `TestRunForegroundResumeMode` at line 2724 are the templates for the new `TestRunForegroundCapture` — reuse the same `_make_args()` / inner `_Executor` fixture pattern
- `MockExecutor` at line 34 and `make_test_fsm()` at line 84 are module-level helpers available for fixtures
- Inline `ansi_re = re.compile(r"\x1b\[[0-9;]*[mABCDEFGHJKSTfhilmnprsu]")` per test method rather than using the scattered instance-method variants found elsewhere in the file.

## Scope Boundaries

- Documentation updates deferred to ENH-1704 (docs-only follow-up)
- No new flag, config key, or opt-out mechanism — capture is unconditional
- No changes to `_format_log_label()` — automatically renders `Log: <path>` once a log file exists
- No changes to `next_loop.py` — already uses `instance_id=None, foreground_internal=False` defaults
- Does not apply to background-spawned foreground children (`--foreground-internal`) — those already write via Popen redirect

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

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py` — dispatches to `cmd_run()` (line 539) and `cmd_resume()` (line 549); already registers `--instance-id` and `--foreground-internal` hidden args for both subcommands — no change needed
- `scripts/little_loops/cli/loop/next_loop.py` — `cmd_next_loop()` (line 332) calls `cmd_run()` with a hardcoded `argparse.Namespace(instance_id=None, foreground_internal=False, ...)`; the tee guard correctly defaults to skipping (`foreground_internal=False`) and tee activates when `instance_id is not None` — **no change needed**, but verify guard handles `None` instance_id safely [Agent 1 / Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_ (ENH-1704 is the designated doc follow-up for these files)
- `docs/reference/CLI.md` — states "`log_file` is `null` for foreground runs (they never write a `.log` file)" in the `ll-loop status --json` description, and lists "Log: (foreground run — output went to terminal)" as a label in the status output section; both become inaccurate after ENH-1703 [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — monitoring section comment reads `# log_file is null for foreground runs` alongside a `tail -f` one-liner; needs updating to reflect that foreground runs now produce `{instance_id}.log` [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py` — `TestDisplayProgressEvents` (line 1645), `TestRunForegroundExitCodes` (line 2663), `TestRunForegroundResumeMode` (line 2724) each call `run_foreground(executor, fsm, args)` directly without `instance_id`; ~55 call sites across these classes will break with `TypeError` if `instance_id` is added as a required argument — see Wiring Phase constraint #7 [Agent 3 finding]
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdStatusJson.test_status_json_log_not_found` asserts `data["log_file"] is None`; review whether this fixture constructs a real running dir without `.pid` that ENH-1703 would now populate with a `.log`; update if affected [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These constraints were identified by wiring analysis and must be respected in the implementation:_

7. **`instance_id` MUST default to `None`** — declare as `instance_id: str | None = None` in `run_foreground()`. Approximately 55 direct call sites in `test_ll_loop_display.py` pass `(executor, fsm, args)` with no `instance_id`; a required parameter breaks them all. Tee logic should be guarded: `if instance_id is not None and not getattr(args, "foreground_internal", False): ...`
8. **`test_status_json_log_not_found` in `TestCmdStatusJson`** — review the mock fixture for `foreground_internal` state; update the assertion if the mock state can trigger log file creation.
9. **`next_loop.py` hardcoded Namespace** — already has `instance_id=None, foreground_internal=False`; no change required, but verify after the signature change is in place.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-27_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- **Broad call surface (Pattern A, ~65 call sites)** — `run_foreground()` is called in ~55 test methods across `test_ll_loop_display.py` plus 2 production call sites (`run.py`, `lifecycle.py`). The backward-compatible `instance_id: str | None = None` default (wiring constraint #7) is the critical safeguard — any deviation from this exact default would break all 55 test call sites with `TypeError`. Risk is managed but the wide surface demands careful implementation.

## Impact

- **Priority**: P4 — Quality-of-life; operators gain a recoverable artifact without config overhead
- **Effort**: Medium — `_TeeWriter` wrapper, signature change with default, ~55 test call sites verified safe by backward-compatible default
- **Risk**: Low — `instance_id: str | None = None` default preserves all existing call sites; tee guarded by `instance_id is not None` and `foreground_internal` flag
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `loop-runner`, `logging`, `testing`

## Related Issues

- ENH-1682 (cancelled) — absorbed into this issue; ANSI-strip addition above
- ENH-1704 — docs-only follow-up (depends on this issue)

**Done** | Created: 2026-05-25 | Priority: P4

## Resolution

Implemented always-on foreground log capture via `_TeeWriter` in `_helpers.py`:

- Added `_ANSI_RE` (broad regex covering all escape sequences) and `_TeeWriter` class to `_helpers.py`
- Added `instance_id: str | None = None` and `running_dir: Path | None = None` params to `run_foreground()`; tee guarded by `instance_id is not None and not foreground_internal`
- Wrapped function body in outer `try/finally` to guarantee `sys.stdout`/`sys.stderr` restoration and log file close
- Propagated `instance_id` and `running_dir` in both `run.py` (`cmd_run`) and `lifecycle.py` (`cmd_resume`)
- Updated `test_status_foreground_run_no_pid_no_log` docstring to reflect it is now a legacy-fallback guard
- Added `TestRunForegroundCapture` (5 tests) in `test_ll_loop_display.py`
- Added `TestRunBackgroundInstanceIdForwarding` (1 test) in `test_cli_loop_background.py`
- All 7877 tests pass; ruff and mypy clean

## Session Log
- `/ll:ready-issue` - 2026-05-27T20:58:10 - `433b1b9b-ce33-437c-9c1f-0ee0bb7c8b8a.jsonl`
- `/ll:confidence-check` - 2026-05-27T21:15:00 - `e3786d8e-e9c2-4081-b930-0fcc1bd2c80f.jsonl`
- `/ll:wire-issue` - 2026-05-27T20:51:24 - `72d039de-33dc-4db3-ac4e-00b6406c2c7f.jsonl`
- `/ll:refine-issue` - 2026-05-27T20:45:55 - `da4cdbba-d276-49c6-8178-d0634377bace.jsonl`
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `49c875d1-35f0-42f5-a121-41c0c7663183.jsonl`
- Design revised to always-on (dropped flag/config) - 2026-05-26
- `/ll:manage-issue` - 2026-05-27T21:13:47Z - `433b1b9b-ce33-437c-9c1f-0ee0bb7c8b8a.jsonl`
