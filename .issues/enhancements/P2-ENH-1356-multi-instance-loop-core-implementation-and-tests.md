---
id: ENH-1356
type: ENH
priority: P2

confidence_score: 95
outcome_confidence: 85
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-03T20:53:16Z
parent: ENH-1355
---

# ENH-1356: Multi-Instance Loop — Core Implementation + Tests

## Summary

Decomposed from ENH-1355. Add `_find_instances` to `lifecycle.py` to discover all running instances of a named loop. Rewrite `cmd_status`, `cmd_stop`, `cmd_resume` to aggregate across instances, and update `cmd_list` deduplication in `info.py`. Update all affected test files and write new multi-instance tests.

**Depends on**: ENH-1354 must be merged first (provides instance-ID-named runtime files).

## Parent Issue

Decomposed from ENH-1355: Multi-Instance Loop — Aggregated CLI (status/stop/resume/list) + Docs & Skills

## Current Behavior

After ENH-1354 merged, every `ll-loop run` invocation writes state to an instance-ID-scoped file (e.g., `autodev-20260503T122306.state.json`). However, `cmd_status`, `cmd_stop`, and `cmd_resume` in `lifecycle.py` still construct a `StatePersistence` object using the bare logical name (e.g., `autodev.state.json`), which no longer exists for any active loop. As a result:
- `ll-loop status <name>` fails to find any state and reports nothing.
- `ll-loop stop <name>` fails to terminate running instances.
- `ll-loop resume <name>` fails to find the awaiting-continuation state.
- `ll-loop list --running` shows duplicate rows when multiple instances of the same loop are running.

## Expected Behavior

- `_find_instances(loop_name, running_dir)` globs `{loop_name}-*.state.json` plus `{loop_name}.state.json` (legacy), returns list of `(instance_id, LoopState)` tuples.
- `ll-loop status autodev` shows all running instances in a numbered list with per-instance detail (state, PID, log path, log age).
- `ll-loop stop autodev` terminates all running instances.
- `ll-loop resume autodev` errors with a list of running instance IDs when 2+ match (single-instance resume unchanged).
- `ll-loop list` deduplicates or groups by `loop_name` so multiple instances don't produce confusing duplicate rows.
- Legacy files without timestamp suffix continue to work transparently.

### Aggregate status output (2 instances):
```
2 instances of 'autodev':

[1] autodev-20260503T122306
  Status: running
  Current state: implement
  Iteration: 12
  PID: 54147 (running)
  Log: .loops/.running/autodev-20260503T122306.log
  Log updated: 8m 12s ago

[2] autodev-20260503T122340
  Status: running
  Current state: refine_current
  Iteration: 3
  PID: 58522 (running)
  Log: .loops/.running/autodev-20260503T122340.log
  Log updated: 3m 6s ago
```

## Implementation Steps

