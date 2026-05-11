---
id: ENH-1354
type: ENH
priority: P2

confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-03T19:56:24Z
parent: ENH-1351
---

# ENH-1354: Multi-Instance Loop — instance_id Generation and File Path Scoping

## Summary

Decomposed from ENH-1351. Add `_make_instance_id` helper and thread `instance_id` through all runtime file path construction so each `ll-loop run` produces uniquely namespaced `.pid`, `.log`, `.state.json`, `.events.jsonl`, and `.lock` files. Covers the core plumbing layer: `_helpers.py`, `__init__.py`, `concurrency.py`, `persistence.py`, `run.py`, plus all tests for the path-construction layer.

## Parent Issue

Decomposed from ENH-1351: Multi-Instance Loop Naming with Aggregated Status

## Current Behavior

All runtime files are keyed on loop name: `autodev.pid`, `autodev.state.json`, etc. A second `ll-loop run autodev` queues behind the first (`-q`) rather than running independently.

## Expected Behavior

- `_make_instance_id(loop_name)` returns `f"{loop_name}-{datetime.now().strftime('%Y%m%dT%H%M%S')}"`.
- `run_background` in `_helpers.py` generates `instance_id` and embeds it in the `--foreground-internal` re-exec command.
- `LockManager.acquire` / `release` accept `instance_id: str | None = None`; fall back to `loop_name` when `None`.
- `StatePersistence.__init__` and `PersistentExecutor.__init__` accept `instance_id: str | None = None`; files are stored as `{instance_id or loop_name}.*`.
- `cmd_run` in `run.py` generates `instance_id` (or reads it from `args.instance_id` when foreground-internal), routes it through `LockManager` and `PersistentExecutor`, and scopes the `foreground_pid_file` and `atexit` closure to the instance-ID path.
- All new kwargs default to `None` → backward-compatible with existing behavior.

## Success Metrics

- Two concurrent `ll-loop run autodev` invocations produce distinct runtime files (`autodev-TIMESTAMP1.*` vs `autodev-TIMESTAMP2.*`) with no collision.
- Single-instance behavior unchanged: a lone `ll-loop run foo` behaves identically to before.
- Legacy runtime files without a timestamp suffix (e.g., `foo.pid`) are still recognized and loaded (applies to `StatePersistence` fallback).
- `python -m pytest scripts/tests/test_concurrency.py scripts/tests/test_fsm_persistence.py scripts/tests/test_cli_loop_background.py scripts/tests/test_ll_loop_execution.py` all pass.

## Implementation Steps

