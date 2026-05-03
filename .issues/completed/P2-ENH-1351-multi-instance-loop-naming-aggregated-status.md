---
id: ENH-1351
type: ENH
priority: P2
status: open
captured_at: '2026-05-03T17:41:57Z'
discovered_date: '2026-05-03'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 60
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
---

# ENH-1351: Multi-Instance Loop Naming with Aggregated Status

## Summary

When multiple instances of the same loop (e.g. `autodev`) run concurrently, they collide on runtime files (`.pid`, `.log`, `.state.json`, `.events.jsonl`, `.lock`) because `ll-loop` uses the loop name as the key for all of them. Add auto-generated `instance_id` (`{loop_name}-{YYYYMMDDTHHMMSS}`) to namespace runtime files per-instance while keeping logical loop names for user-facing commands. Make `ll-loop status <name>` aggregate across all matching instances.

## Current Behavior

- All runtime files are keyed on loop name: `autodev.pid`, `autodev.state.json`, etc.
- A second `ll-loop run autodev` queues behind the first (`-q`) rather than running independently.
- `ll-loop status autodev` shows only one instance regardless of how many are running.
- `ll-loop stop autodev` only stops the one tracked instance.

## Expected Behavior

- Each `ll-loop run autodev` generates a unique `instance_id` (`autodev-20260503T122306`) at startup.
- Runtime files are scoped to the instance: `autodev-20260503T122306.pid`, `.state.json`, etc.
- `ll-loop status autodev` shows all running instances in a numbered list with per-instance detail.
- `ll-loop stop autodev` stops all running instances.
- `LoopState.loop_name` stays as the logical name (`autodev`) — no schema change.
- Legacy files without timestamp suffix continue to work transparently (instance_id falls back to loop_name).

## Success Metrics

- Two concurrent `ll-loop run autodev` invocations produce distinct runtime files (`autodev-TIMESTAMP1.*` vs `autodev-TIMESTAMP2.*`) with no collision
- `ll-loop status autodev` lists all N running instances with individual state, PID, and log details
- `ll-loop stop autodev` terminates all running instances of the named loop
- Single-instance behavior unchanged: a lone `ll-loop run foo` behaves identically to before (backward-compatible)
- Legacy runtime files without a timestamp suffix (e.g., `foo.pid`) are still recognized and loaded transparently

## Motivation

Users running `ll-parallel` or manually launching multiple loop instances for different issues hit silent collisions — the second instance blocks behind the first instead of running in parallel. There is no way to observe or manage concurrent instances of the same loop type. This is a blocking capability gap for any parallel automation workflow.

## Proposed Solution

Auto-generate `instance_id = f"{loop_name}-{datetime.now().strftime('%Y%m%dT%H%M%S')}"` at the start of each foreground or background run. Thread it through all file path construction. Aggregate by logical `loop_name` in status/stop commands.

**Key interface changes:**

```python
# concurrency.py — LockManager
def acquire(self, loop_name: str, scope, *, instance_id: str | None = None) -> ScopeLock: ...
def release(self, loop_name: str, *, instance_id: str | None = None) -> None: ...

# persistence.py — StatePersistence
class StatePersistence:
    def __init__(self, loop_name: str, loops_dir: Path, instance_id: str | None = None): ...

# persistence.py — PersistentExecutor
class PersistentExecutor:
    def __init__(self, fsm, ..., instance_id: str | None = None): ...

# _helpers.py — new helper
def _make_instance_id(loop_name: str) -> str:
    return f"{loop_name}-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
```

**Hidden CLI arg** (`--instance-id`, `argparse.SUPPRESS`) added to `run_parser` and `resume_parser` so background launcher can pass its pre-generated ID to the foreground child process.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Current function signatures (pre-change):**

```python
# concurrency.py:98
def acquire(self, loop_name: str, scope: list[str]) -> bool: ...
# concurrency.py:143
def release(self, loop_name: str) -> None: ...

# persistence.py:196
def __init__(self, loop_name: str, loops_dir: Path | None = None) -> None: ...

# persistence.py:346
def __init__(
    self,
    fsm: FSMLoop,
    persistence: StatePersistence | None = None,
    loops_dir: Path | None = None,
    **executor_kwargs: Any,
) -> None: ...

# _helpers.py:232
def run_background(loop_name: str, args: argparse.Namespace, loops_dir: Path, subcommand: str = "run") -> int: ...
```

