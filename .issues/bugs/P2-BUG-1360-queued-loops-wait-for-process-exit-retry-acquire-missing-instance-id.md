---
captured_at: "2026-05-04T17:13:05Z"
discovered_date: 2026-05-04
discovered_by: capture-issue
status: done
completed_at: 2026-05-04T00:00:00Z
---

# BUG-1360: Queued loops wait for process exit instead of lock release — retry acquire missing instance_id

## Summary

When multiple loops are queued with `--queue`, only the first queued loop fires immediately after the running loop completes. Subsequent queued loops appear stuck waiting indefinitely and only start after the previous loop's process fully exits — rather than when its work finishes and its lock is released.

## Root Cause

**File**: `scripts/little_loops/cli/loop/run.py`, line 266 (before fix)

The retry acquire inside the queue wait loop omitted `instance_id`:

```python
# BUG — creates {loop_name}.lock instead of {instance_id}.lock
if lock_manager.acquire(fsm.name, scope):
```

The initial acquire (line 230) correctly passes `instance_id`:

```python
if not lock_manager.acquire(fsm.name, scope, instance_id=instance_id):
```

`LockManager.acquire` with no `instance_id` creates the lock file as `{loop_name}.lock` (e.g., `test-loop.lock`) instead of `{instance_id}.lock` (e.g., `test-loop-20260504T100001.lock`).

When the loop finished, `release()` was called with the correct `instance_id`:

```python
lock_manager.release(fsm.name, instance_id=instance_id)  # line 360
```

This tried to delete `{instance_id}.lock` — which didn't exist. `missing_ok=True` silently swallowed the error. The actual lock file `{loop_name}.lock` was **never deleted**.

The dangling lock was only cleared by stale-lock detection in `find_conflict()`, which polls every second checking whether the lock-holder's PID is dead. Subsequent queued loops therefore had to wait not just for the previous loop's work to finish, but for its entire process to fully exit. Any delay in process shutdown (slow `close_transports`, lingering subprocesses, Python GC) extended this window, making subsequent loops appear frozen.

## History

The bug existed from the original BUG-1281 fix (commit `c5483377`) which introduced the retry-acquire loop. Both the initial BUG-1281 implementation and the subsequent FIFO-ordering enhancement (commit `aedc56e0`, ENH-1332) used the no-`instance_id` form. The FIFO change made the symptom more visible: before FIFO, all waiters raced opportunistically after the running loop finished; after FIFO, each waiter serialized behind the next, so every hop required the previous process to die rather than just release its lock.

## Fix

**One-line change** in `scripts/little_loops/cli/loop/run.py`:

```python
# Before (bug):
if lock_manager.acquire(fsm.name, scope):

# After (fix):
if lock_manager.acquire(fsm.name, scope, instance_id=instance_id):
```

This ensures the retry acquire creates the same `{instance_id}.lock` file that `release()` will later delete, so the lock is cleaned up as soon as the loop finishes — not waiting for process exit.

## Test Coverage Added

Extended `test_retries_acquire_after_losing_race` in `scripts/tests/test_cli_loop_queue.py` to assert that all retry `acquire` calls carry the same `instance_id` keyword argument as the initial acquire. Previously the tests only verified call counts, not arguments.

## Files Changed

- `scripts/little_loops/cli/loop/run.py` — line 266: added `instance_id=instance_id`
- `scripts/tests/test_cli_loop_queue.py` — added `instance_id` kwarg assertions to `test_retries_acquire_after_losing_race`

## Impact

- **Affected**: all users running multiple loops with `--queue` in foreground mode
- **Symptom**: 2nd and later queued loops appeared stuck after the 1st completed; they eventually ran (after process exit) but with an unpredictable delay
- **Risk of fix**: None — passing `instance_id` aligns retry behavior with initial acquire and with `release()`

## Session Log

- `/ll:capture-issue` - 2026-05-04T17:13:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

## Status

**Completed** | Created: 2026-05-04 | Completed: 2026-05-04 | Priority: P2