1. Add `_find_instances(loop_name: str, running_dir: Path) -> list[tuple[str, LoopState]]` to `scripts/little_loops/cli/loop/lifecycle.py` — glob `{loop_name}-*.state.json` plus `{loop_name}.state.json` for legacy; use `_INSTANCE_SUFFIX = re.compile(r"-\d{8}T\d{6}$")` to strip timestamp suffix and recover logical `loop_name`. Promote `_INSTANCE_SUFFIX` to module level in `persistence.py` (currently defined inline in `list_running_loops()`) so both functions share the same pattern.
2. Rewrite `cmd_status` (line 46) in `lifecycle.py` to call `_find_instances` and display aggregated output; single-instance output unchanged.
3. Rewrite `cmd_stop` (line 123) in `lifecycle.py` to call `_find_instances` and terminate all matching instances.
4. Rewrite `cmd_resume` (line 180) in `lifecycle.py` to call `_find_instances`; when 2+ matches found, print error listing instance IDs and exit non-zero (single-instance unchanged); update `foreground_pid_file` (line 201) and `atexit._cleanup_pid` closure (lines 206-209) to use the resolved instance-ID-scoped path.
5. Update `scripts/little_loops/cli/loop/info.py:52-54` (`cmd_list`) to handle multiple `LoopState` objects with the same `loop_name` — group or deduplicate the display table.
6. Update `scripts/tests/test_cli_loop_lifecycle.py:563` (`test_plain_foreground_resume_writes_pid_file`) to use instance-ID-aware lookup. Update additional breaking tests: `TestCmdResumeBackground.test_foreground_internal_registers_pid_cleanup` (line 531), `test_foreground_internal_does_not_overwrite_parent_pid` (line 613), `TestCmdResume.test_resume_registers_signal_handlers` (line 386), `TestCmdStop.test_stop_with_pid_sends_sigterm_and_waits` (line 127), `test_stop_sends_sigkill_if_process_does_not_exit` (line 156), `test_stop_sigkill_handles_race_if_process_exits_between_poll_and_kill` (line 186), `TestCmdStatusLogFile` (lines 903, 956). Patch target for `TestCmdStatusJson` tests (~lines 2371, 2398, 2431) changes from `StatePersistence.load_state` to `lifecycle._find_instances`.
7. Verify `scripts/tests/test_ll_loop_state.py` — `TestCmdStop` at lines 89, 132, 167: confirm `_find_instances` discovers legacy bare-stem `test-loop.state.json` files (no timestamp) and `cmd_stop` writes status back to the same path; update fixtures to pass explicit `instance_id=None` if needed.
8. Update `scripts/tests/test_ll_loop_integration.py` — `test_list_running_shows_status_info` (line 315): update bare-stem state file fixtures to use instance-ID names, or verify `cmd_list` deduplication handles legacy names cleanly without duplicate rows.
9. Update `scripts/tests/test_ll_loop_commands.py` — `TestCmdHistory.events_file` fixture (line 533): write `test-loop.events.jsonl` as legacy bare-stem file and confirm `cmd_history` reads it; update `TestCmdStatusJson` tests (lines ~2371, ~2398, ~2431) to patch `little_loops.cli.loop.lifecycle._find_instances` instead of `StatePersistence.load_state`.
10. Run full test suite: `python -m pytest scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_ll_loop_state.py scripts/tests/test_ll_loop_integration.py scripts/tests/test_ll_loop_commands.py`. Then smoke test with two concurrent `ll-loop run` invocations.
11. Update `scripts/tests/test_cli_loop_background.py` — rework `TestCmdStopWithPid` and `TestCmdStatusWithPid`: change patch target from `"little_loops.fsm.persistence.StatePersistence"` (constructor) to `"little_loops.cli.loop.lifecycle._find_instances"` returning `list[tuple[str, LoopState]]`; update bare-stem `.pid` file fixtures to use instance-ID-scoped filenames.
12. Update `scripts/tests/test_cli.py` — rework `TestLoopCommands` (~line 2192) stop-subcommand test with the same `_find_instances` patch pattern.
13. Write new test class for `_find_instances` (can be placed in `test_cli_loop_lifecycle.py` or `test_ll_loop_state.py`) — cover bare-stem discovery, timestamp-scoped discovery, mixed (both), and empty-result cases. Follow inline fixture pattern from `TestCmdStop` in `test_ll_loop_state.py` (write state JSON directly to `running_dir / "test-loop.state.json"`).
14. Write new multi-instance tests: `cmd_status` aggregate output (two state files → numbered list), `cmd_stop` multi-instance (two state files → both updated to `status: interrupted`), `cmd_resume` multi-instance error (two state files → exit non-zero + list of instance IDs), `cmd_list` deduplication (two state files with same `loop_name` → no duplicate rows).

## Integration Map