**`PersistentExecutor` internal `StatePersistence` construction (persistence.py:366):**

When no explicit `persistence` is passed to `PersistentExecutor`, the constructor builds one internally:
```python
self.persistence = persistence or StatePersistence(fsm.name, loops_dir or Path(".loops"))
```
The easiest threading path: add `instance_id: str | None = None` to `PersistentExecutor.__init__` and forward it when constructing the default `StatePersistence`. Callers that pass an explicit `persistence` object are unaffected.

**`--queue` / `lock_manager.wait_for_scope` interaction (run.py:227-278):**

When `acquire` returns `False` and `args.queue` is set, `cmd_run` enters a polling wait via `lock_manager.wait_for_scope`. With instance IDs, each run gets its own lock file (`autodev-TIMESTAMP.lock`) and its own scope. Two concurrent runs will no longer conflict on the lock file — so `--queue` becomes a no-op for multi-instance runs. Verify that this is intentional: `--queue` can be kept as-is (it will simply never trigger in the parallel-instance scenario) without breaking anything.

**Aggregate status output** (2 instances):
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

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/concurrency.py` — `LockManager.acquire` / `LockManager.release` (`instance_id` kwarg)
- `scripts/little_loops/fsm/persistence.py` — `StatePersistence.__init__`, `PersistentExecutor.__init__`, `list_running_loops` deduplication fix
- `scripts/little_loops/cli/loop/_helpers.py` — `_make_instance_id` helper, `run_background` instance scoping
- `scripts/little_loops/cli/loop/__init__.py` — hidden `--instance-id` arg on `run_parser` and `resume_parser`
- `scripts/little_loops/cli/loop/run.py` — generate/consume `instance_id` in `cmd_run`
- `scripts/little_loops/cli/loop/lifecycle.py` — `_find_instances` helper, rewrite `cmd_status`, `cmd_stop`, `cmd_resume`

### Dependent Files (Callers/Importers)
- Any script that constructs `{loop_name}.pid` / `{loop_name}.state.json` paths directly (grep `running_dir / f"{.*}.pid"`)
- `scripts/tests/test_cli_loop_background.py` — asserts on exact `my-loop.pid` / `my-loop.log` paths → update to glob `my-loop*.pid`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**All path construction points (exact line numbers):**
| File | Line | Expression |
|------|------|------------|
| `concurrency.py` | 131 | `running_dir / f"{loop_name}.lock"` (acquire) |
| `concurrency.py` | 149 | `running_dir / f"{loop_name}.lock"` (release) |
| `persistence.py` | 206 | `running_dir / f"{loop_name}.state.json"` |
| `persistence.py` | 207 | `running_dir / f"{loop_name}.events.jsonl"` |
| `_helpers.py` | 250 | `running_dir / f"{loop_name}.pid"` |
| `_helpers.py` | 251 | `running_dir / f"{loop_name}.log"` |
| `run.py` | 203–205 | `running_dir / f"{loop_name}.pid"` (foreground) |
| `lifecycle.py` | 64 | `running_dir / f"{loop_name}.pid"` (status) |
| `lifecycle.py` | 67 | `running_dir / f"{loop_name}.log"` (status) |
| `lifecycle.py` | 147 | `running_dir / f"{loop_name}.pid"` (stop) |
| `lifecycle.py` | 200 | `running_dir / f"{loop_name}.pid"` (resume) |

**Additional dependent file not previously listed:**
- `scripts/little_loops/cli/loop/info.py:52-54` — `cmd_list` calls `list_running_loops(loops_dir)` directly; the displayed status table iterates all returned `LoopState` objects. Once multi-instance state files exist, this will surface duplicate logical-name rows unless `list_running_loops` groups by `loop_name`.

### Similar Patterns
- `list_running_loops` in `persistence.py` — deduplication logic currently uses `loop_name` set; needs `stem`-based tracking

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`list_running_loops` deduplication bug mechanics** (`persistence.py:566`):

The function runs two glob passes. The second pass (PID files, line 590) guards against phantom "starting" entries via:
```python
known_names = {s.loop_name for s in states}   # e.g. {"autodev"}
if pid_file.stem in known_names: continue      # compares "autodev-TIMESTAMP" against "autodev"
```
With instance-ID suffixes, `pid_file.stem` = `"autodev-20260503T122306"` will never equal `"autodev"` in `known_names`, so every instance generates a spurious "starting" state object. The fix: strip the timestamp suffix when building `known_names`, or track already-seen `loop_name` values from state objects so the PID-file pass can skip any logical name already represented.

**Hidden argparse arg precedent** (`__init__.py:122-124`, `__init__.py:229-231`):

`--foreground-internal` is already registered with `help=argparse.SUPPRESS` on both `run_parser` and `resume_parser` — the exact same pattern to use for `--instance-id`. Consumed downstream via `getattr(args, "foreground_internal", False)`.

**`_RUN_FOLDER` regex for parsing timestamp suffixes** (`persistence.py:45`):

An existing regex already parses `{timestamp}-{name}` from archive folder names:
```python
_RUN_FOLDER = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{6})-(.+)$")
```
`_find_instances` can use a similar regex to strip the timestamp suffix from a `stem` and recover the logical `loop_name`.

**`strftime` format inconsistency** (`run.py:293` vs proposed):

`cmd_run` already generates a worktree timestamp using `%Y%m%d-%H%M%S` (hyphen between date and time). The issue proposes `%Y%m%dT%H%M%S` (ISO-style `T`). `archive_run()` at `persistence.py:316` uses `%Y-%m-%dT%H%M%S`. Implementer should pick one format consistently — ISO-T (`%Y%m%dT%H%M%S`) is already in the issue's expected-behavior examples and matches the archive run ID format most closely.

### Tests
- `scripts/tests/test_cli_loop_background.py` — `test_writes_pid_file` (line 154), `test_creates_log_file` (line 174): assert exact `my-loop.pid`/`my-loop.log` paths → update to `glob("my-loop*.pid")`
- `scripts/tests/test_cli_loop_lifecycle.py:563` — `TestCmdResumeBackground.test_plain_foreground_resume_writes_pid_file`: asserts `tmp_path / ".running" / "test-loop.pid"` exists → needs glob or instance-ID-aware lookup
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdStop`, `TestCmdStatusWithPid`: use `_process_alive` mock patterns (both `return_value=True/False` and `side_effect=[True, False]` sequence forms)
- `scripts/tests/test_concurrency.py:75-88` — lock file path assertions in `TestLockManager` → update to instance-ID path

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py` — **MISSING from known tests; must update**. Primary coverage file for `StatePersistence`, `PersistentExecutor`, `list_running_loops`. Breaking path assertions:
  - `TestPersistentExecutor.test_run_creates_state_file` (line 589): asserts `.running/test-loop.state.json` → update to instance-ID-aware glob
  - `TestPersistentExecutor.test_run_creates_events_file` (line 601): asserts `.running/test-loop.events.jsonl` → same
  - `TestAcceptanceCriteria.test_state_saved_after_state_transition` (line 1084): asserts `.running/test-loop.state.json` → same
  - `TestUtilityFunctions.test_list_running_loops_no_duplicate_for_loop_with_both_files` (line 1020): deduplication test uses `pid_file.stem` directly as loop name; with suffix `"autodev-TIMESTAMP"` won't match `known_names = {"autodev"}` → update for the deduplication fix
  - New cases needed for `test_list_running_loops` variants where `pid_file.stem` = `"my-loop-TIMESTAMP"` but `LoopState.loop_name` = `"my-loop"`
- `scripts/tests/test_cli_loop_lifecycle.py` — additional breaking tests beyond those already listed:
  - `TestCmdResumeBackground.test_foreground_internal_registers_pid_cleanup` (line 531): sets up `pid_file = running_dir / "test-loop.pid"` → must use instance-ID path
  - `TestCmdResumeBackground.test_foreground_internal_does_not_overwrite_parent_pid` (line 613): same
  - `TestCmdResume.test_resume_registers_signal_handlers` (line 386): `expected_pid_file = tmp_path / ".running" / "test-loop.pid"` asserted via `mock_register.assert_called_once_with` → must use instance-ID path
  - `TestCmdStop.test_stop_with_pid_sends_sigterm_and_waits` (line 127): `pid_file = running_dir / "test-loop.pid"` → update
  - `TestCmdStop.test_stop_sends_sigkill_if_process_does_not_exit` (line 156): same
  - `TestCmdStop.test_stop_sigkill_handles_race_if_process_exits_between_poll_and_kill` (line 186): same
  - `TestCmdStatusLogFile` (lines 903, 956): `log_file = running_dir / "test-loop.log"` → update
  - `TestCmdStatus.test_no_state_returns_1` (line 25): patches `StatePersistence` directly; after rewrite `cmd_status` calls `_find_instances` — patch target may change

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_execution.py` — **MISSING from known tests; must update**. Integration-level tests that call `main_loop()` and assert on bare-stem file paths:
  - `TestBackgroundMode.test_background_flag_spawns_process` (line ~469): asserts `loops_dir / ".running" / "test-background.pid"` exact path → update to glob `test-background-*.pid`
  - `TestBackgroundMode.test_plain_foreground_run_writes_pid_file` (line ~499): asserts `loops_dir / ".running" / "test-foreground-pid.pid"` exact path → same glob pattern
  - `TestBackgroundMode.test_creates_state_files` (line ~543): asserts `running_dir / "test-state.state.json"` and `running_dir / "test-state.events.jsonl"` → update to instance-ID-aware globs
