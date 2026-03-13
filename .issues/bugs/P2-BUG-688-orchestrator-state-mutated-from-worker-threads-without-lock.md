---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# BUG-688: `self.state` mutated from worker threads without lock in orchestrator

## Summary

The `_on_worker_complete` callback runs in `ThreadPoolExecutor` worker threads (registered via `future.add_done_callback`). It directly mutates `self.state.corrections` and `self.state.timing` — plain dict fields on the `OrchestratorState` dataclass — while the main thread may be reading or serializing the same state in `_report_results` or `_save_state`.

## Location

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Line(s)**: 836, 848 (at scan commit: 3e9beea)
- **Anchor**: `in method ParallelOrchestrator._on_worker_complete()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/3e9beeaf2bbe8608104beb89fbc7e2e2259310d8/scripts/little_loops/parallel/orchestrator.py#L836)
- **Code**:
```python
self.state.corrections[result.issue_id] = result.corrections   # line 836
self.state.timing[result.issue_id] = {"total": result.duration} # line 848
```

## Current Behavior

`_on_worker_complete` writes to `self.state` dicts from worker threads. The main thread reads `self.state.timing` in `_report_results` and serializes the entire state in `_save_state`. No lock protects `self.state` access in either direction. Under concurrent worker completions, dict writes from multiple threads could interleave with dict reads/serialization.

## Expected Behavior

Access to `self.state` should be synchronized, either by adding a lock around state mutations and reads, or by queuing state updates for the main thread to process.

## Motivation

`ll-parallel` is the primary concurrent execution tool. Under concurrent worker completions, unsynchronized dict writes from multiple threads can silently corrupt `self.state.corrections` and `self.state.timing`, causing state data loss during `_save_state()` serialization or raising a `RuntimeError` at runtime. This makes parallel runs unreliable and difficult to diagnose — results may appear to succeed while quietly dropping correction data.

## Steps to Reproduce

1. Run `ll-parallel` with 3+ concurrent workers
2. Multiple workers complete simultaneously
3. `_on_worker_complete` callbacks fire on different threads
4. Main thread calls `_save_state()` which serializes all state dicts
5. Potential for corrupted state serialization or `RuntimeError`

## Root Cause

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Anchor**: `in method _on_worker_complete()`
- **Cause**: The callback registered via `future.add_done_callback` runs in the executor's thread, not the main thread. The state dataclass fields are plain dicts with no synchronization.

## Proposed Solution

Add a `threading.Lock` to protect `self.state` mutations. Apply it in `_on_worker_complete` and in `_save_state`/`_report_results` when reading state.

## Implementation Steps

1. In `orchestrator.py`, add `self._state_lock = threading.Lock()` to `ParallelOrchestrator.__init__`
2. Wrap `self.state.corrections[...]` and `self.state.timing[...]` writes in `_on_worker_complete` with `with self._state_lock:`
3. Wrap `self.state.timing` reads in `_report_results` with `with self._state_lock:`
4. Wrap state serialization in `_save_state` with `with self._state_lock:`

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator.__init__()`, `_on_worker_complete()`, `_report_results()`, `_save_state()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — self-contained; `_on_worker_complete` is registered internally via `future.add_done_callback`, not called externally

### Similar Patterns
- Check `orchestrator.py` for any other `future.add_done_callback` registrations that access shared state; apply the same lock pattern for consistency

### Tests
- `scripts/tests/test_orchestrator.py` — add a concurrent-completion scenario test that fires multiple `_on_worker_complete` callbacks simultaneously to assert no state corruption

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 - Can cause state corruption or crashes during concurrent parallel runs
- **Effort**: Small - Add lock around state access points
- **Risk**: Low - Standard thread-safety fix
- **Breaking Change**: No

## Related Key Documentation

- N/A

## Labels

`bug`, `parallel`, `thread-safety`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:format-issue` - 2026-03-13T02:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:verify-issues` - 2026-03-13T02:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-13T02:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P2
