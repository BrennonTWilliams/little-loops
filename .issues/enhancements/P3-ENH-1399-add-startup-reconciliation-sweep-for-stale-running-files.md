---
id: ENH-1399
type: ENH
priority: P3
status: open
captured_at: '2026-05-09T20:55:45Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
decision_needed: false
confidence_score: 98
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1399: Add Startup Reconciliation Sweep for Stale `.running/` Files

## Summary

On loop startup, scan `.loops/.running/` for state files left behind by previously interrupted or crashed loop processes and archive them to `.loops/.history/`. Currently there is no recovery path for abnormal exits, so stale files accumulate indefinitely.

## Current Behavior

When a loop process exits abnormally (SIGTERM, process kill, crash), its `.state.json` file in `.loops/.running/` is never archived. `PersistentExecutor.run()` in `scripts/little_loops/fsm/persistence.py` calls `archive_run()` at line 513 only on clean exits. There is no recovery path for interrupted runs, so `.running/` accumulates files without bound.

A real-world instance had 64 files in `.loops/.running/` with only 1 actually active.

## Expected Behavior

When little-loops starts a new loop run, it should scan `.loops/.running/` for stale state files — those belonging to processes that are no longer alive — and archive them to `.loops/.history/` before beginning execution. After the sweep, `.running/` should only contain files for genuinely active runs.

## Motivation

The accumulation problem is silent and unbounded: every interrupted run adds a file that never gets cleaned up. This misleads consumers that read from `.running/`:
- loop-viz's `handleGetRunning` endpoint returned 64 entries when only 1 was active
- SSE seeding pushed all 64 stale entries into client state
- The problem gets worse over time with no self-healing mechanism

The fix-at-source here is preferable to defensive filtering in consumers because it corrects the root cause rather than papering over it.

## Proposed Solution

Add a startup reconciliation function to `PersistentExecutor` or the `ll-loop` CLI entry point. At the start of each loop run, before `clear_all()`, call a sweep that:

1. Lists all `.state.json` files in `.loops/.running/`
2. For each file, loads the state and checks if it belongs to a live process
3. Archives any file whose process is no longer alive (using PID tracking or process existence check)

**Option A — PID-based (preferred)**: Store the current PID in the state file on startup. On reconciliation sweep, check `os.kill(pid, 0)` for each file's PID. If the process is dead, call `archive_run()`.

**Option B — Status-based (simpler)**: Archive any `.state.json` file where `status` is already a terminal value (`completed`, `failed`, `interrupted`, `timed_out`) — these were written but never moved. This is safe to do unconditionally since terminal-status files in `.running/` are definitionally stale.
> **Selected:** Option B — Status-based — Safest, simplest predicate with the highest scoring profile (12/12); real `.running/` observation confirms 24/29 stale files have terminal status; implementation steps already include a PID-check extension for the `status="running"` edge case, making the full implementation the combined approach anchored in Option B's safety guarantee.

A combined approach handles both cases: archive terminal-status files immediately, and archive `status == "running"` files only if their PID is dead.

```python
def _reconcile_stale_runs(loops_dir: Path) -> None:
    """Archive state files in .running/ that belong to dead processes."""
    running_dir = loops_dir / "running"
    if not running_dir.exists():
        return
    for state_file in running_dir.glob("*.state.json"):
        state = _load_state_safe(state_file)
        if state is None:
            continue
        terminal_statuses = {"completed", "failed", "interrupted", "timed_out"}
        is_terminal = state.status in terminal_statuses
        is_dead_pid = state.pid and not _is_pid_alive(state.pid)
        if is_terminal or is_dead_pid:
            _archive_orphan(state_file, loops_dir)
```

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-09.

**Selected**: Option B — Status-based

