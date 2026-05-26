---
captured_at: '2026-05-24T04:52:29Z'
discovered_date: '2026-05-24'
discovered_by: capture-issue
status: done
depends_on:
- BUG-1668
relates_to:
- ENH-1669
- ENH-1667
- ENH-1682
decision_needed: false
confidence_score: 90
outcome_confidence: 66
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
implementation_order_risk: true
size: Very Large
---

# ENH-1670: Optional log capture for foreground runs (tee to `{instance_id}.log`)

## Summary

Background runs persist child stdout/stderr to `{instance_id}.log` via `run_background()`. Foreground runs write nothing to disk — output goes only to the user's terminal. This means foreground runs are unrecoverable for post-hoc inspection once the terminal is closed. Add an optional path that tees foreground output to `{instance_id}.log` as well, giving operators a recoverable artifact without sacrificing the live-terminal experience.

## Motivation

When investigating loop behavior after the fact, the events file (`{instance_id}.events.jsonl`) shows structured state transitions but lacks the free-form stdout that often contains the real explanation (LLM tool output, error tracebacks, debug prints). Background runs already have this — foreground runs should be able to opt in. BUG-1668 makes the `Log:` line honest about run mode, but the underlying gap (no log file for foreground) remains a real ergonomic loss.

## Current Behavior

- `run_background()` at `scripts/little_loops/cli/loop/_helpers.py:540, 589` redirects child stdout/stderr to `{instance_id}.log` via `subprocess.Popen(..., stdout=log_fh, stderr=log_fh, ...)`.
- `run_foreground()` at `_helpers.py:608+` does not redirect; output streams to the controlling terminal only.
- Once the terminal closes or scrollback rolls off, the run output is gone.

## Expected Behavior

A new flag (e.g. `--log` or `--capture`) or a config option causes `run_foreground()` to additionally tee stdout/stderr to `{instance_id}.log` while still streaming to the terminal. Default off (to preserve current behavior and not surprise users with new disk writes), but easy to enable for diagnostic runs.

## Proposed Solution

In `run_foreground()`, when `--log`/`--capture` is set:

1. Open `{instance_id}.log` for writing in the same way `run_background()` does.
2. Use a tee approach — either spawn a subprocess with stdout/stderr piped through a Python tee reader, or use `subprocess.run(..., stdout=subprocess.PIPE)` with the parent writing each line to both `sys.stdout` and the log file.

The Python-side tee is preferable because the existing `run_foreground()` already drives the child synchronously; adding a line-by-line forwarder is a minimal extension.

Once the file exists, BUG-1668's three-way `Log:` label naturally degrades to the existing `Log: <path>` case for these runs.

### Flag vs config

Two reasonable shapes:

- CLI flag: `ll-loop run <loop> --log` — explicit per-invocation opt-in.
- Config: `.ll/ll-config.json` → `loop.capture_foreground_logs: true` — persistent default.

Recommend both, with the flag overriding the config value when present.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/_helpers.py` — `run_foreground()` (~line 608+); add tee logic guarded by the new flag/config.
- `scripts/little_loops/cli/loop/__init__.py` — register the new `--log`/`--capture` flag on the `run` subcommand.
- `scripts/little_loops/cli/loop/run.py` — propagate the flag from argparse into `run_foreground()`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/next_loop.py` — add `log=False` to the hardcoded `argparse.Namespace` in `cmd_next_loop()` (~lines 306–331) so `cmd_run()` can read `args.log` without `AttributeError` [Agent 1 + 2 finding]
- `scripts/little_loops/config/features.py` — add `capture_foreground_logs: bool = False` dataclass field to `LoopsConfig` and `capture_foreground_logs=data.get("capture_foreground_logs", False)` to `LoopsConfig.from_dict()`; **do NOT use `feature_enabled()`** — that helper is for hook handlers only; `BRConfig.loops.*` attributes are plain Python dataclass fields [Agent 2 finding]

### Dependent Files (Callers/Importers)

- BUG-1668's `Log:` label helper — once a foreground run has a `.log`, the label should render as `Log: <path>` (no special case needed; the absence test already handles it).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/next_loop.py` — `cmd_next_loop()` constructs a hardcoded `argparse.Namespace` (~lines 306–331) that is passed directly to `cmd_run()`; every new flag on `run_parser` must be added here manually (e.g. `log=False`) or `cmd_run()` will raise `AttributeError` when it reads `args.log` [Agent 1 + 2 finding]

### Similar Patterns

