---
id: ENH-1355
type: ENH
priority: P2
parent_issue: ENH-1351
---

# ENH-1355: Multi-Instance Loop — Aggregated CLI (status/stop/resume/list) + Docs & Skills

## Summary

Decomposed from ENH-1351. Builds on ENH-1354 (instance_id path scoping). Add `_find_instances` to `lifecycle.py` to discover all running instances of a named loop, then rewrite `cmd_status`, `cmd_stop`, `cmd_resume`, and update `cmd_list` to aggregate across instances. Update all remaining tests (lifecycle, state, integration, commands) and all documentation/skill files that reference bare-loop-name runtime paths.

## Parent Issue

Decomposed from ENH-1351: Multi-Instance Loop Naming with Aggregated Status

**Depends on**: ENH-1354 must be merged first (provides instance-ID-named runtime files).

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

## Success Metrics

- `ll-loop status autodev` lists all N running instances with individual state, PID, and log details.
- `ll-loop stop autodev` terminates all running instances.
- `ll-loop resume autodev` with 2+ instances prints error listing instance IDs and exits non-zero.
- `ll-loop list` does not show duplicate `loop_name` rows for multi-instance runs.
- All listed test files pass.

## Implementation Steps

1. Add `_find_instances(loop_name: str, running_dir: Path) -> list[tuple[str, LoopState]]` to `scripts/little_loops/cli/loop/lifecycle.py` — glob `{loop_name}-*.state.json` plus `{loop_name}.state.json` for legacy; use a regex similar to `_RUN_FOLDER` (`persistence.py:45`) to strip timestamp suffix and recover logical `loop_name`.
2. Rewrite `cmd_status` (line 46) in `lifecycle.py` to call `_find_instances` and display aggregated output; single-instance output unchanged.
3. Rewrite `cmd_stop` (line 123) in `lifecycle.py` to call `_find_instances` and terminate all matching instances.
4. Rewrite `cmd_resume` (line 180) in `lifecycle.py` to call `_find_instances`; when 2+ matches found, print error listing instance IDs and exit non-zero (single-instance unchanged); update `foreground_pid_file` (line 201) and `atexit._cleanup_pid` closure (lines 206-209) to use the resolved instance-ID-scoped path.
5. Update `scripts/little_loops/cli/loop/info.py:52-54` (`cmd_list`) to handle multiple `LoopState` objects with the same `loop_name` — group or deduplicate the display table.
6. Update `scripts/tests/test_cli_loop_lifecycle.py:563` (`test_plain_foreground_resume_writes_pid_file`) to use instance-ID-aware lookup. Update additional breaking tests: `TestCmdResumeBackground.test_foreground_internal_registers_pid_cleanup` (line 531), `test_foreground_internal_does_not_overwrite_parent_pid` (line 613), `TestCmdResume.test_resume_registers_signal_handlers` (line 386), `TestCmdStop.test_stop_with_pid_sends_sigterm_and_waits` (line 127), `test_stop_sends_sigkill_if_process_does_not_exit` (line 156), `test_stop_sigkill_handles_race_if_process_exits_between_poll_and_kill` (line 186), `TestCmdStatusLogFile` (lines 903, 956). Patch target for `TestCmdStatusJson` tests (~lines 2371, 2398, 2431) changes from `StatePersistence.load_state` to `lifecycle._find_instances`.
7. Verify `scripts/tests/test_ll_loop_state.py` — `TestCmdStop` at lines 89, 132, 167: confirm `_find_instances` discovers legacy bare-stem `test-loop.state.json` files (no timestamp) and `cmd_stop` writes status back to the same path; update fixtures to pass explicit `instance_id=None` if needed.
8. Update `scripts/tests/test_ll_loop_integration.py` — `test_list_running_shows_status_info` (line 315): update bare-stem state file fixtures to use instance-ID names, or verify `cmd_list` deduplication handles legacy names cleanly without duplicate rows.
9. Update `scripts/tests/test_ll_loop_commands.py` — `TestCmdHistory.events_file` fixture (line 533): write `test-loop.events.jsonl` as legacy bare-stem file and confirm `cmd_history` reads it; update `TestCmdStatusJson` tests (lines ~2371, ~2398, ~2431) to patch `little_loops.cli.loop.lifecycle._find_instances` instead of `StatePersistence.load_state`.
10. Run full test suite: `python -m pytest scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_ll_loop_state.py scripts/tests/test_ll_loop_integration.py scripts/tests/test_ll_loop_commands.py`. Then smoke test with two concurrent `ll-loop run` invocations.
11. Update `scripts/little_loops/fsm/persistence.py` docstrings — module-level docstring (lines 9–18) and `StatePersistence` class docstring (line 193): replace `{loop_name}.*` file references with `{instance_id}.*`.
12. Update `docs/reference/API.md` — `StatePersistence.__init__` and `PersistentExecutor.__init__` signature blocks (add `instance_id: str | None = None`), `LockManager.acquire`/`release` methods table, and `.running/` directory layout diagram under `StatePersistence` section.
13. Update `docs/guides/LOOPS_GUIDE.md` — `.running/` file layout section: reflect `{instance_id}.*` naming and the aggregated status display.
14. Update `skills/cleanup-loops/SKILL.md` — Steps 6 and 7: replace `rm -f ".loops/.running/<loop_name>.pid"` and `tail -20 ".loops/.running/<loop_name>.events.jsonl"` with glob-based paths (`{loop_name}-*.pid`, `{loop_name}-*.events.jsonl`) or delegate to `ll-loop stop`.
15. Update `skills/rename-loop/SKILL.md` — Step 4: replace `test -f ".loops/.running/<old_name>.pid"` guard with glob (`ls .loops/.running/<old_name>*.pid 2>/dev/null | head -1`) to correctly detect running instances.
16. Update `skills/analyze-loop/SKILL.md` and `skills/assess-loop/SKILL.md` — Step 1: handle duplicate `loop_name` entries from `ll-loop list --running --json` by using `instance_id` (or combined `loop_name:instance_id` key) for user selection disambiguation.
17. Update `docs/reference/COMMANDS.md` — `/ll:cleanup-loops` description (~line 661): replace `<loop_name>.pid` references with glob pattern `{loop_name}-*.pid`.