- `scripts/tests/test_ll_loop_state.py` — **MISSING from known tests; verify**. Three `TestCmdStop` tests write bare `test-loop.state.json` fixtures (lines 89, 132, 167). Legacy backward-compat should preserve these, but must verify `_find_instances` still discovers `test-loop.state.json` (no timestamp suffix) via the legacy fallback glob, and that `cmd_stop` writes status updates back to the same path
- `scripts/tests/test_ll_loop_integration.py` — **MISSING from known tests; update**. `TestMainLoopIntegration.test_list_running_shows_status_info` (line 315) writes bare-stem `loop-a.state.json` / `loop-b.state.json` fixtures and exercises `cmd_list` display. After multi-instance support, `cmd_list` may surface duplicate `loop_name` rows if `list_running_loops` returns multiple entries; verify deduplication in `info.py:cmd_list` or update test fixture to use instance-ID filenames
- `scripts/tests/test_ll_loop_commands.py` — **MISSING from known tests; update**:
  - `TestCmdHistory.events_file` fixture (line 533): writes `running_dir / "test-loop.events.jsonl"` (bare stem); if `cmd_history` reads events via `StatePersistence(instance_id=...)`, the bare-stem file will not be found → pass explicit `instance_id=None` or use legacy path
  - `TestCmdStatusJson.test_status_json_output` (line ~2371), `test_status_json_no_state` (line ~2398), `test_status_human_readable_unchanged` (line ~2431): all patch `little_loops.fsm.persistence.StatePersistence.load_state` directly. After `cmd_status` is rewritten to call `_find_instances` (which constructs `StatePersistence` internally), the patch target changes — update to patch `little_loops.cli.loop.lifecycle._find_instances` or the new internal call site

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — describes `.running/` file layout with bare `{loop_name}.*` filenames; update to reflect `{instance_id}.*` naming and the aggregated status display
- `scripts/little_loops/fsm/persistence.py` — module docstring (lines 9–18) shows `{loop_name}.*` file layout (e.g. `fix-types.state.json`); stale after change. `StatePersistence` class docstring (line 193): "Files are stored in `.loops/.running/<loop_name>.*`" — update to reflect `<instance_id>.*` naming
- `docs/reference/API.md` — already in related docs, but specific sections need updating: `StatePersistence.__init__` signature block, `PersistentExecutor.__init__` signature block (add `instance_id` kwarg), `LockManager` methods table (`acquire`/`release`), and the `.running/` file structure diagram under `StatePersistence` section (shows `my-loop.state.json` / `my-loop.events.jsonl`)
- `skills/cleanup-loops/SKILL.md` — Step 6 uses `rm -f ".loops/.running/<loop_name>.pid"` and Step 7 uses `tail -20 ".loops/.running/<loop_name>.events.jsonl"` — both hardcode bare loop-name paths; after this change stale PID/events files will be named `{instance_id}.*`, so cleanup will silently fail. Fix: glob `{loop_name}-*.pid` or delegate cleanup to `ll-loop stop`
- `skills/rename-loop/SKILL.md` — Step 4 guard: `test -f ".loops/.running/<old_name>.pid"` always returns false when a loop is running with instance-ID suffix, silently allowing rename of a live loop. Fix: glob `{old_name}*.pid` or `{old_name}-*.pid`
- `skills/analyze-loop/SKILL.md` — Step 1 calls `ll-loop list --running --json` and iterates by `loop_name` for user selection. With multiple instances of the same `loop_name`, the selection list presents duplicate entries with no disambiguator. Needs instance-ID awareness in the selection step
- `skills/assess-loop/SKILL.md` — same `ll-loop list --running --json` ambiguity in Step 1