### Files to Modify (Implementation)
- `scripts/little_loops/cli/loop/lifecycle.py` — `_find_instances`, `cmd_status`, `cmd_stop`, `cmd_resume`
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` deduplication
- `scripts/little_loops/fsm/persistence.py` — promote `_INSTANCE_SUFFIX` to module level

### Tests to Update
- `scripts/tests/test_cli_loop_lifecycle.py` — multiple test classes (see step 6)
- `scripts/tests/test_ll_loop_state.py` — `TestCmdStop` at lines 89, 132, 167
- `scripts/tests/test_ll_loop_integration.py` — `test_list_running_shows_status_info` (line 315)
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdHistory` (line 533), `TestCmdStatusJson` (~2371, ~2398, ~2431)
- `scripts/tests/test_cli_loop_background.py` — `TestCmdStopWithPid` and `TestCmdStatusWithPid`
- `scripts/tests/test_cli.py` — `TestLoopCommands` (~line 2192)

### Tests to Write (New)
- New test class for `_find_instances` (bare-stem, timestamp-scoped, mixed, empty)
- New multi-instance tests for `cmd_status`, `cmd_stop`, `cmd_resume`, `cmd_list`

### Tests to Verify (No Code Change Expected)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py` — `TestUtilityFunctions` uses bare-stem state fixtures (`loop-a.state.json`); `TestStatePersistence` / `TestAcceptanceCriteria` use instance-ID-scoped files. Verify no breakage after `_INSTANCE_SUFFIX` promotion to module level in `persistence.py`. No test code changes expected since promotion is transparent to `list_running_loops` behavior.
- `scripts/tests/test_ll_loop_execution.py` — `TestEndToEndExecution` uses glob-based assertions (`*.state.json`, `*.pid`) that should continue to pass after `lifecycle.py` rewrite. Verify no regressions; no code changes expected.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — line 23 imports `cmd_resume, cmd_status, cmd_stop` from `lifecycle`; line 22 imports `cmd_list` from `info`. These are the dispatch entry points; not changed but are live callers of the rewritten functions.

### Breakage Coupling (ENH-1357 Scope — Noted for Awareness)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/cleanup-loops/SKILL.md` — Steps 2, 6, 7 hard-code single-instance assumptions that break for multi-instance loops after ENH-1356: (a) Step 2 runs `ll-loop status <name> --json` and parses the `pid` field from a single JSON object — aggregated multi-instance output breaks this parse; (b) Step 7 runs `tail -20 ".loops/.running/<loop_name>.events.jsonl"` using bare logical name — instance-scoped files use `<instance_id>.events.jsonl`; (c) lines 113/226 clean `.loops/.running/<loop_name>.pid` bare-stem paths that no longer exist post-ENH-1354. This file is **out of ENH-1356 scope** (ENH-1357 owns doc/skill updates) but is flagged here so the implementer knows the skill is broken until ENH-1357 ships.

### Key Codebase References
- `lifecycle.py:46` — `cmd_status`
- `lifecycle.py:123` — `cmd_stop`
- `lifecycle.py:180` — `cmd_resume`; `lifecycle.py:200-209` — `foreground_pid_file`, `atexit` closure
- `info.py:52-54` — `cmd_list` / `list_running_loops` iteration
- `persistence.py:45` — `_RUN_FOLDER` regex (NOT the right model — use `_INSTANCE_SUFFIX` instead)
- `persistence.py:566-590` — `list_running_loops` two-pass glob logic and `known_names` deduplication (contains inline `_INSTANCE_SUFFIX`)

### Codebase Research Findings

**Critical: use `_INSTANCE_SUFFIX`, not `_RUN_FOLDER`:**
- `_RUN_FOLDER` (`persistence.py:45`) targets `.history/` folder names with hyphenated date format. NOT used for `.running/` file stems.
- Correct model is `_INSTANCE_SUFFIX` defined inline in `list_running_loops()`: `re.compile(r"-\d{8}T\d{6}$")`. Matches compact timestamp from `_make_instance_id` in `_helpers.py` (`%Y%m%dT%H%M%S`).
- Promote `_INSTANCE_SUFFIX` to module level before adding `_find_instances`.

