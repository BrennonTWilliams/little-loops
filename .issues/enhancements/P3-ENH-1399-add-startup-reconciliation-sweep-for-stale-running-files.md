---
id: ENH-1399
type: ENH
priority: P3
status: open
captured_at: "2026-05-09T20:55:45Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
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

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — add `_reconcile_stale_runs()` utility, call from `PersistentExecutor.__init__` or `run()`
- `scripts/little_loops/fsm/state.py` (or wherever `LoopState` is defined) — add optional `pid: int | None` field to state schema

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — entry point for `ll-loop run`; alternative location for reconciliation call
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor` (called by `PersistentExecutor`)

### Similar Patterns
- `persistence.py:archive_run()` — existing archival implementation to reuse
- `persistence.py:clear_all()` — existing startup cleanup pattern to extend

### Tests
- `scripts/tests/test_persistence.py` (if exists) — add tests for reconciliation of terminal-status and dead-PID files
- Add test: stale `.state.json` with terminal status is archived on next run startup

### Documentation
- N/A — no user-facing docs reference this behavior

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

1. Add optional `pid: int | None` to `LoopState` dataclass and persist it on startup
2. Implement `_reconcile_stale_runs(loops_dir)` utility in `persistence.py`
3. Call reconciliation at the start of `PersistentExecutor.run()` (before `clear_all()`)
4. Add helper `_is_pid_alive(pid)` using `os.kill(pid, 0)` with appropriate error handling
5. Write tests covering: terminal-status stale file archived, dead-PID file archived, live-PID file left alone, empty `.running/` dir handled safely
6. Verify with a real interrupted run that `.running/` is cleaned on next startup

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
- `/ll:format-issue` - 2026-05-09T20:59:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be5fe9b0-f172-4370-b9f7-304173c44475.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:55:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7db205e9-01e7-4bfd-9c7c-5fce9c641172.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P3