_Wiring pass 2 added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `/ll:cleanup-loops` description (line ~661) mentions "removes orphaned .pid files (stale-interrupted)" without naming the new `{instance_id}.pid` convention; update to reference glob-based cleanup (`{loop_name}-*.pid`)

### Configuration
- N/A

## Implementation Steps

1. Add `_make_instance_id(loop_name: str) -> str` to `_helpers.py`; update `run_background` (line 232) to generate `instance_id`, embed it in the `--foreground-internal` re-exec command (line 264 pattern), and use it for `pid_file` (line 250) and `log_file` (line 251) paths
2. Add hidden `--instance-id` arg (model after `--foreground-internal` at `__init__.py:122-124`) to `run_parser` (line 96) and `resume_parser` (line 220) in `__init__.py`
3. Update `cmd_run` in `run.py:87` to generate `instance_id` (when not foreground-internal) or read it from `args.instance_id`; route through `LockManager.acquire(fsm.name, scope, instance_id=instance_id)` (line 225) and `PersistentExecutor.__init__` (line 332); update PID file path (line 203-205)
4. Add `instance_id: str | None = None` kwarg to `LockManager.acquire` (line 98) and `release` (line 143) in `concurrency.py`; replace `f"{loop_name}.lock"` at lines 131, 149 with `f"{instance_id or loop_name}.lock"`
5. Add `instance_id: str | None = None` kwarg to `StatePersistence.__init__` (line 196) and `PersistentExecutor.__init__` (line 346) in `persistence.py`; replace path stems at lines 206-207 with `instance_id or loop_name`; at line 366 forward `instance_id` to the internally-constructed `StatePersistence`; fix `list_running_loops` deduplication at line 590 (strip timestamp suffix before comparing against `known_names`)
6. Add `_find_instances(loop_name: str, running_dir: Path) -> list[tuple[str, LoopState]]` to `lifecycle.py` (glob `{loop_name}-*.state.json` plus `{loop_name}.state.json` for legacy); rewrite `cmd_status` (line 46), `cmd_stop` (line 123), `cmd_resume` (line 180) to call `_find_instances` and iterate all matches. **Multi-instance `cmd_resume` behavior**: when `_find_instances` returns 2+ matches, print an error listing all running instance IDs and exit non-zero (since `--select-instance` is out of scope per Scope Boundaries; single-instance resume is unchanged)
7. Update `info.py:52-54` (`cmd_list`) to handle multiple `LoopState` objects with the same `loop_name` (group or deduplicate the display table)
8. Update `atexit._cleanup_pid` closures in `run.py:211-214` and `lifecycle.py:206-209` — these are closed over `pid_file` which must now be the instance-ID-scoped path, not the bare loop-name path. Also update `foreground_pid_file` at `run.py:206` and `lifecycle.py:201` (same Path binding passed to `register_loop_signal_handlers(executor, pid_file=foreground_pid_file)` at `run.py:335` and `lifecycle.py:265`) — the signal handler unlinks `pid_file` on forced exit and must reference the same instance-ID-scoped path
9. Update `test_cli_loop_background.py` path assertions from `my-loop.pid` / `my-loop.log` to `glob("my-loop*.pid")` / `glob("my-loop*.log")` (lines 154, 174)
10. Update `test_cli_loop_lifecycle.py:563` (`test_plain_foreground_resume_writes_pid_file`) and `test_concurrency.py:75-88` lock path assertions to use instance-ID-aware lookup
11. Run full test suite (`python -m pytest scripts/tests/`); smoke test with two concurrent `ll-loop run` invocations

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