**`LoopState` has no `instance_id` field** (`persistence.py:64-183`):
- `_find_instances` must derive `instance_id` from `state_file.stem`. For instance-scoped files: `instance_id = state_file.stem`; for legacy bare-name files: `instance_id = None`.

**`list_running_loops` already discovers all instances** (`persistence.py:574-626`):
- `cmd_list --running` already renders duplicate `loop_name` rows today. Fix is display-layer grouping only — no new discovery logic needed in `info.py`.

**`StatePersistence` current call sites** (`lifecycle.py:56, 131, 240`):
- After ENH-1355, they call `_find_instances(loop_name, running_dir)` then instantiate `StatePersistence(loop_name, loops_dir, instance_id=inst_id)` per discovered instance.

### Codebase Research Findings (2026-05-03 Verification)

_Added by `/ll:refine-issue` — verified against current code:_

**ENH-1354 is confirmed merged** — `StatePersistence.__init__` already accepts `instance_id: str | None = None` (persistence.py:196), and `_make_instance_id` exists in `_helpers.py:233`. Every `run` invocation (foreground and background) now assigns an instance-scoped state file.

**`cmd_status` internal call sites** (`lifecycle.py`):
- Line 56: `StatePersistence(loop_name, loops_dir)` — no `instance_id` → resolves to unscoped `{loop_name}.state.json`, which no longer exists for any active loop
- Line 64: PID file as `running_dir / f"{loop_name}.pid"` — hard-coded to logical name
- Line 67: Log file as `running_dir / f"{loop_name}.log"` — hard-coded to logical name

**`cmd_stop` has no `args` parameter** (`lifecycle.py:123`):
- Signature is `cmd_stop(loop_name, loops_dir, logger)` — no `args`. Cannot receive `instance_id` from CLI. Must use `_find_instances` for discovery.
- Line 131: `StatePersistence(loop_name, loops_dir)` — unscoped
- Line 147: PID file as `running_dir / f"{loop_name}.pid"` — unscoped

**`cmd_resume` asymmetry** (`lifecycle.py:180`):
- Line 200: `instance_id = getattr(args, "instance_id", None)` — reads instance_id from args
- Line 201: `pid_file = running_dir / f"{instance_id or loop_name}.pid"` — instance-scoped when provided
- **Line 240**: `StatePersistence(loop_name, loops_dir)` — **unscoped** (the pre-flight "is it awaiting_continuation?" check). This will fail to find state for any loop started after ENH-1354.
- Line 263: `PersistentExecutor(... instance_id=instance_id)` — correctly instance-scoped for execution

**`cmd_list` display fix location** (`info.py`):
- The `--running` branch iterates `states` at line 68 (`for state in states: ...`) with no grouping by `loop_name`. Fix is adding a grouping step over the `states` list before rendering. No changes needed to `list_running_loops` in `persistence.py`.

**Exact patch strings that need changing in tests:**

| Test | File | Current patch target | New patch target |
|---|---|---|---|
| `TestCmdStatusJson` | `test_ll_loop_commands.py:2371,2398,2431` | `patch.object(StatePersistence, "load_state", return_value=...)` | `patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[...])` |
| `TestCmdStopWithPid` / `TestCmdStatusWithPid` | `test_cli_loop_background.py` | `patch("little_loops.fsm.persistence.StatePersistence")` with `mock_cls.return_value.load_state.return_value = mock_state` | `patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(instance_id, mock_state)])` |
| `test_stop_command` | `test_cli.py` | `patch("little_loops.fsm.persistence.StatePersistence")` with `mock_sp_cls.return_value = mock_sp; mock_sp.load_state.return_value = mock_state` | `patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(loop_name, mock_state)])` |

