# Plan: BUG-423 - Lock file race condition in FSM concurrency LockManager

**Issue**: P4-BUG-423-lock-file-race-condition-in-fsm-concurrency.md
**Action**: fix
**Created**: 2026-02-14

## Problem

Three `unlink()` call sites in `LockManager` lack `missing_ok=True`, creating potential `FileNotFoundError` in concurrent scenarios:

1. **`release()` line 132**: Uses TOCTOU check-then-delete pattern (`if exists(): unlink()`)
2. **`find_conflict()` line 157**: Bare `unlink()` for stale lock cleanup
3. **`list_locks()` line 192**: Bare `unlink()` for stale lock cleanup

Note: `find_conflict()` and `list_locks()` already catch `FileNotFoundError` in their except blocks (lines 164, 193), so those calls won't crash — but they rely on exception handling as flow control. Using `missing_ok=True` is cleaner and more explicit.

## Solution

### Phase 1: Fix `release()` TOCTOU race (concurrency.py:131-132)

Replace check-then-delete with unconditional `unlink(missing_ok=True)`:

```python
# Before:
if lock_file.exists():
    lock_file.unlink()

# After:
lock_file.unlink(missing_ok=True)
```

### Phase 2: Fix `find_conflict()` bare unlink (concurrency.py:157)

```python
# Before:
lock_file.unlink()

# After:
lock_file.unlink(missing_ok=True)
```

### Phase 3: Fix `list_locks()` bare unlink (concurrency.py:192)

```python
# Before:
lock_file.unlink()

# After:
lock_file.unlink(missing_ok=True)
```

### Phase 4: Add race condition test (test_concurrency.py)

Add test that simulates the TOCTOU race in `release()`:
- Acquire lock, manually delete the lock file, then call `release()` — should not raise.

Add test that simulates concurrent stale lock cleanup:
- Create stale lock file, delete it before `find_conflict()` processes it — should not raise.

## Success Criteria

- [ ] All three `unlink()` calls use `missing_ok=True`
- [ ] `release()` no longer uses check-then-delete pattern
- [ ] New tests cover the race condition scenarios
- [ ] All existing tests pass
- [ ] Lint and type checks pass
