---
captured_at: "2026-04-25T17:52:57Z"
completed_at: "2026-04-25T18:36:53Z"
discovered_date: "2026-04-25"
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
status: done
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
6. The loser returns `False` from `acquire` and hits `run.py:250–253`:
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
- **Lines**: 250–253
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

1. In `scripts/little_loops/cli/loop/run.py:250–253`, replace the single `acquire()` call with a retry loop. Capture `start = time.time()` immediately before the loop (note: `_queue_wait_start` referenced in the Proposed Solution does not yet exist — add it here). The loop should call `wait_for_scope` followed by `acquire` until `acquired` or `time.time() - start >= queue_wait_timeout_seconds`.
2. Track elapsed time with `start = time.time()` captured once before the retry loop; pass the remaining budget `(queue_wait_timeout_seconds - elapsed)` as the `timeout` arg to each `wait_for_scope` call to avoid consuming the full timeout on every iteration.
3. Add tests in `scripts/tests/test_concurrency.py` (unit: N threads race after `wait_for_scope`, all eventually acquire) and `scripts/tests/test_cli_loop_background.py` or a new `test_cli_loop_queue.py` (integration: 3 loops against the same scope all complete in order). Follow the `threading.Barrier` pattern at `test_concurrency.py:333–355` for the unit test, and `patch("time.sleep")` suppression from `test_cli_loop_background.py:440–468` for integration tests.
4. Update the queue entry's `context` to reflect "nth in queue" position if possible (dashboard improvement — optional/separate).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Review `docs/guides/LOOPS_GUIDE.md:1248` — verify "exits with code 1 if the timeout is reached" language remains accurate (it does — retry loop exhausts full budget before exiting with code 1)
6. Review `docs/reference/CLI.md:325` — verify `_cleanup_queue_entry()` is called on all exit paths inside the new retry loop, preserving the documented cleanup contract
7. Add test to `scripts/tests/test_concurrency.py` in `TestLockManagerRaceConditions` — N-thread race after `wait_for_scope`, all eventually acquiring; validates the post-fix guarantee that all waiters succeed

## Affected Files

- `scripts/little_loops/cli/loop/run.py` (primary fix)
- `scripts/little_loops/fsm/concurrency.py` (may need `wait_for_scope` signature adjustment)
- `scripts/tests/test_cli_loop_background.py` or new test file (new test)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` (primary fix: retry loop in `cmd_run`)
- `scripts/little_loops/fsm/concurrency.py` (may need `wait_for_scope` signature adjustment)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:221` — first `acquire(fsm.name, scope)` call (non-queued path; not affected)
- `scripts/little_loops/cli/loop/run.py:243–245` — calls `wait_for_scope(scope, timeout=_config.loops.queue_wait_timeout_seconds)` in the queue wait path
- `scripts/little_loops/cli/loop/run.py:250` — re-acquire after wait (the race-loser exit at lines 251–253; **the bug site**)
- `scripts/little_loops/cli/loop/lifecycle.py` — imports from `concurrency` module (indirect dependency; not affected by fix)
- `scripts/little_loops/fsm/persistence.py` — imports concurrency utilities (indirect dependency; not affected by fix)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py:24` — deferred import dispatches to `cmd_run`; review if function signature changes [Agent 1 finding]
- `scripts/little_loops/cli/loop/_helpers.py:254-255` — forwards `--queue` when spawning background child; no code change needed but queue behavior changes propagate through this spawn path [Agent 1 finding]
- `scripts/little_loops/fsm/__init__.py:73-76` — re-exports `LockManager` and `ScopeLock` as public API; no callers use this path for `wait_for_scope` directly [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/parallel/git_lock.py:110–181` — `for attempt in range(max_retries + 1)` retry loop with exponential backoff; closest existing model for retry-on-contention
- `scripts/little_loops/parallel/orchestrator.py:1052–1058` — `start = time.time()` / `while time.time() - start > timeout` timeout-bounded polling idiom
- `scripts/little_loops/fsm/concurrency.py:221–238` — `wait_for_scope` itself uses `start = time.time()` / `while time.time() - start < timeout`; the same idiom needed in the retry loop
- No existing `while ... acquire()` retry loop anywhere in the codebase; this fix introduces the pattern for FSM scope locks