**Class name correction for `test_cli.py`:** Issue step 12 says `TestLoopCommands (~line 2192)` — actual class is `TestMainLoopAdditionalCoverage`, method `test_stop_command` (line ~2191). The patch string `"little_loops.fsm.persistence.StatePersistence"` is correct; only the class name reference in the issue was wrong.

**Inline fixture pattern for `_find_instances` new tests** (from `TestCmdStop` in `test_ll_loop_state.py:76`):
- Write state JSON directly: `state_file = running_dir / "test-loop.state.json"; state_file.write_text(json.dumps({...}))`
- Instance-scoped variant: `running_dir / "test-loop-20260503T122306.state.json"`
- The `_find_instances` function globs `running_dir` directly, so no mock is needed for new unit tests — just write files and call the function.

## Success Metrics

- `ll-loop status autodev` lists all N running instances with individual state, PID, and log details.
- `ll-loop stop autodev` terminates all running instances.
- `ll-loop resume autodev` with 2+ instances prints error listing instance IDs and exits non-zero.
- `ll-loop list` does not show duplicate `loop_name` rows for multi-instance runs.
- All listed test files pass.
- New `_find_instances` test class covers all four cases: bare-stem, timestamp-scoped, mixed, empty.

## Scope Boundaries

- Does NOT update docs or skill files — those are in ENH-1357.
- Does NOT re-implement instance_id generation or path-construction — ships in ENH-1354.
- Does NOT add `--select-instance` flag.

## Impact

- **Priority**: P2
- **Effort**: Medium — 3 CLI files, 6 test files, new test class
- **Risk**: Low — `_find_instances` is additive; fallback to single instance preserves current behavior
- **Breaking Change**: No

## Labels

`enhancement`, `multi-instance`, `fsm-loops`, `cli`

## Session Log
- `/ll:ready-issue` - 2026-05-03T20:32:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9801a914-60fd-4c39-bd37-f692c9dedc08.jsonl`
- `/ll:wire-issue` - 2026-05-03T20:27:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/879ddfc0-5808-4a4e-a0a4-51d0bf3fb3a9.jsonl`
- `/ll:refine-issue` - 2026-05-03T20:21:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94486e63-c38d-4bfc-93ce-d33e07f115ca.jsonl`
- `/ll:issue-size-review` - 2026-05-03T21:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/995ae302-a902-4497-a747-428e14fa83da.jsonl`
- `/ll:confidence-check` - 2026-05-03T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a287343-6cbe-4223-ac2d-83767cd52baf.jsonl`

---

## Resolution

Implemented all 14 steps from the issue:

- **`persistence.py`**: Promoted `_INSTANCE_SUFFIX` to module level; added `_find_instances(loop_name, running_dir)` that globs `{loop_name}-*.state.json` (instance-scoped) and `{loop_name}.state.json` (legacy), returning `list[tuple[str | None, LoopState]]`.
- **`lifecycle.py`**: Rewrote `cmd_status` (aggregate numbered-list for 2+ instances), `cmd_stop` (terminates all running instances), `cmd_resume` (errors with instance list when 2+ resumable). Added `_find_instances` as module-level import to enable `patch("little_loops.cli.loop.lifecycle._find_instances")`.
- **`info.py`**: Updated `cmd_list --running` to group by `loop_name`, rendering multi-instance loops as a single grouped row.
- **Tests updated**: `test_cli_loop_lifecycle.py`, `test_cli_loop_background.py`, `test_ll_loop_commands.py`, `test_cli.py` — all `StatePersistence.load_state` patches replaced with `lifecycle._find_instances` patches.
- **New tests**: `TestFindInstances` (6 cases), `TestCmdStatusMultiInstance`, `TestCmdStopMultiInstance`, `TestCmdResumeMultiInstance`, `TestCmdListMultiInstance`.

All 377 affected tests pass; 5 pre-existing unrelated failures unchanged.

**Closed** | Completed: 2026-05-03 | Priority: P2
