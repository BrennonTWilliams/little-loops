---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# BUG-525: TOCTOU Race Condition in `LockManager.acquire` — Two Loops Can Acquire Same Scope

## Summary

`LockManager.acquire` checks for scope conflicts before writing its lock file, but there is no atomic check-and-write. Two loops starting simultaneously with overlapping scope can both pass `find_conflict`, then both write their lock files — each believing it holds exclusive access. This undermines the entire concurrency protection model.

## Location

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Line(s)**: 82–122 (at scan commit: 47c81c8)
- **Anchor**: `in method LockManager.acquire()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/concurrency.py#L82-L122)
- **Code**:
```python
conflict = self.find_conflict(scope)   # check
if conflict:
    return False
# ... (gap here — no lock held) ...
lock_file = self.running_dir / f"{loop_name}.lock"
with open(lock_file, "w") as f:
    fcntl.flock(f, fcntl.LOCK_EX)     # write (TOCTOU gap above)
    json.dump(lock.to_dict(), f)
```

## Current Behavior

`find_conflict` scans existing `.lock` files for scope overlap, then (after a potential OS preemption) creates a new lock file. Two processes can both pass the `find_conflict` check before either has written its file. `fcntl.flock` on the individual file only serializes writes to the *same* file — it does not protect the cross-file check-and-create sequence.

## Expected Behavior

Exactly one of two simultaneously started loops with overlapping scope acquires the lock; the other receives a conflict error.

## Motivation

The lock mechanism is the sole guard preventing two `ll-loop` instances from corrupting shared state or running the same automation twice. A race window defeats this entirely. The failure mode (two loops running simultaneously) is silent — no error is raised.

## Steps to Reproduce

1. Write a loop `my-loop` with `scope: global`
2. Launch two instances simultaneously: `python -c "import subprocess; [subprocess.Popen(['ll-loop', 'run', 'my-loop']) for _ in range(2)]"`
3. Observe: both processes start and both write `.running/my-loop.lock` (or both proceed as if they acquired scope)

## Actual Behavior

Both processes pass `find_conflict`, both write their lock files, and both execute concurrently — violating scope exclusivity.

## Root Cause

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Anchor**: `in method LockManager.acquire()`
- **Cause**: `find_conflict` (read phase) and `open(lock_file, "w")` (write phase) are not atomic. No advisory lock guards the entire `.running/` directory during the check-and-create operation. `fcntl.flock` on the created file only serializes later writers to that same filename.

## Proposed Solution

Use a directory-level advisory lock file (e.g., `.running/.acquire.lock`) that is held with `LOCK_EX` across the entire check-and-create sequence:

```python
# In LockManager.acquire():
dir_lock_path = self.running_dir / ".acquire.lock"
self.running_dir.mkdir(parents=True, exist_ok=True)
with open(dir_lock_path, "w") as dir_lock:
    fcntl.flock(dir_lock, fcntl.LOCK_EX)   # serialize all acquire() calls
    conflict = self.find_conflict(scope)   # now atomic with write below
    if conflict:
        return False
    lock_file = self.running_dir / f"{loop_name}.lock"
    with open(lock_file, "w") as f:
        json.dump(lock.to_dict(), f)
    # dir_lock released on context exit
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/concurrency.py` — add directory-level lock in `LockManager.acquire()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py` — instantiates `LockManager`; behavior change is transparent
- `scripts/little_loops/cli/loop/run.py` — calls `persistence` which uses lock manager

### Similar Patterns
- `scripts/little_loops/parallel/git_lock.py` — check for similar advisory lock patterns to reuse

### Tests
- `scripts/tests/test_ll_loop_execution.py` — add concurrent-start test
- `scripts/tests/test_cli_loop_background.py` — test overlapping scope rejection

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `.acquire.lock` directory-level file lock wrapping the `find_conflict` + lock-file-write in `LockManager.acquire()`
2. Ensure lock file cleanup (`release()`, `cleanup_stale()`) does not remove `.acquire.lock`
3. Add a concurrent-start test that launches two processes simultaneously and verifies exactly one proceeds

## Impact

- **Priority**: P2 — Correctness bug in the exclusive-scope guarantee; silently allows double-execution
- **Effort**: Small — Wrapping with `fcntl.flock` on a sentinel file is a one-function change
- **Risk**: Low — Change is isolated to `acquire()`; all callers treat it as a boolean return
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Concurrency and locking model (line 1288), scope declaration, overlap rules |
| `docs/guides/LOOPS_GUIDE.md` | Scope-based concurrency overview (line 386) |

## Labels

`bug`, `ll-loop`, `concurrency`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md` concurrency section

## Resolution

- **Status**: Fixed
- **Date**: 2026-03-03
- **Commit**: (see git log)

### Changes Made

- `scripts/little_loops/fsm/concurrency.py`: Wrapped `find_conflict()` + lock-file creation in `LockManager.acquire()` with an `fcntl.LOCK_EX` on `.running/.acquire.lock` sentinel. The sentinel is a dotfile, so `Path.glob("*.lock")` does not match it and stale-lock cleanup in `find_conflict`/`list_locks` ignores it. The directory-level exclusive lock serializes all `acquire()` calls across processes/threads, eliminating the TOCTOU gap.
- `scripts/tests/test_concurrency.py`: Added `test_concurrent_acquire_same_scope_only_one_wins` to `TestLockManagerRaceConditions` — spawns two threads racing to acquire the same scope via `threading.Barrier`, asserts exactly one returns `True`.

---

**Closed** | Created: 2026-03-03 | Closed: 2026-03-03 | Priority: P2