12. Update `scripts/tests/test_fsm_persistence.py` — adapt `TestPersistentExecutor.test_run_creates_state_file` (line 589), `test_run_creates_events_file` (line 601), and `TestAcceptanceCriteria.test_state_saved_after_state_transition` (line 1084) from hard-coded `test-loop.*` path assertions to instance-ID-aware lookups (glob or pass explicit `instance_id` to constructors). Add new `TestUtilityFunctions` cases for `list_running_loops` deduplication where `pid_file.stem` = `"my-loop-TIMESTAMP"` but returned `LoopState.loop_name` = `"my-loop"`
13. Update `scripts/tests/test_cli_loop_lifecycle.py` additional tests — `TestCmdResumeBackground.test_foreground_internal_registers_pid_cleanup` (line 531), `test_foreground_internal_does_not_overwrite_parent_pid` (line 613), `TestCmdResume.test_resume_registers_signal_handlers` (line 386), `TestCmdStop` tests at lines 127/156/186, `TestCmdStatusLogFile` at lines 903/956 — update from bare `test-loop.pid`/`test-loop.log` path construction to instance-ID-aware paths
14. Update `persistence.py` docstrings — module-level docstring (lines 9–18) and `StatePersistence` class docstring (line 193) to reflect `{instance_id}.*` file naming instead of `{loop_name}.*`
15. Update `docs/reference/API.md` — `StatePersistence.__init__` and `PersistentExecutor.__init__` signature blocks (add `instance_id: str | None = None` kwarg), `LockManager.acquire`/`release` methods table (same), and the `.running/` directory layout diagram under `StatePersistence`
16. Update `skills/cleanup-loops/SKILL.md` — Steps 6 and 7: replace `rm -f ".loops/.running/<loop_name>.pid"` and `tail -20 ".loops/.running/<loop_name>.events.jsonl"` with glob-based paths (`{loop_name}-*.pid`, `{loop_name}-*.events.jsonl`) or delegate to `ll-loop stop`
17. Update `skills/rename-loop/SKILL.md` — Step 4: replace `test -f ".loops/.running/<old_name>.pid"` guard with `ls .loops/.running/<old_name>*.pid 2>/dev/null | head -1` or equivalent glob to correctly detect running instances
18. Update `skills/analyze-loop/SKILL.md` and `skills/assess-loop/SKILL.md` — Step 1: handle duplicate `loop_name` entries from `ll-loop list --running --json` by using `instance_id` (or a combined `loop_name:instance_id` key) for user selection disambiguation

