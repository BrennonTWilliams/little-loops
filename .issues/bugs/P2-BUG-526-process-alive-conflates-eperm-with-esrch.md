---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# BUG-526: `_process_alive` Conflates EPERM with ESRCH — Treats Running Privileged Process as Dead

## Summary

`_process_alive` catches `OSError` broadly, returning `False` for both `ESRCH` (process does not exist) and `EPERM` (process exists but current user lacks permission to signal it). If a lock file was written by a loop running as a different user, `_process_alive` returns `False`, triggering stale-lock cleanup that deletes the lock file and allows a new loop to acquire the scope — overriding an actually-running process.

## Location

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Line(s)**: 252–258 (at scan commit: 47c81c8)
- **Anchor**: `in method LockManager._process_alive()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/concurrency.py#L252-L258)
- **Code**:
```python
def _process_alive(self, pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:      # catches BOTH ESRCH and EPERM
        return False
```

The identical logic is duplicated at `scripts/little_loops/cli/loop/lifecycle.py:28–34`.

## Current Behavior

`os.kill(pid, 0)` raises `OSError` with `errno.EPERM` when the target process exists but the calling user lacks permission to signal it. The bare `except OSError` returns `False`, making the process appear dead. The stale-lock path at `concurrency.py:155–157` then deletes the lock file, and the new invocation proceeds.

## Expected Behavior

`EPERM` (errno 1) means the process is alive but not owned by the current user. `_process_alive` should return `True` in this case (the lock is valid). Only `ESRCH` (errno 3 — no such process) should return `False`.

## Motivation

In multi-user or privileged environments (systemd services, sudo-escalated loops, CI agents running as different users), this causes the concurrency guard to be silently bypassed. Two instances run simultaneously, potentially corrupting shared state.

## Steps to Reproduce

1. Start `ll-loop run my-loop --background` as user A
2. Run `ll-loop run my-loop` as user B (different UID)
3. Observe: user B sees no conflict — it deletes A's lock as "stale" and proceeds

## Actual Behavior

User B deletes user A's lock file and starts the loop, violating scope exclusivity.

## Root Cause

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Anchor**: `in method LockManager._process_alive()`
- **Cause**: `except OSError` is too broad; `errno.EPERM` and `errno.ESRCH` require different responses

## Proposed Solution

```python
import errno

def _process_alive(self, pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        if e.errno == errno.ESRCH:
            return False   # process does not exist
        # EPERM or other: process exists, no permission — treat as alive
        return True
```

Apply the same fix to the duplicate in `lifecycle.py` (or extract to a shared utility — see ENH-537).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/concurrency.py` — `LockManager._process_alive()`
- `scripts/little_loops/cli/loop/lifecycle.py` — module-level `_process_alive()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/concurrency.py` — `cleanup_stale()` calls `_process_alive()`
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_stop()` calls module-level version

### Similar Patterns
- N/A — no other `os.kill(pid, 0)` calls in codebase

### Tests
- `scripts/tests/test_ll_loop_execution.py` — mock `os.kill` to raise `OSError(errno.EPERM, ...)` and verify lock not deleted

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Update both `_process_alive` implementations to distinguish `ESRCH` from `EPERM`
2. Extract to a shared utility if ENH-537 is also being addressed (reduces change surface)
3. Add tests mocking `EPERM` and `ESRCH` errno values

## Impact

- **Priority**: P2 — Silent correctness failure in multi-user deployments; wrong lock deletion
- **Effort**: Small — 3-line fix in two locations
- **Risk**: Low — Change is purely in error-code dispatch; no behavioral change for single-user case
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Concurrency and locking model (line 1288), stale-lock cleanup behavior |
| `docs/guides/LOOPS_GUIDE.md` | Scope-based concurrency (line 295) |

## Labels

`bug`, `ll-loop`, `concurrency`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted `test_cli_loop_background.py:220` (TestCmdStopWithPid) as os.kill mock pattern

---

**Open** | Created: 2026-03-03 | Priority: P2
