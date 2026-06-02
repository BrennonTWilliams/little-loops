---
id: ENH-1355
type: ENH
priority: P2

decision_needed: false
confidence_score: 98
outcome_confidence: 72
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
size: Very Large
parent: ENH-1351
status: done
completed_at: 2026-05-10T00:00:00Z
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

18. Update `scripts/tests/test_cli_loop_background.py` — rework `TestCmdStopWithPid` and `TestCmdStatusWithPid`: change patch target from `"little_loops.fsm.persistence.StatePersistence"` (constructor) to `"little_loops.cli.loop.lifecycle._find_instances"` returning `list[tuple[str, LoopState]]`; update bare-stem `.pid` file fixtures to use instance-ID-scoped filenames.
19. Update `scripts/tests/test_cli.py` — rework `TestLoopCommands` (~line 2192) stop-subcommand test with the same `_find_instances` patch pattern.
20. Write new test class for `_find_instances` (can be placed in `test_cli_loop_lifecycle.py` or `test_ll_loop_state.py`) — cover bare-stem discovery, timestamp-scoped discovery, mixed (both), and empty-result cases.
21. Write new `cmd_status`/`cmd_stop`/`cmd_resume`/`cmd_list` multi-instance tests (aggregate output format, multi-stop, multi-resume error path, deduplication).
22. Update `docs/reference/CLI.md` — revise `ll-loop status`, `ll-loop stop`, `ll-loop resume`, `ll-loop list` sections to reflect multi-instance semantics and the new `--json` output shape.
23. Update `docs/generalized-fsm-loop.md` — fix bare-name file references in directory layout diagram (lines 1433–1435, 1518, 1537) to show `{instance-id}.*` naming.

## Integration Map

### Files to Modify (Implementation)
- `scripts/little_loops/cli/loop/lifecycle.py` — `_find_instances`, `cmd_status`, `cmd_stop`, `cmd_resume`
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` deduplication

### Tests to Update
- `scripts/tests/test_cli_loop_lifecycle.py` — multiple test classes (see implementation steps 6)
- `scripts/tests/test_ll_loop_state.py` — `TestCmdStop` at lines 89, 132, 167
- `scripts/tests/test_ll_loop_integration.py` — `test_list_running_shows_status_info` (line 315)
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdHistory` (line 533), `TestCmdStatusJson` (~2371, ~2398, ~2431)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_background.py` — `TestCmdStopWithPid` and `TestCmdStatusWithPid` patch `StatePersistence` constructor; once `cmd_stop`/`cmd_status` call `_find_instances`, the patch target must shift to `little_loops.cli.loop.lifecycle._find_instances`; bare-stem `.pid` file fixtures also need instance-ID-aware names [Agent 1 + 3 finding]
- `scripts/tests/test_cli.py` — `TestLoopCommands` (~line 2192) patches `patch("little_loops.fsm.persistence.StatePersistence")` for the `stop` subcommand via `main_loop()`; same patch target breakage as above [Agent 3 finding]

### Tests to Write (New)

_Wiring pass added by `/ll:wire-issue`:_
- New test class for `_find_instances` — verify: (a) discovers bare-stem `{loop_name}.state.json` with `instance_id=None`; (b) discovers `{loop_name}-{YYYYMMDDTHHMMSS}.state.json` with correct `instance_id`; (c) returns both when both exist; (d) returns empty list when no match. Follow inline fixture pattern from `TestCmdStop` in `test_ll_loop_state.py` (write state JSON directly to `running_dir / "test-loop.state.json"`). [Agent 3 finding]
- New test for `cmd_status` aggregate output — write two instance-scoped state files, call `cmd_status`, assert numbered-list output `[1]` / `[2]` and per-instance fields (`Status:`, `PID:`, `Log:`). [Agent 3 finding]
- New test for `cmd_stop` multi-instance — write two instance-scoped state files, call `cmd_stop`, assert both files are updated to `status: interrupted`. [Agent 3 finding]
- New test for `cmd_resume` multi-instance error — write two instance-scoped state files, call `cmd_resume`, assert exit code non-zero and output lists instance IDs. [Agent 3 finding]
- New test for `cmd_list` deduplication — write two state files with same `loop_name`, call `cmd_list --running`, assert no duplicate `loop_name` rows in output. [Agent 3 finding]

### Docs & Skills to Update
- `scripts/little_loops/fsm/persistence.py` — module + class docstrings
- `docs/reference/API.md`
- `docs/guides/LOOPS_GUIDE.md`
- `skills/cleanup-loops/SKILL.md`
- `skills/rename-loop/SKILL.md`
- `skills/analyze-loop/SKILL.md`
- `skills/assess-loop/SKILL.md`
- `docs/reference/COMMANDS.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### ll-loop status <loop>`, `#### ll-loop stop <loop>`, `#### ll-loop resume <loop>`, `#### ll-loop list` sections each describe single-instance semantics; `--json` docs say it returns a flat state dict (now may return multi-instance shape); `stop` says "Stop a running loop" (now stops all instances); `resume` has no mention of multi-instance error path [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — directory layout diagram at lines 1433–1435 shows bare-name `fix-types.state.json`/`.events.jsonl`; lines 1518, 1537 comment `// .loops/.running/<name>.state.json` and `Events stream to .loops/.running/<name>.events.jsonl` — all will be `<instance-id>.*` after ENH-1354/1355 [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py` — line 23 imports `cmd_resume, cmd_status, cmd_stop` from `lifecycle`; line 22 imports `cmd_list` from `info`. These are the dispatch entry points from the `ll-loop` CLI argument parser and are not changed, but they are the live callers of the rewritten functions. [Agent 1 finding]