- `run_background()` at `_helpers.py:540, 589` — direct redirect via `subprocess.Popen(..., stdout=log_fh, stderr=log_fh, ...)`.
- Python `tee`-like helpers in the standard library are rare; the codebase may need a small `_tee_stream(src, *dsts)` helper.

### Tests

- `scripts/tests/test_cli_loop_run.py` (or equivalent foreground-run test file) — assert that `--log` produces a `.log` file with captured content; assert that without the flag, no file is written.
- Verify that terminal output is not suppressed when `--log` is on.

_Wiring pass added by `/ll:wire-issue`:_

**Note: `test_cli_loop_run.py` does not exist.** Foreground-run tests live across four files:
- `scripts/tests/test_ll_loop_display.py` — primary `run_foreground()` call site (40+ invocations); write new class `TestRunForegroundCapture` here with: log file written when `log=True`, not written when `log=False`, terminal output not suppressed [Agent 3 finding]
- `scripts/tests/test_cli_loop_lifecycle.py` — covers `cmd_run()` and `cmd_resume()` directly; add test asserting `cmd_resume()` forwards `log` flag to `run_foreground()` [Agent 3 finding]
- `scripts/tests/test_cli_loop_background.py` — add new pair `test_forwards_log_flag` / `test_log_flag_not_forwarded_when_false` following the `test_forwards_verbose` pattern (line ~280) [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — add sentinel test asserting `loops.capture_foreground_logs` exists in schema with type boolean, following `test_loops_glyphs_parallel_in_schema` pattern [Agent 2 finding]

**Existing tests to update** (will break or silently pass incorrectly if `args.log` is read without `getattr` default):
- `test_ll_loop_display.py:TestDisplayProgressEvents._make_args()` (line 1648) — add `log=False` [Agent 3]
- `test_ll_loop_display.py:TestRunForegroundExitCodes._make_args()` (line 2600) — add `log=False` [Agent 3]
- `test_ll_loop_display.py:TestRunForegroundResumeMode._make_args()` (line 2661) — add `log=False` [Agent 3]
- `test_ll_loop_display.py:TestFollowMode._args()` (line 3902) — add `log=False` [Agent 3]
- `test_ll_loop_display.py` — ~15 inline `argparse.Namespace(...)` in individual test methods — add `log=False` [Agent 3]
- `test_cli_loop_queue.py:_make_args()` module-level (line 12) — add `"log": False` [Agent 3]
- `test_cli_loop_worktree.py:_make_args()` class-level (line 562) — add `"log": False` [Agent 3]
- `test_cli_loop_lifecycle.py:TestCmdRunHandoffThreshold._make_args()` (line 841) — add `"log": False` [Agent 3]
- `test_cli_loop_lifecycle.py:TestCmdRunYAMLConfigOverrides._make_args()` (line 932) — add `"log": False` [Agent 3]
- `test_config.py:TestLoopsConfig.test_from_dict_with_all_fields` (line 565) — add `"capture_foreground_logs": True` to data dict and assertion [Agent 2 + 3]
- `test_config.py:TestLoopsConfig.test_from_dict_with_defaults` (line 577) — add `assert config.capture_foreground_logs is False` [Agent 2 + 3]

**Leave unchanged** (regression guard):
- `test_cli_loop_lifecycle.py:TestCmdStatusLogFile.test_status_foreground_run_no_pid_no_log` (line 1103) — already asserts no log file without `--log`; this is the "default off" contract guard [Agent 3]

### Documentation

- `docs/reference/CLI.md` — document the new `--log`/`--capture` flag on `ll-loop run`.
- `docs/guides/LOOPS_GUIDE.md` — note the option in the monitoring/debugging section.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `### loops` table (line ~479) needs a new row for `capture_foreground_logs` (boolean, default false); also update the Full Configuration Example block (line ~159) to include the key [Agent 1 + 2 finding]

### Configuration

- `config-schema.json` — add `loop.capture_foreground_logs` (boolean, default false) if going with the config-knob approach.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Confirmed / corrected line numbers:**
- `_make_instance_id()` — `_helpers.py:535`
- `run_background()` — `_helpers.py:540`; log file open + Popen at lines 621–628
- `run_foreground()` — `_helpers.py:640` (not ~608 as noted in issue)
- `cmd_run()` dispatch — `run.py:198–205`; `instance_id` set at lines 213–216; `run_foreground()` called at line 356
- `cmd_resume()` — `lifecycle.py:426` — also calls `run_foreground(mode="resume")`; **needs the same flag**
- `_format_log_label()` — `lifecycle.py:33` — already checks `running_dir / f"{stem}.log"` existence; will automatically render `Log: <path>` for foreground runs once a log file exists — **no change needed here**

**`instance_id` availability:** Already in scope at `cmd_run()` lines 213–216 for all foreground runs, but **not currently passed to `run_foreground()`**. `run_foreground()` will need a new `capture_log: bool = False` parameter and the log path constructed as `running_dir / f"{instance_id}.log"` — matching `run_background()`'s convention exactly.

**No existing tee helper.** The codebase has no `TeeStream` or multi-sink writer class. The model to follow is the callback-based dual-sink in `DefaultActionRunner.run()` at `scripts/little_loops/fsm/runners.py:125`:
```python
for line in process.stdout:
    output_chunks.append(line)       # sink 1: memory/file
    if on_output_line:
        on_output_line(line.rstrip()) # sink 2: caller-controlled
```
Implement tee via `subprocess.PIPE` on the child's stdout/stderr + a line-by-line loop writing each line to both `sys.stdout` and the log file handle.

**Flag forwarding in `run_background()`**: `run_background()` re-execs itself as `ll-loop run <loop> --foreground-internal --instance-id <id>`. All existing boolean flags follow the pattern at lines 576–619 (`getattr(args, "attr", False)` → `cmd.append("--flag")`). The new `--log` flag must be added here so background-launched foreground children also receive it when the user's intent was to capture.

**Correct test file:** `scripts/tests/test_cli_loop_background.py` — `TestRunBackground.test_creates_log_file()` at line 182 is the existing model for log file creation assertions.

**Config reading pattern:** `BRConfig` (from `scripts/little_loops/config/core.py`) is loaded in `cmd_run()` at `run.py:165`. Boolean config flags use `feature_enabled()` from `scripts/little_loops/config/features.py:13`. Use `BRConfig(Path.cwd()).loops` to read the loops config section for `capture_foreground_logs`.

**ENH-1682 overlap:** `P4-ENH-1682` proposes `--log-to <file>` with ANSI-stripping. Coordinate on flag naming (`--log` vs `--log-to`) and whether a single flag covers both use cases before implementing.

## Implementation Steps

1. In `__init__.py` `main_loop()` lines 103–219, add `run_parser.add_argument("--log", "--capture", action="store_true", help="Tee foreground output to {instance_id}.log")` following the existing `store_true` pattern. Add the same to `resume_parser`.
2. In `run.py` `cmd_run()`, pass `instance_id` and the log flag into `run_foreground()` (both already in scope before the call at line 356).
3. In `lifecycle.py` `cmd_resume()` at line 426, thread the flag through to `run_foreground(mode="resume")` the same way.
4. Add `capture_log: bool = False` parameter to `run_foreground()` at `_helpers.py:640`. Construct `log_file = running_dir / f"{instance_id}.log"` matching `run_background()`'s convention at line 560.
5. Implement the tee loop modeled on `DefaultActionRunner.run()` at `runners.py:125`: use `subprocess.PIPE`, iterate lines, write each to both `sys.stdout` and the open log file handle.
6. In `run_background()` flag-forwarding block (lines 576–619), add `if getattr(args, "log", False): cmd.append("--log")` so re-exec'd foreground children also capture.
7. Add tests in `test_cli_loop_background.py` modeled on `TestRunBackground.test_creates_log_file()` (line 182): assert `--log` produces `{instance_id}.log` with captured content; assert terminal output is not suppressed; assert no file is written without the flag.
8. Add `loop.capture_foreground_logs` boolean to `config-schema.json`; wire via `BRConfig(Path.cwd()).loops` in `cmd_run()`.
9. Document the flag in `docs/reference/CLI.md` and `docs/guides/LOOPS_GUIDE.md`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. In `scripts/little_loops/config/features.py` `LoopsConfig`, add `capture_foreground_logs: bool = False` dataclass field and `capture_foreground_logs=data.get("capture_foreground_logs", False)` in `from_dict()` — this is how all `BRConfig.loops.*` booleans are wired, NOT via `feature_enabled()`
11. In `scripts/little_loops/cli/loop/next_loop.py` `cmd_next_loop()`, add `log=False` to the hardcoded `argparse.Namespace` (~lines 306–331) passed to `cmd_run()` — otherwise `cmd_run()` will raise `AttributeError` when reading `args.log`
12. Update all `_make_args()` / `argparse.Namespace` helpers across 5 test files to include `log=False` — critical to do before or alongside the `run_foreground()` change: `test_ll_loop_display.py` (4 helpers + ~15 inline), `test_cli_loop_queue.py` (line 12), `test_cli_loop_worktree.py` (line 562), `test_cli_loop_lifecycle.py` (lines 841, 932)
13. Update `test_config.py:TestLoopsConfig` (lines 565, 577) for the new `capture_foreground_logs` field; add sentinel test to `test_config_schema.py` following `test_loops_glyphs_parallel_in_schema` pattern
14. Add `capture_foreground_logs` row and example to `docs/reference/CONFIGURATION.md` `### loops` section (~line 479) and Full Configuration Example block (~line 159)

## Impact

- **Priority**: P4 — useful but a feature, not a bug fix. Most users won't notice; investigators will appreciate it.
- **Effort**: Small-to-medium — tee logic is straightforward but needs care around line buffering, signal handling, and TTY behavior to avoid breaking interactive runs.
- **Risk**: Medium — touching the foreground I/O path risks regressions in terminal interaction (especially around stderr ordering, ANSI escape passthrough, and signal forwarding).
- **Breaking Change**: No (opt-in only).

## Scope Boundaries

- Foreground runs only. Background runs already capture logs.
- No retroactive capture for already-running foreground instances (not technically recoverable).
- No log rotation, compression, or retention policy — those are separate concerns.

## API/Interface

New CLI flag on `ll-loop run`:

```
ll-loop run <loop> [--log | --capture]
```

- `--log` (alias `--capture`): boolean flag, default false. When set, foreground runs tee stdout/stderr to `{instance_id}.log` in addition to streaming to the terminal.

New config key in `.ll/ll-config.json` (`config-schema.json` addition):

```json
{
  "loop": {
    "capture_foreground_logs": false
  }
}
```

Resolution precedence: CLI flag overrides config when present; otherwise config value applies; otherwise default false.

No changes to existing public function signatures. Internally, `run_foreground()` in `scripts/little_loops/cli/loop/_helpers.py` gains an optional `capture_log: bool = False` keyword parameter.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `cli`, `observability`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-25_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 66/100 → MODERATE

### Outcome Risk Factors
- Wide breadth (17 files across core logic, test infrastructure, config, and docs): most changes are mechanical (test Namespace additions, doc rows, config field) but the tee I/O logic in `_helpers.py` carries medium risk around line buffering, signal handling, and ANSI passthrough in interactive TTY mode
- ENH-1682 naming overlap: `--log` vs `--log-to` flag naming coordination with ENH-1682 should be confirmed before merging; both are P4 so timing may not matter, but flag-name collisions are hard to fix post-ship
- Implement test Namespace updates (`log=False`) before or alongside the `run_foreground()` change — ~17 inline `argparse.Namespace()` calls and 4 `_make_args()` helpers across test files will cause `AttributeError` if the flag is read via `args.log` (without `getattr` fallback) before tests are updated

## Session Log
- `/ll:confidence-check` - 2026-05-25T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/641ff968-cf61-463e-b44e-9e775d9964a0.jsonl`
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49c875d1-35f0-42f5-a121-41c0c7663183.jsonl`
- `/ll:wire-issue` - 2026-05-25T23:22:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/329b3576-60ac-481c-ad67-e1ee496ec829.jsonl`
- `/ll:refine-issue` - 2026-05-25T23:16:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5e693ba-2b17-4a96-a11e-4fb2d161fd62.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:format-issue` - 2026-05-24T05:08:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71b13280-abbe-4af9-a47c-adb27bd0900e.jsonl`
- `/ll:capture-issue` - 2026-05-24T04:52:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f605fdcc-8000-4585-8dc4-835fc0020291.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-25
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1703: Foreground log capture — core tee implementation and test wiring
- ENH-1704: Foreground log capture — config schema and documentation

### Design Revision (2026-05-26)

After decomposition, the opt-in design was reconsidered. Background runs always capture; foreground parity means always-on as well. The `--log`/`--capture` flag and `capture_foreground_logs` config key were dropped in favour of unconditional tee. ENH-1703 and ENH-1704 were updated to reflect this — no flag registration, no config field, no schema entry. ENH-1704 is now docs-only.

---

## Status

**Done** | Created: 2026-05-24 | Priority: P4

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The artifact path for this issue (`{instance_id}.log`) should be verified against ENH-1667's `.loops/runs/<name>/meta-eval.jsonl` convention — both define per-run observability artifacts; align on directory policy before implementing. Also, ENH-1669 (auto-reconcile orphaned state files) addresses the same foreground-run gap from a different angle (state accuracy vs. log capture); these two issues form a cluster with BUG-1668 and should be sequenced together.