1. Add `_make_instance_id(loop_name: str) -> str` to `scripts/little_loops/cli/loop/_helpers.py`; update `run_background` (line 232) to generate `instance_id`, embed it in the `--foreground-internal` re-exec command (line 264 pattern), and use it for `pid_file` (line 250) and `log_file` (line 251) paths.
2. Add hidden `--instance-id` arg (modeled after `--foreground-internal` at `__init__.py:122-124`) to `run_parser` (line 96) and `resume_parser` (line 220) in `scripts/little_loops/cli/loop/__init__.py`.
3. Update `cmd_run` in `scripts/little_loops/cli/loop/run.py:87` to generate `instance_id` (when not foreground-internal) or read it from `args.instance_id`; route through `LockManager.acquire(fsm.name, scope, instance_id=instance_id)` (line 225) and `PersistentExecutor.__init__` (line 332); update PID file path (line 203-205); update `foreground_pid_file` (line 206) and `atexit._cleanup_pid` closure (lines 211-214) to use instance-ID-scoped path.
4. Add `instance_id: str | None = None` kwarg to `LockManager.acquire` (line 98) and `release` (line 143) in `scripts/little_loops/fsm/concurrency.py`; replace `f"{loop_name}.lock"` at lines 131, 149 with `f"{instance_id or loop_name}.lock"`.
5. Add `instance_id: str | None = None` kwarg to `StatePersistence.__init__` (line 196) and `PersistentExecutor.__init__` (line 346) in `scripts/little_loops/fsm/persistence.py`; replace path stems at lines 206-207 with `instance_id or loop_name`; at line 366 forward `instance_id` to the internally-constructed `StatePersistence`; fix `list_running_loops` deduplication at line 590 (strip timestamp suffix before comparing against `known_names` — `pid_file.stem` = `"autodev-TIMESTAMP"` must not produce a spurious "starting" entry when `known_names = {"autodev"}`).
6. Update `scripts/tests/test_cli_loop_background.py` path assertions from `my-loop.pid` / `my-loop.log` (lines 154, 174) to `glob("my-loop*.pid")` / `glob("my-loop*.log")`.
7. Update `scripts/tests/test_fsm_persistence.py` — adapt `TestPersistentExecutor.test_run_creates_state_file` (line 589), `test_run_creates_events_file` (line 601), and `TestAcceptanceCriteria.test_state_saved_after_state_transition` (line 1084) from hard-coded `test-loop.*` path assertions to instance-ID-aware lookups (glob or pass explicit `instance_id` to constructors). Add new `TestUtilityFunctions` cases for `list_running_loops` deduplication where `pid_file.stem` = `"my-loop-TIMESTAMP"` but returned `LoopState.loop_name` = `"my-loop"`.
8. Update `scripts/tests/test_concurrency.py:75-88` lock file path assertions in `TestLockManager` to use instance-ID path.
9. Update `scripts/tests/test_ll_loop_execution.py` — `TestBackgroundMode` tests at lines ~469, ~499, ~543: update bare-stem path assertions (`test-background.pid`, `test-foreground-pid.pid`, `test-state.state.json`, `test-state.events.jsonl`) to use instance-ID-aware globs (e.g., `list(running_dir.glob("test-background-*.pid"))[0]`).
10. Run full test suite for covered files: `python -m pytest scripts/tests/test_concurrency.py scripts/tests/test_fsm_persistence.py scripts/tests/test_cli_loop_background.py scripts/tests/test_ll_loop_execution.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `cmd_resume` in `scripts/little_loops/cli/loop/lifecycle.py` — read `args.instance_id` from the new hidden arg on `resume_parser` (step 2) and pass `instance_id=instance_id` to `PersistentExecutor.__init__` (line 262); update PID path construction to `f"{args.instance_id or loop_name}.pid"` so foreground-internal resumes write to the correct instance-scoped path.
12. Update `scripts/tests/test_cli_loop_lifecycle.py` — confirmed-breaking bare-stem `.pid` and `.log` assertions (lines 135, 164, 196, 412, 545, 585, 610, 626, 910, 929, 966); update to glob patterns or pass explicit `instance_id` to constructors.
13. Update `scripts/tests/test_ll_loop_state.py` — confirmed-breaking bare-stem `.state.json` write fixtures (lines 89, 142, 176, 302, 364); update to pass explicit `instance_id` to `StatePersistence` and write fixture files at the scoped path.
14. Update `scripts/tests/test_ll_loop_integration.py` — confirmed-breaking bare-stem `.state.json` fixtures (lines 315, 330); seed files with instance-ID-qualified names.
15. Add `TestMakeInstanceId` tests for `_make_instance_id(loop_name)` — verify format (`r"^{name}-\d{8}T\d{6}$"`), uniqueness across two successive calls, and loop-name prefix embedding.
16. Add `TestMultiInstanceSameName` in `scripts/tests/test_concurrency.py` — concurrent test verifying two same-loop-name instances with different `instance_id` values do not conflict (follow `threading.Barrier` pattern from lines 333–355).
17. Run expanded test suite: `python -m pytest scripts/tests/test_concurrency.py scripts/tests/test_fsm_persistence.py scripts/tests/test_cli_loop_background.py scripts/tests/test_ll_loop_execution.py scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_ll_loop_state.py scripts/tests/test_ll_loop_integration.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — `_make_instance_id` helper, `run_background` instance scoping
- `scripts/little_loops/cli/loop/__init__.py` — hidden `--instance-id` arg on `run_parser` and `resume_parser`
- `scripts/little_loops/cli/loop/run.py` — generate/consume `instance_id` in `cmd_run`, scope `foreground_pid_file` and `atexit` closure
- `scripts/little_loops/fsm/concurrency.py` — `LockManager.acquire` / `release` (`instance_id` kwarg)
- `scripts/little_loops/fsm/persistence.py` — `StatePersistence.__init__`, `PersistentExecutor.__init__`, `list_running_loops` deduplication fix

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume`: read `args.instance_id` (from the new hidden `--instance-id` arg on `resume_parser`, added in step 2) and forward to `PersistentExecutor.__init__` (line 262); also update bare `{loop_name}.pid` path construction to `{args.instance_id or loop_name}.pid` so the foreground-internal resume writes to the correct instance-scoped path

### Tests to Update
- `scripts/tests/test_cli_loop_background.py` — lines 154, 174: exact path assertions → glob patterns
- `scripts/tests/test_fsm_persistence.py` — lines 589, 601, 1084: hard-coded path assertions; add deduplication test cases
- `scripts/tests/test_concurrency.py` — lines 75-88: lock path assertions
- `scripts/tests/test_ll_loop_execution.py` — lines ~469, ~499, ~543: bare-stem path assertions

### Additional Test Files to Verify (Codebase Research Findings)

_Added by `/ll:refine-issue` — research found bare-stem fixture usage in these files; may require similar glob updates:_

- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdResumeBackground`, `TestCmdStop`, `TestCmdStatus` contain PID file and log file path assertions; verify during test run
- `scripts/tests/test_ll_loop_state.py` — `TestCmdStop` at lines 89, 132, 167 uses bare-stem state file fixtures
- `scripts/tests/test_ll_loop_integration.py` — `TestMainLoopIntegration.test_list_running_shows_status_info()` uses bare-stem state file fixtures
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdHistory.events_file` fixture and `TestCmdStatusJson` tests with `StatePersistence` may have bare-stem dependencies

### Confirmed Test Updates

_Wiring pass added by `/ll:wire-issue` — three of the four "verify" files above were confirmed to contain bare-stem path assertions that WILL break:_

- `scripts/tests/test_cli_loop_lifecycle.py` — **CONFIRMED WILL BREAK**: `TestCmdStop` lines 135, 164, 196 (write `"test-loop.pid"` fixtures); `TestCmdResume` lines 412, 585, 610 (assert `running_dir / "test-loop.pid"`); `TestCmdResumeBackground` lines 545, 626 (foreground-internal PID fixtures); `TestCmdStatusLogFile` lines 910, 929, 966 (bare `.log` path assertions). Update all to glob patterns or pass explicit `instance_id`.
- `scripts/tests/test_ll_loop_state.py` — **CONFIRMED WILL BREAK**: lines 89, 142, 176, 302, 364 — write `running_dir / "test-loop.state.json"` fixtures that `StatePersistence` will no longer find after instance-ID scoping. Update to pass explicit `instance_id` to constructors and write files at the scoped path.
- `scripts/tests/test_ll_loop_integration.py` — **CONFIRMED WILL BREAK**: lines 315, 330 — seed `running_dir / "loop-a.state.json"` and `"loop-b.state.json"` for `test_list_running_shows_status_info`; update to instance-ID-named files.
- `scripts/tests/test_ll_loop_commands.py` — **CONFIRMED SAFE**: no bare-stem path assertions found.

### New Tests to Write

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_background.py` or `scripts/tests/test_ll_loop_execution.py` — `TestMakeInstanceId`: unit tests for `_make_instance_id(loop_name)` — verify format (`r"^{loop_name}-\d{8}T\d{6}$"`), two successive calls return distinct values, output embeds the `loop_name` prefix
- `scripts/tests/test_concurrency.py` — `TestMultiInstanceSameName`: concurrent test (follow `threading.Barrier` pattern at lines 333–355) verifying two instances of the **same** loop name with different `instance_id` values both acquire their locks and produce distinct lock files without conflict

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` calls `list_running_loops(loops_dir)` at line 54; the deduplication fix changes returned entries (dedup by logical loop name, not instance-id stem) — no code change needed, but verify `ll-loop list --running` output shows correct loop names after the fix
- `scripts/little_loops/fsm/__init__.py` — re-exports `LockManager`, `StatePersistence`, `PersistentExecutor`, `list_running_loops` in `__all__`; new `instance_id` kwargs are additive — no change needed

### Key Codebase References
- `concurrency.py:131,149` — `running_dir / f"{loop_name}.lock"` (both replace with `instance_id or loop_name`)
- `concurrency.py:169` — `find_conflict()` globs `*.lock"` — already picks up any lock file; no change needed, but `ScopeLock.loop_name` field (stored in lock JSON) still holds the logical name and will continue to correctly identify the loop
- `persistence.py:206-207` — `running_dir / f"{loop_name}.state.json"` and `.events.jsonl`
- `persistence.py:590` — deduplication: `if pid_file.stem in known_names: continue`; with instance-IDs the stem becomes `"autodev-20240115T103000"` which won't match `s.loop_name = "autodev"` — strip with `re.sub(r"-\d{8}T\d{6}$", "", pid_file.stem)` before the `known_names` check
- `persistence.py:45` — `_RUN_FOLDER = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{6})-(.+)$")` — this regex matches history archive folder names (dashed-date format: `2024-01-15T103000`); it is **not** used for running-dir deduplication and does **not** need updating for this issue
- `__init__.py:122-124` — `--foreground-internal` hidden arg (exact model to follow for `--instance-id`; use `type=str, default=None` instead of `action="store_true"`)
- `run.py:203-214` — PID file path, `foreground_pid_file`, `atexit` closure
- `_helpers.py:250-251` — `pid_file` and `log_file` path construction
- `run.py:293` — uses `%Y%m%d-%H%M%S` for worktree timestamp (no dashes: `20240115-103000`); `_make_instance_id` uses `%Y%m%dT%H%M%S` (no dashes: `20240115T103000`) — intentionally different from archive format (`persistence.py:316` uses `%Y-%m-%dT%H%M%S` with dashes in the date, producing `2024-01-15T103000`); instance-id format is compact for filesystem stems

