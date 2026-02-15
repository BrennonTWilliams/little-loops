---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# BUG-423: Lock file race condition in FSM concurrency LockManager

## Summary

In `LockManager.acquire()`, the file lock (`fcntl.LOCK_UN`) is released before the function returns. Between the unlock and the return, another process could delete the lock file via `release()` or another `acquire()` could proceed. The `release()` method also doesn't hold any lock while deleting, so concurrent releases could race.

## Location

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Line(s)**: 114-122, 131-132 (at scan commit: 71616c7)
- **Anchor**: `in methods LockManager.acquire() and LockManager.release()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/71616c711e2fe9f5f1ececcf1c64552bca9d82ec/scripts/little_loops/fsm/concurrency.py#L114-L132)
- **Code**:
```python
# acquire():
with open(lock_file, "w") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    try:
        json.dump(lock.to_dict(), f)
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
return True

# release():
lock_file = self.running_dir / f"{loop_name}.lock"
if lock_file.exists():
    lock_file.unlink()
```

## Current Behavior

Lock is released before `acquire()` returns. `release()` has no locking around file deletion.

## Expected Behavior

Lock operations should be atomic. Consider keeping the lock file handle open for the duration of the lock hold, or using `unlink(missing_ok=True)` in release.

## Steps to Reproduce

1. Run two concurrent FSM loops targeting the same scope
2. Have them rapidly acquire and release locks
3. Race condition may manifest as `FileNotFoundError` in release or stale lock detection

## Actual Behavior

Theoretical race window between lock release and function return; `FileNotFoundError` possible in concurrent `release()` calls.

## Root Cause

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Anchor**: `in class LockManager`
- **Cause**: Lock release and file deletion are not atomic. The `with open()` context manager closes the file (releasing the lock) before the function returns, and `release()` uses check-then-delete pattern.

## Proposed Solution

1. Use `unlink(missing_ok=True)` in `release()` to avoid race on deletion

> **Scope note (2026-02-14)**: The "keep fd open" redesign (storing file handles in instance dict) is out of scope — it adds significant complexity for a theoretical race that is already mitigated by `find_conflict()`. The `missing_ok=True` fix alone addresses the concrete `FileNotFoundError` risk.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/concurrency.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/engine.py` — uses LockManager

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_concurrency.py` — if exists, add race condition test

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Replace `if exists(): unlink()` with `unlink(missing_ok=True)` in `release()`
2. Add concurrency tests

## Impact

- **Priority**: P4 - Theoretical race condition, mitigated by existing `find_conflict()` check
- **Effort**: Small - Minor code change
- **Risk**: Low - Defensive improvement
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `fsm`, `concurrency`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P4
