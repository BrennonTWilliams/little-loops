---
id: ENH-1351
type: ENH
priority: P2
status: open
captured_at: "2026-05-03T17:41:57Z"
discovered_date: "2026-05-03"
discovered_by: capture-issue
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

### Similar Patterns
- `list_running_loops` in `persistence.py` — deduplication logic currently uses `loop_name` set; needs `stem`-based tracking

### Tests
- `scripts/tests/test_cli_loop_background.py` — `test_writes_pid_file`, `test_creates_log_file`
- `scripts/tests/test_cli_loop_lifecycle.py` — status/stop tests may assert on exact file names
- `scripts/tests/test_concurrency.py` — lock file path assertions

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `_make_instance_id` to `_helpers.py`; update `run_background` to generate and pass `instance_id`
2. Add hidden `--instance-id` arg to `run_parser` / `resume_parser` in `__init__.py`
3. Update `run.py` `cmd_run` to generate or consume `instance_id` and route it to `LockManager` and `PersistentExecutor`
4. Add `instance_id` kwarg to `LockManager.acquire` / `release` in `concurrency.py`
5. Add `instance_id` kwarg to `StatePersistence` and `PersistentExecutor` in `persistence.py`; fix `list_running_loops` deduplication
6. Add `_find_instances` to `lifecycle.py`; rewrite `cmd_status`, `cmd_stop`, `cmd_resume` for aggregate multi-instance handling
7. Update `test_cli_loop_background.py` path assertions to glob pattern
8. Run full test suite; smoke test with two concurrent `ll-loop run` invocations

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

## Session Log

- `/ll:capture-issue` - 2026-05-03T17:41:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/483c54db-a329-4b0d-92ed-ebfb1be65160.jsonl`

---

**Open** | Created: 2026-05-03 | Priority: P2
