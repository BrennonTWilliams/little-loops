---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
resolution: wont-fix
closed_date: 2026-02-05
closing_note: "Theoretical edge case with existing mitigations. The race window is microseconds, fcntl.flock() provides file-level atomicity, and stale locks from dead processes are auto-cleaned. Adding a global lock introduces complexity for a near-impossible scenario with no evidence of occurring in practice."
---

# BUG-232: TOCTOU race condition in scope lock acquisition

## Summary

There is a Time-Of-Check-To-Time-Of-Use (TOCTOU) race between calling `find_conflict()` and creating the lock file in `LockManager.acquire()`. Two FSM loops with overlapping scopes could both pass the conflict check and acquire locks simultaneously.

## Location

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Line(s)**: 82-122 (at scan commit: a8f4144)
- **Anchor**: `in method LockManager.acquire`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/fsm/concurrency.py#L82-L122)
- **Code**:
```python
def acquire(self, loop_name: str, scope: list[str]) -> bool:
    conflict = self.find_conflict(scope)  # Check
    if conflict:
        return False
    # Gap: another process could acquire here
    self.running_dir.mkdir(parents=True, exist_ok=True)
    lock_file = self.running_dir / f"{loop_name}.lock"
    # ...
    with open(lock_file, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # Only locks THIS file
        try:
            json.dump(lock.to_dict(), f)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
```

## Current Behavior

The `fcntl.flock()` only provides mutual exclusion on the individual lock file, not on the check-then-create operation. Two concurrent `acquire()` calls with overlapping scopes can both pass the conflict check and create their locks.

## Expected Behavior

The conflict check and lock creation should be atomic. Either a global lock file for the running directory, or an atomic create-and-check approach should be used.

## Reproduction Steps

1. Start two `ll-loop run` instances with overlapping scopes nearly simultaneously
2. Both can pass `find_conflict()` before either creates a lock file
3. Both acquire locks despite having conflicting scopes

## Proposed Solution

Use a global directory lock for the check-and-create sequence:
```python
global_lock = self.running_dir / ".global.lock"
with open(global_lock, "w") as gl:
    fcntl.flock(gl, fcntl.LOCK_EX)
    conflict = self.find_conflict(scope)
    if conflict:
        return False
    # Create lock file while holding global lock
    # ...
```

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p2`

---

## Status
**Closed (won't-fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P2
