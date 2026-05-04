---
captured_at: "2026-05-04T18:08:58Z"
discovered_date: 2026-05-04
discovered_by: capture-issue
---

# BUG-1361: FIFO queue blocked by orphaned entries from dead processes — _is_earliest_waiter never checks PID liveness

## Summary

When multiple loops are queued with `--queue`, any queue entry whose process died without a clean shutdown (SIGKILL, crash, OOM) is never removed. `_is_earliest_waiter` sorts all entries by `enqueuedAt` timestamp without checking whether each entry's process is still alive. Orphaned entries from earlier dates sort to the front and block every live waiter indefinitely — the live waiter sees itself as "not earliest" on every check and sleeps forever, even when no lock is held and the scope is completely free.

Observed in blender-agents: two stale queue entries from May 1 (PIDs 3254 and 38272, both dead) were blocking a live autodev loop for ENH-9140 (PID 45279, May 4) from ever acquiring the lock, despite the previous loop having completed and released its lock successfully.

## Root Cause

**File**: `scripts/little_loops/cli/loop/_helpers.py`, `_is_earliest_waiter` function

```python
# Before fix — no liveness check
for f in queue_dir.glob("*.json"):
    try:
        with open(f) as fh:
            data = json.load(fh)
        entries.append(data)   # ← appended unconditionally, dead PIDs included
    except ...:
        continue
entries.sort(key=lambda d: d.get("enqueuedAt", ""))
return entries[0].get("id") == entry_id
```

Queue entries write their PID in `context.pid` but `_is_earliest_waiter` never reads it. `atexit` handlers clean up entries on normal exit but do not run on SIGKILL or crash, leaving orphaned `.json` files in `.loops/.queue/`. These permanently block any later-timestamped live waiter.

`find_conflict` in `concurrency.py` has analogous stale-lock handling — it calls `_process_alive(lock.pid)` for each lock file and removes dead ones. `_is_earliest_waiter` was written without this pattern (ENH-1332 commit aedc56e0).

## Fix

**File**: `scripts/little_loops/cli/loop/_helpers.py`

Added dead-PID filtering inside the entry-loading loop, matching `find_conflict`'s stale-cleanup pattern:

```python
pid = data.get("context", {}).get("pid")
if pid is not None and not _process_alive(pid):
    f.unlink(missing_ok=True)
    continue
entries.append(data)
```

Also added the necessary import: `from little_loops.fsm.concurrency import _process_alive`.

With the fix, stale entries are deleted on discovery and excluded from the ordering sort, so live waiters correctly identify themselves as earliest and proceed to acquire the lock.

## Immediate Remediation (blender-agents)

Manually deleted the two orphaned queue entries:
- `f9dfe946-a597-427e-afda-1eaa91459858.json` (autodev, PID 38272, May 1)
- `a0d023df-7a39-470d-967d-c3fe753bc91a.json` (eval-specfile-gold, PID 3254, May 1)

The live autodev loop for ENH-9140 (PID 45279) picked up within one polling cycle (~1 second) after removal.

## Test Coverage Added

Added `test_stale_entries_from_dead_pids_are_skipped` to `TestQueueFifoOrdering` in `scripts/tests/test_cli_loop_queue.py`. Verifies that:
- An entry with a dead PID (99999999) that sorts earlier by timestamp is skipped and its file deleted
- The live entry with a later timestamp is returned as the earliest waiter

## Files Changed

- `scripts/little_loops/cli/loop/_helpers.py` — added `_process_alive` import; added dead-PID check and cleanup in `_is_earliest_waiter`
- `scripts/tests/test_cli_loop_queue.py` — added `test_stale_entries_from_dead_pids_are_skipped`

## Relationship to BUG-1360

BUG-1360 (same session) fixed a separate issue: the retry acquire omitting `instance_id`, causing lock files to be named wrong and not cleaned up on loop completion. BUG-1361 is independent — it occurs even when locks are properly released, because the queue entry for a crashed earlier run is never removed.

Together these two bugs explain the full "queued loops never fire" symptom:
- BUG-1360: lock not released → next loop waits for process exit (~seconds delay)
- BUG-1361: orphaned queue entry → next loop defers forever

## Session Log

- `/ll:capture-issue` - 2026-05-04T18:08:58Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

## Status

**Completed** | Created: 2026-05-04 | Completed: 2026-05-04 | Priority: P2