**Reasoning**: Option B scores 12/12 vs Option A's 10/12. Terminal-status files in `.running/` are definitionally stale by invariant — archiving them unconditionally carries zero risk of false-positive removal. Real-world evidence from the observed `.running/` directory confirms 24 of 29 stale files carry terminal statuses (`completed`, `interrupted`, `timed_out`), handled entirely by Option B without PID infrastructure. The implementation steps already describe adding the `.pid`-file PID check for `status="running"` files as step 2's fallback branch, making the full implementation the combined approach — but the core decision principle is Option B's unconditional terminal-status archival, which is the simplest, most testable, and safest foundation.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — PID-based | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B — Status-based | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Option A**: `_process_alive` and sibling `.pid` files are fully established (reuse score 3/3), but the missing-PID fallback branch and EPERM edge cases reduce simplicity and risk scores. `LockManager.find_conflict()` is the exact structural template.
- **Option B**: `resume()` at `persistence.py:529` already uses the same `{"completed","failed","interrupted","timed_out"}` terminal set; `StatePersistence.clear_all()` handles copy+delete atomically; `TestArchiveRun` provides the exact test fixture pattern; the `awaiting_continuation` gap is minor and handled by the PID-check extension in step 2.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`_process_alive()` already exists — reuse it:**
- `scripts/little_loops/fsm/concurrency.py` defines `_process_alive(pid: int) -> bool` using `os.kill(pid, 0)` with `errno.ESRCH` handling; it is already imported by `persistence.py` and `lifecycle.py`. Implement `_is_pid_alive` as an alias or just call `_process_alive` directly — no new helper needed.

**PIDs tracked via `.pid` files, not `LoopState` fields — simplifies Option A:**
- `cmd_run()` writes `{instance_id}.pid` containing `os.getpid()` to `.running/` on every startup, with an `atexit` handler that deletes it on normal exit. The reconciliation sweep can read `{state_file.stem}.pid` (sibling file) to get the PID without modifying `LoopState` schema at all. If no `.pid` file exists (old runs or background cases), fall back to Option B (status check).
- Example: `state_file = running_dir / "myloop-20260503T122306.state.json"` → check `running_dir / "myloop-20260503T122306.pid"` for the PID.

**`RUNNING_DIR` and `HISTORY_DIR` constants are in `persistence.py`:**
- Use `loops_dir / RUNNING_DIR` (not `loops_dir / ".running"`) for consistency with the rest of the codebase.

**`archive_run()` copies but does NOT delete source files — use `clear_all()` instead:**
- To archive and remove a stale file, call `persistence.clear_all()` on a temporary `StatePersistence` instance for that `instance_id`, or implement `_archive_orphan()` as: `shutil.copy2` the files, then `unlink(missing_ok=True)` each.

**Preferred integration point: `cmd_run()` in `run.py`, not `PersistentExecutor`:**
- `PersistentExecutor` only knows one `instance_id` at a time and calls `clear_all()` for that instance only. A global sweep requires access to all `*.state.json` files — only code with the `loops_dir` can do this. `cmd_run()` at line ~88 already has `loops_dir`; the sweep fits naturally after `running_dir.mkdir()` and before `LockManager.acquire()`, mirroring the `find_conflict()` stale-lock cleanup which already fires at `LockManager.acquire()` time.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — add `_reconcile_stale_runs()` utility and call it from `cmd_run()` startup sequence; `LoopState` dataclass is also defined here (no separate `state.py`)
- `scripts/little_loops/cli/loop/run.py` — **preferred integration point**: call `_reconcile_stale_runs(loops_dir)` at startup in `cmd_run()`, after the `running_dir.mkdir()` call and before `PersistentExecutor` is instantiated (follows the `LockManager.acquire()` → `find_conflict()` stale-lock cleanup pattern)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/concurrency.py` — contains `_process_alive(pid: int) -> bool` using `os.kill(pid, 0)` / `errno.ESRCH`; already imported in `persistence.py` and `lifecycle.py`; reuse instead of implementing `_is_pid_alive()`
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor` (called by `PersistentExecutor`); no changes needed
- `scripts/little_loops/cli/loop/lifecycle.py` — `_find_instances()` and `cmd_stop()` scan `.running/` with similar patterns; review for consistency; **key-collision risk**: `_status_single()` and `cmd_status()` merge a separately-read `pid` key (from `.pid` file) into `state.to_dict()` — if `pid` is added to `to_dict()`, the merged dict will have a duplicate `pid` key; the `.pid`-file value should win, so ensure `to_dict()` emits `pid` only when non-None and that lifecycle's merge uses `state.to_dict() | {"pid": file_pid, ...}` ordering (later key wins) or skips the merge if `to_dict()` already emits it
- `scripts/little_loops/cli/loop/_helpers.py` — `_make_instance_id()` generates `{loop_name}-{YYYYMMDDTHHMMSS}`; file naming convention: `{instance_id}.state.json`, `{instance_id}.pid`, `{instance_id}.lock`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — calls `list_running_loops()` and `LoopState.from_dict()` directly in `cmd_list()` and `_list_archived_runs()`; if `LoopState.from_dict()` changes to add `pid`, the function works via `.get()` with no code change, but `cmd_list --running --json` output will gain a `pid` field — verify against expected output
- `scripts/little_loops/transport.py` — `_make_seed_callback()` calls `state.to_dict()` and emits the result as a `state_change` SSE event to loop-viz and other clients; if `pid` is added to `to_dict()`, the seed payload gains a `pid` field — intended per the issue's motivation, but should be noted as a downstream schema addition