### Wiring Phase 2 (added by `/ll:wire-issue`)

_Additional touchpoints found in second wiring pass:_

19. Update `scripts/tests/test_ll_loop_execution.py` — `TestBackgroundMode` tests at lines ~469, ~499, ~543: update bare-stem path assertions (`test-background.pid`, `test-foreground-pid.pid`, `test-state.state.json`, `test-state.events.jsonl`) to use instance-ID-aware globs (e.g., `list(running_dir.glob("test-background-*.pid"))[0]`)
20. Verify `scripts/tests/test_ll_loop_state.py` — `TestCmdStop` at lines 89, 132, 167: confirm that `_find_instances` still discovers legacy bare-stem `test-loop.state.json` files (no timestamp) and that `cmd_stop` writes status back to the same path; update fixtures to pass explicit `instance_id=None` if needed
21. Update `scripts/tests/test_ll_loop_integration.py` — `test_list_running_shows_status_info` (line 315): update bare-stem state file fixtures to use instance-ID names, or verify `cmd_list` deduplication handles legacy names cleanly without duplicate rows
22. Update `scripts/tests/test_ll_loop_commands.py` — `TestCmdHistory.events_file` fixture (line 533): write `test-loop.events.jsonl` as legacy bare-stem file and confirm `cmd_history` reads it; update `TestCmdStatusJson` tests (lines ~2371, ~2398, ~2431) to patch `little_loops.cli.loop.lifecycle._find_instances` instead of `StatePersistence.load_state`
23. Update `docs/reference/COMMANDS.md` — `/ll:cleanup-loops` description: replace `<loop_name>.pid` references with glob pattern `{loop_name}-*.pid` to reflect instance-scoped naming