### Tests
- `scripts/tests/test_cli_loop_background.py` (extend with 3-loop queue scenario)
- `scripts/tests/test_cli_loop_queue.py` (new test file for queue race behavior)

#### Codebase Research Findings

_Added by `/ll:refine-issue` — existing test patterns to follow:_

- `scripts/tests/test_concurrency.py:333–355` — `TestLockManagerRaceConditions.test_concurrent_acquire_same_scope_only_one_wins`: uses `threading.Barrier(2)` to fire concurrent `acquire()` calls simultaneously; directly models the N-loser scenario
- `scripts/tests/test_concurrency.py:394–409` — `TestLockManagerWait.test_wait_succeeds_when_released`: releases a lock in a background thread after 0.5 s while the main thread calls `wait_for_scope`; pattern for the "lock released mid-wait" flow
- `scripts/tests/test_cli_loop_background.py:440–468` — uses `side_effect=[True, False]` list drain for mocked `_process_alive` and `patch("time.sleep")` suppression; useful pattern for testing retry loops without real sleeps

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_concurrency.py` — add new test in `TestLockManagerRaceConditions` (after line 355): N threads all call `wait_for_scope` then `acquire`; assert all eventually acquire (validates post-fix guarantee that all waiters succeed, not just the first) [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:1189,1248` — describes `--queue` timeout behavior; review that "exits with code 1 if timeout is reached" language remains accurate after fix (the retry loop exhausts budget before exiting with code 1, so the statement stays true) [Agent 2 finding]
- `docs/reference/CLI.md:325` — documents queue entry cleanup contract; ensure `_cleanup_queue_entry()` is called on all exit paths inside the new retry loop [Agent 2 finding]

### Configuration
- N/A

## Impact

- **Priority**: P2 - Race condition silently drops queued work; `--queue` flag unreliable with 3+ loops
- **Effort**: Small - Localized retry loop in `cmd_run`; no new public API surface
- **Risk**: Low - Only affects the queued wait code path; normal non-queued runs are unaffected
- **Breaking Change**: No

## Labels

`bug`, `concurrency`, `queue`

## Resolution

**Status**: Resolved — 2026-04-25

**Root cause confirmed**: `run.py:250–253` — single `acquire()` attempt after `wait_for_scope` returned; race losers exited instead of retrying.

**Fix**: Replaced the single `acquire()` call with a budget-bounded retry loop (`run.py:249–265`). Each iteration calls `wait_for_scope` (with remaining budget) followed by `acquire`; losers loop back and wait again rather than erroring out. The full `queue_wait_timeout_seconds` budget is honored across all retry iterations.

**Files changed**:
- `scripts/little_loops/cli/loop/run.py` — added `import time`, replaced single re-acquire with retry loop
- `scripts/tests/test_concurrency.py` — added `test_n_waiters_all_acquire_with_retry_loop` to `TestLockManagerRaceConditions`
- `scripts/tests/test_cli_loop_queue.py` — new file with 3 integration tests covering retry-on-race-loss, timeout, and no-queue paths

## Status

**Completed** | Created: 2026-04-25 | Resolved: 2026-04-25 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-04-25T18:28:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4588686a-6793-4135-809c-1d6ca930a43d.jsonl`
- `/ll:confidence-check` - 2026-04-25T19:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a9f32ef-6ec4-4af5-8546-284a45998af5.jsonl`
- `/ll:wire-issue` - 2026-04-25T18:22:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/54b83519-3784-4f4d-b5d2-f18d09719dba.jsonl`
- `/ll:refine-issue` - 2026-04-25T18:17:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/72c88749-3ee6-4e4b-abc5-6e087bca4831.jsonl`
- `/ll:format-issue` - 2026-04-25T17:55:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d2c7950-d0ee-4041-bf92-0ddda25d62fa.jsonl`
- `/ll:manage-issue` - 2026-04-25T18:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/12337146-4afa-476f-8b72-8f6e961f721f.jsonl`
- `/ll:capture-issue` - 2026-04-25T17:52:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96749c6f-f17b-4d10-b158-4822f481e6b6.jsonl`