### Similar Patterns
- `persistence.py:StatePersistence.archive_run()` — existing archival implementation to reuse; copies `.state.json` + `.events.jsonl` to `.loops/.history/{run_id}-{loop_name}/`
- `persistence.py:StatePersistence.clear_all()` — existing startup cleanup pattern (archive + delete); per-instance only, not a global sweep
- `concurrency.py:LockManager.find_conflict()` — **closest analog**: iterates `.lock` files, calls `_process_alive(lock.pid)`, unlinks stale locks with `lock_file.unlink(missing_ok=True)` — exact same pattern needed for state files
- `parallel/orchestrator.py` — `_cleanup_orphaned_worktrees()` — startup sweep pattern for orphaned git worktrees using `os.kill(pid, 0)`

### Tests
- `scripts/tests/test_fsm_persistence.py` — primary test file (1950+ lines); add tests for reconciliation here in a new `TestReconcileStaleRuns` class; existing `TestUtilityFunctions` and `TestArchiveRun` show state file fixture patterns
- `scripts/tests/test_concurrency.py` — EPERM/ESRCH mock patterns for `os.kill` (`patch("os.kill", side_effect=OSError(errno.EPERM, ...))`)
- Test cases needed: terminal-status file archived, dead-PID file archived, live-PID file left alone, missing `.pid` file with `status="running"` left alone, empty `.running/` dir handled safely

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_queue.py` — `TestQueueRetryOnRace` (3 tests) calls `cmd_run()` with `dry_run=False` and patches `LockManager` but NOT `_reconcile_stale_runs`; the sweep will run against a real `tmp_path` directory; since the dir is empty it's a no-op and safe, but if the sweep calls `_process_alive` on real PIDs from stale data, it could cause flakiness — **add a `patch("little_loops.cli.loop.run._reconcile_stale_runs")` stub** to these tests to insulate them [Agent 3 finding, at-risk]
- `scripts/tests/test_cli_loop_worktree.py` — `TestCmdRunWorktree.test_worktree_atexit_registration()` asserts `len(registered) >= 2` after patching `atexit.register`; if `_reconcile_stale_runs` registers any cleanup handlers, the count may mismatch — verify or add a compensating patch [Agent 3 finding, at-risk]
- `scripts/tests/test_ll_loop_execution.py` — `TestForegroundExecution` runs real `cmd_run()` end-to-end without mocking the sweep; safe because it runs against clean `tmp_path` (empty `.running/`), but any startup-sweep bug will surface here first — these are the integration-level canary tests for this change [Agent 3 finding]

### Documentation
- N/A — no user-facing docs reference this behavior

_Wiring pass added by `/ll:wire-issue`:_
- `skills/cleanup-loops/SKILL.md` — Step 1 field table lists fields returned by `ll-loop list --running --json`; if `pid` is added to `LoopState.to_dict()`, the Step 1 output gains an undocumented `pid` field; minor — the skill still functions, but the table will be incomplete [Agent 2 finding]

### Configuration
- N/A — no config changes needed

## API/Interface

`LoopState` gains a new optional field (backward-compatible — existing `.state.json` files without `pid` are unaffected):

```python
@dataclass
class LoopState:
    # ... existing fields ...
    pid: int | None = None  # populated on startup; used by reconciliation sweep