## Impact

- **Priority**: P2 — blocks parallel automation; silent collision is a hard failure mode for concurrent use
- **Effort**: Medium — 6 files, well-defined seams, all changes are additive kwargs with backward-compat defaults
- **Risk**: Low — all new kwargs default to `None` which falls back to existing behavior; legacy files work unchanged
- **Breaking Change**: No

## Scope Boundaries

- Does not change `LoopState.loop_name` (stays logical name, no schema migration needed).
- Does not add a `--select-instance` flag for targeting a specific instance by ID (future work).
- Does not add instance-level log streaming UI.

## API/Interface

```python
# New helper (cli/loop/_helpers.py)
def _make_instance_id(loop_name: str) -> str: ...

# Updated signatures (all backward-compatible via default None)
LockManager.acquire(loop_name, scope, *, instance_id=None)
LockManager.release(loop_name, *, instance_id=None)
StatePersistence(loop_name, loops_dir, instance_id=None)
PersistentExecutor(fsm, ..., instance_id=None)

# New internal helper (lifecycle.py)
def _find_instances(loop_name: str, running_dir: Path) -> list[tuple[str, LoopState]]: ...
```

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | architecture | FSM loop runtime file layout |
| [docs/reference/API.md](../../docs/reference/API.md) | architecture | `StatePersistence`, `PersistentExecutor`, `LockManager` API |

## Labels

`enhancement`, `ll-loop`, `concurrency`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-03_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- **Large file surface (22+ files)**: Core changes are 7 files but wiring passes added 8 test files + 7 docs/skill files. Each catalogued with specific line numbers — the risk is missing an update in one of the 8 test files (all have exact path assertions that become stale). Mitigation: work step-by-step through the numbered implementation list, running `pytest` after each subsystem.
- **Broad test assertion surface**: 8 test files contain `{loop_name}.pid` / `{loop_name}.state.json` exact-path assertions. With 22+ test cases spread across `test_fsm_persistence.py`, `test_cli_loop_lifecycle.py`, `test_ll_loop_execution.py`, `test_ll_loop_commands.py`, and others, a partial update will produce hard-to-diagnose path-not-found failures. Mitigation: run the full test suite after implementing each numbered step rather than at the end.
- **Strftime format (minor)**: Issue flags `%Y%m%d-%H%M%S` vs `%Y%m%dT%H%M%S` inconsistency and recommends ISO-T. No open decision, but `_find_instances` regex must match the exact chosen format consistently.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-03
- **Reason**: Issue too large for single session (score: 9/11, Very Large)

### Decomposed Into
- ENH-1354: Multi-Instance Loop — instance_id Generation and File Path Scoping
- ENH-1355: Multi-Instance Loop — Aggregated CLI (status/stop/resume/list) + Docs & Skills

---

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-03T19:26:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e26d0d3-b923-4ec1-86ac-7959fadea8f7.jsonl`
- `/ll:issue-size-review` - 2026-05-03T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e26d0d3-b923-4ec1-86ac-7959fadea8f7.jsonl`
- `/ll:confidence-check` - 2026-05-03T20:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1710d27d-e7e6-41eb-bdb2-221618751457.jsonl`
- `/ll:wire-issue` - 2026-05-03T19:18:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2a9ee3ef-3cc6-4159-9524-6a2a2ffaf0b5.jsonl`
- `/ll:refine-issue` - 2026-05-03T19:11:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6df60d0-1c78-4851-b324-323ef58d2758.jsonl`
- `/ll:wire-issue` - 2026-05-03T18:02:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/075b3abf-eb8a-4b05-91fe-ab01841deab1.jsonl`
- `/ll:refine-issue` - 2026-05-03T17:54:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c82c3b7-5d03-4f7e-ad8c-05324d8acd14.jsonl`
- `/ll:format-issue` - 2026-05-03T17:47:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c397985-bbb0-4895-8d56-7d1468247afa.jsonl`

- `/ll:capture-issue` - 2026-05-03T17:41:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/483c54db-a329-4b0d-92ed-ebfb1be65160.jsonl`

---

**Open** | Created: 2026-05-03 | Priority: P2