## Integration Map

### Files to Modify (Implementation)
- `scripts/little_loops/cli/loop/lifecycle.py` — `_find_instances`, `cmd_status`, `cmd_stop`, `cmd_resume`
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` deduplication

### Tests to Update
- `scripts/tests/test_cli_loop_lifecycle.py` — multiple test classes (see implementation steps 6)
- `scripts/tests/test_ll_loop_state.py` — `TestCmdStop` at lines 89, 132, 167
- `scripts/tests/test_ll_loop_integration.py` — `test_list_running_shows_status_info` (line 315)
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdHistory` (line 533), `TestCmdStatusJson` (~2371, ~2398, ~2431)

### Docs & Skills to Update
- `scripts/little_loops/fsm/persistence.py` — module + class docstrings
- `docs/reference/API.md`
- `docs/guides/LOOPS_GUIDE.md`
- `skills/cleanup-loops/SKILL.md`
- `skills/rename-loop/SKILL.md`
- `skills/analyze-loop/SKILL.md`
- `skills/assess-loop/SKILL.md`
- `docs/reference/COMMANDS.md`

### Key Codebase References
- `lifecycle.py:46` — `cmd_status`
- `lifecycle.py:123` — `cmd_stop`
- `lifecycle.py:180` — `cmd_resume`; `lifecycle.py:200-209` — `foreground_pid_file`, `atexit` closure
- `info.py:52-54` — `cmd_list` / `list_running_loops` iteration
- `persistence.py:45` — `_RUN_FOLDER` regex (model for timestamp-suffix stripping in `_find_instances`)
- `persistence.py:566-590` — `list_running_loops` two-pass glob logic and `known_names` deduplication

## Scope Boundaries

- Does NOT re-implement instance_id generation or path-construction — those ship in ENH-1354.
- Does NOT add `--select-instance` flag (future work per ENH-1351 scope boundaries).
- Does NOT add instance-level log streaming UI.

## Impact

- **Priority**: P2
- **Effort**: Medium — 2 core CLI files, 4 test files, 8 docs/skill files
- **Risk**: Low — `_find_instances` is additive; fallback to single instance preserves current behavior
- **Breaking Change**: No

## Session Log
- `/ll:issue-size-review` - 2026-05-03T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e26d0d3-b923-4ec1-86ac-7959fadea8f7.jsonl`

---

**Open** | Created: 2026-05-03 | Priority: P2