### Key Codebase References
- `lifecycle.py:46` — `cmd_status`
- `lifecycle.py:123` — `cmd_stop`
- `lifecycle.py:180` — `cmd_resume`; `lifecycle.py:200-209` — `foreground_pid_file`, `atexit` closure
- `info.py:52-54` — `cmd_list` / `list_running_loops` iteration
- `persistence.py:45` — `_RUN_FOLDER` regex (model for timestamp-suffix stripping in `_find_instances`)
- `persistence.py:566-590` — `list_running_loops` two-pass glob logic and `known_names` deduplication

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical correction for Step 1 — `_RUN_FOLDER` vs `_INSTANCE_SUFFIX`:**
- `_RUN_FOLDER` (`persistence.py:45`) targets `.history/` folder names using a hyphenated date format (`r"^(\d{4}-\d{2}-\d{2}T\d{6})-(.+)$"`). It is NOT used for `.running/` file stems.
- The correct model for stripping runtime instance suffixes is `_INSTANCE_SUFFIX`, defined inline inside `list_running_loops()`: `re.compile(r"-\d{8}T\d{6}$")`. This matches the compact timestamp format produced by `_make_instance_id` in `_helpers.py` (`%Y%m%dT%H%M%S`).
- Recommend promoting `_INSTANCE_SUFFIX` to module level in `persistence.py` before adding `_find_instances`, so both functions share the same pattern without duplication.

**`LoopState` has no `instance_id` field** (`persistence.py:64-183`):
- The dataclass persists only `loop_name` (the logical name, e.g., `"autodev"`). Instance identity lives only in the filename stem.
- `_find_instances` must derive `instance_id` from each `state_file.stem` — for instance-scoped files (e.g., `autodev-20240115T103000.state.json`) `instance_id = state_file.stem`; for legacy bare-name files (`autodev.state.json`) yield `instance_id = None` (or `loop_name`).

**`list_running_loops` already discovers all instances** (`persistence.py:574-626`):
- The first pass globs `*.state.json` (unrestricted), returning one `LoopState` per file — including multiple instances of the same logical loop. The `known_names` dedup only prevents duplicate "starting" PID-only entries, not multi-instance state files.
- `cmd_list --running` therefore already renders duplicate `loop_name` rows today. The fix is a display-layer grouping change only — no new discovery logic needed in `info.py`.

**`StatePersistence` current call sites** (`lifecycle.py:56, 131, 240`):
- All three commands instantiate `StatePersistence(loop_name, loops_dir)` with no `instance_id`. After this ENH, they call `_find_instances(loop_name, running_dir)` then instantiate `StatePersistence(loop_name, loops_dir, instance_id=inst_id)` per discovered instance.

**Test mock target for `TestCmdStatusJson`** (`test_ll_loop_commands.py:~2371, ~2398, ~2431`):
- Currently patches `StatePersistence.load_state` returning a single `LoopState`. After ENH-1355, patch target becomes `little_loops.cli.loop.lifecycle._find_instances` and must return `list[tuple[str, LoopState]]`.

**Legacy bare-stem fixture compatibility** (`test_ll_loop_state.py`, `TestCmdStop`):
- Tests write `test-loop.state.json` directly (no timestamp suffix). `_find_instances` must include the `{loop_name}.state.json` legacy path so these fixtures remain discoverable — confirming the issue's legacy-glob requirement is load-bearing, not just aspirational.

## Scope Boundaries

- Does NOT re-implement instance_id generation or path-construction — those ship in ENH-1354.
- Does NOT add `--select-instance` flag (future work per ENH-1351 scope boundaries).
- Does NOT add instance-level log streaming UI.

## Impact

- **Priority**: P2
- **Effort**: Medium — 2 core CLI files, 4 test files, 8 docs/skill files
- **Risk**: Low — `_find_instances` is additive; fallback to single instance preserves current behavior
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-03_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- File count is high (17+ files across implementation, 6 test files, 9 doc/skill files), dragging complexity score to 0/25 despite the core change being isolated to 2 files. Plan extra time for the mechanical test/doc sweep.
- `cmd_list` deduplication approach is slightly open ("group or deduplicate") — implementor should choose a display strategy (e.g., show `loop_name:instance_id` in multi-instance rows) before writing tests to avoid rework.

## Session Log
- `/ll:wire-issue` - 2026-05-03T20:07:45 - `5cbb3f20-7b82-47b5-b9c1-7fb3636aa30c.jsonl`
- `/ll:refine-issue` - 2026-05-03T20:01:08 - `5789665c-c933-4922-be7b-65434de9886a.jsonl`
- `/ll:issue-size-review` - 2026-05-03T20:30:00Z - `5e26d0d3-b923-4ec1-86ac-7959fadea8f7.jsonl`
- `/ll:confidence-check` - 2026-05-03T21:00:00Z - `74ac2a19-bdf8-4b16-af08-be759563c93b.jsonl`
- `/ll:issue-size-review` - 2026-05-03T21:45:00Z - `995ae302-a902-4497-a747-428e14fa83da.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-03
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1356: Multi-Instance Loop — Core Implementation + Tests
- ENH-1357: Multi-Instance Loop — Docs & Skills Updates

---

**Decomposed** | Created: 2026-05-03 | Priority: P2
