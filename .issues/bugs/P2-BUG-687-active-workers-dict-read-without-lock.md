---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# BUG-687: `_active_workers` dict read without lock in `WorkerPool`

## Summary

`WorkerPool._active_workers` is a plain `dict[str, Future[WorkerResult]]` written from the main thread in `submit()` without a lock, and iterated from other threads in `active_count()`. While CPython's GIL provides some protection for atomic dict operations, iterating `dict.values()` while another thread inserts is not guaranteed safe. Other shared collections (`_active_worktrees`, `_active_processes`, `_worker_stages`) correctly use `_process_lock`.

> **Note**: `get_active_stages()` already uses `with self._process_lock:` — only `submit()` and `active_count()` are unprotected.

## Location

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Line(s)**: 81, 184, 1273, 1308 (at scan commit: 3e9beea)
- **Anchor**: `in class WorkerPool`, methods `submit()`, `active_count()` (`get_active_stages()` already protected)
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/3e9beeaf2bbe8608104beb89fbc7e2e2259310d8/scripts/little_loops/parallel/worker_pool.py#L184)
- **Code**:
```python
# submit() - writes without lock
self._active_workers[issue_id] = future

# active_count() - reads without lock
sum(1 for f in self._active_workers.values() if not f.done())
```

## Current Behavior

`_active_workers` is read and written from multiple threads without synchronization. `active_count` is called from the orchestrator's `_execute` loop and `_wait_for_completion`. `get_active_stages` is called from the status reporter. Concurrent modification during iteration could cause `RuntimeError: dictionary changed size during iteration`.

## Expected Behavior

All reads and writes to `_active_workers` should be protected by `_process_lock`, consistent with how `_active_worktrees`, `_active_processes`, and `_worker_stages` are already protected.

## Steps to Reproduce

1. Run `ll-parallel` with 3+ workers and many issues
2. While workers are submitting, the orchestrator calls `active_count()` from its loop
3. Under load, dict iteration may overlap with dict insertion
4. Potential `RuntimeError` or stale count

## Root Cause

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Anchor**: `in class WorkerPool`
- **Cause**: `_active_workers` was not included in the locking discipline applied to the other shared collections in the class.

## Proposed Solution

Add `with self._process_lock:` guards around the `_active_workers` read in `active_count()` and the write in `submit()`. (`get_active_stages()` is already protected.)

## Implementation Steps

1. In `worker_pool.py`, add `with self._process_lock:` around `self._active_workers[issue_id] = future` in `submit()` (line 184)
2. Add `with self._process_lock:` around the `sum(...)` comprehension in `active_count()` (line 1273)

> Note: `get_active_stages()` (line 1308) already uses `with self._process_lock:` — no change needed.

## Integration Map

- **Modified**: `scripts/little_loops/parallel/worker_pool.py` — `submit()` (line 184), `active_count()` (line 1273)
- **Lock reused**: `self._process_lock` (already used for `_active_worktrees`, `_active_processes`, `_worker_stages`)

## Impact

- **Priority**: P2 - Thread safety issue that could cause crashes under concurrent load
- **Effort**: Small - Add lock guards to 3 locations
- **Risk**: Low - Adding locks to match existing pattern
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `thread-safety`

## Verification Notes

**Verdict**: NEEDS_UPDATE — 2026-03-12

- `submit()` (line 184) and `active_count()` (line 1273) confirmed unprotected
- `get_active_stages()` (line 1306-1308) already uses `with self._process_lock:` — issue incorrectly claimed it was unprotected; corrected above

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P2
