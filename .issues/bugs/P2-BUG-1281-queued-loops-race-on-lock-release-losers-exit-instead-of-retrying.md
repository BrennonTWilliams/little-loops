---
captured_at: "2026-04-25T17:52:57Z"
discovered_date: "2026-04-25"
discovered_by: capture-issue
---

# BUG-1281: Queued loops race on lock release — losers exit instead of retrying

## Summary

When two or more loops are queued with `--queue` and the currently running loop finishes, all waiters simultaneously detect the scope is free and race to acquire the lock. Only one wins; the rest hit an error exit path instead of retrying or re-queuing.

## Current Behavior

1. Loop A runs and holds the scope lock.
2. Loops B and C are started with `--queue`; both enter `wait_for_scope`, polling every 1 second.
3. Loop A finishes and releases the lock.
4. In the same polling tick, B and C both see `conflict is None` and both call `acquire()`.
5. `acquire()` uses `fcntl.flock(LOCK_EX)` on `.acquire.lock`, so only one wins (no TOCTOU race).
6. The loser returns `False` from `acquire` and hits `run.py:185–189`:
   ```python
   if not lock_manager.acquire(fsm.name, scope):
       _cleanup_queue_entry()
       logger.error("Failed to acquire lock after waiting")
       return 1
   ```
7. The loser exits with code 1. Queuing 3+ loops means only 1 successfully follows the first.

## Expected Behavior

All queued loops should execute sequentially, one at a time, in the order they were queued. A loser in the re-acquire race should loop back into `wait_for_scope` and try again rather than erroring out.

## Motivation

When three or more loops are queued against the same scope, only the first queued loop successfully follows the running loop — all others exit with code 1. This silently drops work and makes the `--queue` flag unreliable for coordinating multiple automation tasks. Users relying on queue ordering to serialize loop runs will see unexpected failures with no indication that retrying is an option.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/run.py`
- **Lines**: 185–189
- **Function**: `cmd_run`
- **Explanation**: After `wait_for_scope` returns `True`, `acquire()` is attempted once with no retry. This is correct for detecting genuine contention, but wrong in the queue path where the intent is "keep waiting until I can run." The single `acquire` attempt after the wait is not retry-safe when multiple waiters are released simultaneously.

## Steps to Reproduce

```bash
# Terminal 1: start a long-running loop
ll-loop run my-loop

# Terminal 2: queue a second loop
ll-loop run my-loop --queue

# Terminal 3: queue a third loop
ll-loop run my-loop --queue

# Observe: when Terminal 1 finishes, one of Terminal 2/3 runs but the other
# exits with "Failed to acquire lock after waiting"
```

## Proposed Solution

In `cmd_run`, replace the single re-acquire attempt with a retry loop:

```python
# Instead of:
if not lock_manager.acquire(fsm.name, scope):
    _cleanup_queue_entry()
    logger.error("Failed to acquire lock after waiting")
    return 1

# Use:
acquired = False
while time.time() - _queue_wait_start < _config.loops.queue_wait_timeout_seconds:
    if lock_manager.acquire(fsm.name, scope):
        acquired = True
        break
    if not lock_manager.wait_for_scope(scope, timeout=_config.loops.queue_wait_timeout_seconds):
        break
if not acquired:
    _cleanup_queue_entry()
    logger.error("Failed to acquire lock after waiting")
    return 1
```

Alternatively, wrap the wait-and-acquire in a loop that retries on contention rather than treating re-acquire failure as terminal.

## Implementation Steps

1. Refactor the queue wait path in `cmd_run` (`run.py:156–199`) to loop on `wait_for_scope` + `acquire` until either acquired or timed out.
2. Track total elapsed time across all retry attempts against `queue_wait_timeout_seconds`.
3. Add a test in `test_cli_loop_background.py` or a new `test_cli_loop_queue.py` that spawns three loops against the same scope and asserts all three complete in order.
4. Update the queue entry's `context` to reflect "nth in queue" position if possible (dashboard improvement).

## Affected Files

- `scripts/little_loops/cli/loop/run.py` (primary fix)
- `scripts/little_loops/fsm/concurrency.py` (may need `wait_for_scope` signature adjustment)
- `scripts/tests/test_cli_loop_background.py` or new test file (new test)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` (primary fix: retry loop in `cmd_run`)
- `scripts/little_loops/fsm/concurrency.py` (may need `wait_for_scope` signature adjustment)

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "wait_for_scope" scripts/`

### Similar Patterns
- TBD - check for other single-attempt `acquire()` call sites in lock management code

### Tests
- `scripts/tests/test_cli_loop_background.py` (extend with 3-loop queue scenario)
- `scripts/tests/test_cli_loop_queue.py` (new test file for queue race behavior)

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 - Race condition silently drops queued work; `--queue` flag unreliable with 3+ loops
- **Effort**: Small - Localized retry loop in `cmd_run`; no new public API surface
- **Risk**: Low - Only affects the queued wait code path; normal non-queued runs are unaffected
- **Breaking Change**: No

## Labels

`bug`, `concurrency`, `queue`

## Status

**Open** | Created: 2026-04-25 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-04-25T17:55:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d2c7950-d0ee-4041-bf92-0ddda25d62fa.jsonl`
- `/ll:capture-issue` - 2026-04-25T17:52:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96749c6f-f17b-4d10-b158-4822f481e6b6.jsonl`