## Scope Boundaries

- Does NOT add `_find_instances`, `cmd_status` aggregation, `cmd_stop` multi-kill, or `cmd_resume` multi-instance error — those are ENH-1355.
- Does NOT change `LoopState.loop_name` (stays logical name).
- Does NOT update docs, skills, or COMMANDS.md — those are ENH-1355.

## Impact

- **Priority**: P2
- **Effort**: Medium — 5 core files + 4 test files, all additive kwargs
- **Risk**: Low — all new kwargs default to `None` (backward-compat)
- **Breaking Change**: No

## Labels

`enhancement`, `multi-instance`, `ll-loop`, `path-scoping`

## Resolution

Implemented all 17 steps from the implementation plan:

- Added `_make_instance_id(loop_name)` to `_helpers.py` returning `f"{loop_name}-{datetime:%Y%m%dT%H%M%S}"`
- Updated `run_background` to generate `instance_id` and embed `--instance-id` in the foreground-internal re-exec command; pid/log files now use `{instance_id}.*` naming
- Added hidden `--instance-id` arg to `run_parser` and `resume_parser` in `__init__.py`
- Updated `cmd_run` in `run.py` to generate `instance_id` (plain foreground) or read it from `args.instance_id` (foreground-internal); all runtime files scoped through `instance_id or loop_name`
- Added `instance_id: str | None = None` kwarg to `LockManager.acquire/release` in `concurrency.py`; lock file path uses `{instance_id or loop_name}.lock`
- Added `instance_id: str | None = None` kwarg to `StatePersistence.__init__` and `PersistentExecutor.__init__` in `persistence.py`; state/events files use `{instance_id or loop_name}.*`; fixed `list_running_loops` deduplication to strip `_INSTANCE_SUFFIX` before `known_names` check
- Updated `cmd_resume` in `lifecycle.py` to read `args.instance_id` and forward to `PersistentExecutor`; PID path scoped via `{instance_id or loop_name}.pid`
- Updated 5 breaking test assertions in `test_cli_loop_background.py` and `test_ll_loop_execution.py` to use glob patterns
- Added `TestMakeInstanceId` in `test_cli_loop_background.py` and deduplication tests in `test_fsm_persistence.py`
- Added `TestMultiInstanceSameName` in `test_concurrency.py` covering distinct lock files and non-overlapping scope concurrent execution

All 287 targeted tests pass. All changes are backward-compatible (`instance_id=None` falls back to `loop_name`).

## Session Log
- `/ll:ready-issue` - 2026-05-03T19:45:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3997cebe-d99f-421c-8cd0-f84f10ad032e.jsonl`
- `/ll:wire-issue` - 2026-05-03T19:40:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19eb8221-9d6c-4f34-842e-7ec481236e2f.jsonl`
- `/ll:refine-issue` - 2026-05-03T19:30:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a0fd84b-8053-48e5-b209-d00cba50f314.jsonl`
- `/ll:confidence-check` - 2026-05-03T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed1d4ef5-2706-43f1-84bd-0fa730017e92.jsonl`
- `/ll:issue-size-review` - 2026-05-03T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e26d0d3-b923-4ec1-86ac-7959fadea8f7.jsonl`
- `/ll:manage-issue` - 2026-05-03T19:56:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

**Completed** | Created: 2026-05-03 | Completed: 2026-05-03 | Priority: P2