```

Internal helpers added to `persistence.py` (not public API, but listed for clarity):

```python
def _reconcile_stale_runs(loops_dir: Path) -> None: ...
def _is_pid_alive(pid: int) -> bool: ...
def _archive_orphan(state_file: Path, loops_dir: Path) -> None: ...
```

Consumers reading `.state.json` files (e.g., loop-viz) should treat `pid` as an optional field and not require its presence.

## Implementation Steps

1. Add `_reconcile_stale_runs(loops_dir: Path) -> int` to `persistence.py` (returns count of archived files for logging); import `_process_alive` from `concurrency.py` — it already exists, no new helper needed
2. In `_reconcile_stale_runs()`: use `loops_dir / RUNNING_DIR` glob `*.state.json`; for each file load state with `LoopState.from_dict()`; archive terminal-status files unconditionally; for `status="running"` files, check sibling `{stem}.pid` file — if it exists, read PID and call `_process_alive(pid)`; archive if dead or PID file absent; use `unlink(missing_ok=True)` after archiving (mirroring `concurrency.py:LockManager.find_conflict()` pattern)
3. Call `_reconcile_stale_runs(loops_dir)` in `cmd_run()` in `run.py` — after `running_dir.mkdir(parents=True, exist_ok=True)` and **before** `LockManager.acquire()` (same startup position as lock stale-file cleanup)
4. Optionally add `pid: int | None = None` to `LoopState` in `persistence.py` and populate it in `cmd_run()` after writing the `.pid` file — makes future reconciliation more reliable for cases where `.pid` is cleaned but state remains; backward-compatible (field defaults to `None`)
5. Add `TestReconcileStaleRuns` class in `scripts/tests/test_fsm_persistence.py`; mock `_process_alive` via `pytest.MonkeyPatch.context()` patching `little_loops.fsm.persistence._process_alive`; test cases: terminal-status archived, dead-PID archived, live-PID left alone, missing `.pid` with `status="running"` left alone, empty `.running/` no-op
6. Verify end-to-end: send SIGKILL to a running loop, start a new loop, confirm `.running/` shrinks by 1

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `LoopState.to_dict()` in `persistence.py` — add conditional `pid` emission (`if self.pid is not None: result["pid"] = self.pid`); update `LoopState.from_dict()` to add `pid=data.get("pid")`; both changes are required if step 4 (adding `pid` field) is included
8. Audit `lifecycle.py:_status_single()` — the method merges `state.to_dict()` with a separately-read `pid` from the `.pid` file; if `to_dict()` now emits `pid`, ensure the merge order means the `.pid`-file value wins (use `{"pid": file_pid, ...} | state.to_dict()` so the file value overwrites) or conditionally skip the `to_dict()` pid field when a `.pid` file is present
9. Add `patch("little_loops.cli.loop.run._reconcile_stale_runs")` stub to `TestQueueRetryOnRace` tests in `test_cli_loop_queue.py` — insulates the queue-retry tests from sweep side effects
10. Verify `test_cli_loop_worktree.py:TestCmdRunWorktree.test_worktree_atexit_registration()` — check that the `atexit.register` count assertion still holds after `_reconcile_stale_runs` is added; adjust the assertion or add a patch if the sweep registers any cleanup handlers

## Impact

- **Priority**: P3 - Correctness issue with real-world impact; not blocking but gets worse over time
- **Effort**: Small - Localized to `persistence.py`; reuses existing `archive_run()` logic
- **Risk**: Low - Sweep only touches files for terminated/dead processes; concurrent live runs are unaffected
- **Breaking Change**: No

## Success Metrics

- After an interrupted run, the stale file is archived on the next `ll-loop run` invocation
- `.loops/.running/` contains only files for genuinely active processes
- 64-file accumulation scenario is self-healing within one run cycle

## Scope Boundaries

- Out of scope: a standalone `ll-loop clean` CLI subcommand (could be a follow-on)
- Out of scope: consumer-side filtering in loop-viz (separate issue in that repo)
- Out of scope: tracking PIDs for concurrent loop runs (single-process case is sufficient)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | FSM loop execution and persistence architecture |

## Labels

`enhancement`, `fsm`, `persistence`, `captured`

---

## Session Log
- `/ll:ready-issue` - 2026-05-09T21:25:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a7b1665c-5a8e-4b4b-aa58-2cc6cb788d0d.jsonl`
- `/ll:decide-issue` - 2026-05-09T21:21:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad8d078c-4725-48f5-8f8d-ed3affa348bb.jsonl`
- `/ll:wire-issue` - 2026-05-09T21:14:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32deefa2-352e-4fa9-a9df-ce9aad495a16.jsonl`
- `/ll:refine-issue` - 2026-05-09T21:05:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cdd7083-bfd0-4397-96f9-480af7252983.jsonl`
- `/ll:format-issue` - 2026-05-09T20:59:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be5fe9b0-f172-4370-b9f7-304173c44475.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:55:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7db205e9-01e7-4bfd-9c7c-5fce9c641172.jsonl`
- `/ll:confidence-check` - 2026-05-09T21:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49c941b9-f63f-4121-94e3-efd1fcee3927.jsonl`
- `/ll:confidence-check` - 2026-05-09T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afb5da80-f902-4378-938f-5726e515f0b6.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P3
