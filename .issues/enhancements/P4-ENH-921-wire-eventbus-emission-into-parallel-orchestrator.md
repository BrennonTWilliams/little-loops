---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 86
---

# ENH-921: Wire EventBus Emission into Parallel Orchestrator

## Summary

Add EventBus event emission to `_on_worker_complete()` in `orchestrator.py` so extensions can observe worker completion events during parallel processing runs.

## Context

Identified from FEAT-911 session continuation prompt. The parallel orchestrator manages concurrent issue processing via worktrees. Emitting events from worker completion gives extensions visibility into parallel run progress.

**Note**: ENH-470 (refactor parallel god classes) may modify `orchestrator.py` significantly. Check ENH-470 status before implementing to assess conflict risk.

## Current Behavior

`_on_worker_complete()` in `orchestrator.py` handles worker results silently. Extensions have no visibility into parallel processing progress.

## Expected Behavior

- `_on_worker_complete()` → emits `parallel.worker_completed` with worker ID, issue ID, success/failure status, and duration

## Motivation

Parallel runs are the most complex execution mode. Real-time worker completion events enable progress dashboards, resource monitoring extensions, and failure alerting during long-running parallel batches.

## Proposed Solution

Wire an optional `EventBus` into the parallel orchestrator and emit from `_on_worker_complete()`:

1. Accept an optional `event_bus: EventBus | None` parameter in the orchestrator's `__init__()` (or equivalent entry point)
2. In `_on_worker_complete()`, after existing result handling, emit:
   ```python
   if self._event_bus:
       self._event_bus.emit({
           "event": "parallel.worker_completed",
           "ts": _iso_now(),
           "issue_id": result.issue_id,
           "worker_name": result.worktree_path.name,
           "status": "success" if result.success else "failure",
           "duration_seconds": result.duration,
       })
   ```
3. Follow the same pattern established in FEAT-911 / ENH-919 / ENH-920 for EventBus wiring

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`emit()` takes a single `dict` argument** (`events.py:93`), not two positional args. The flat dict must include `"event"` and `"ts"` top-level keys alongside payload fields, matching `LLEvent.to_dict()` format (`events.py:41-47`).
- **No `worker_id` field exists on `WorkerResult`** (`parallel/types.py:52-91`). Use `result.worktree_path.name` (format: `worker-{issue_id}-{timestamp}`) or `result.branch_name` as the worker identifier. `result.issue_id` is the primary key used throughout the orchestrator.
- **`_on_worker_complete()` runs in a thread pool thread** (`worker_pool.py:188-190`), not the main thread. `EventBus.emit()` is safe here — observer exceptions are caught and logged (`events.py:102-103`), and `_handle_completion()` also catches callback exceptions (`worker_pool.py:224-225`).
- **Two construction sites** need `event_bus` threading: `cli/parallel.py:224` and `cli/sprint/run.py:387`.

## API/Interface

```python
# Event emitted from _on_worker_complete() — single flat dict per EventBus.emit() signature
event_bus.emit({
    "event": "parallel.worker_completed",
    "ts": str,                # ISO 8601 timestamp
    "issue_id": str,          # Issue being processed (from WorkerResult.issue_id)
    "worker_name": str,       # Worktree name (from WorkerResult.worktree_path.name)
    "status": str,            # "success" | "failure"
    "duration_seconds": float, # Wall-clock time (from WorkerResult.duration)
})
```

> **Note**: The original `worker_id` field was renamed to `worker_name` because `WorkerResult` (`parallel/types.py:52-91`) has no `worker_id` attribute. The worktree directory name (`worker-{issue_id}-{timestamp}`) serves as the unique worker identifier.

## Implementation Steps

1. Check ENH-470 status for conflict risk on `orchestrator.py`
2. Add `event_bus: EventBus | None = None` parameter to `ParallelOrchestrator.__init__()` (`orchestrator.py:60-67`), store as `self._event_bus`
3. In `_on_worker_complete()` (`orchestrator.py:830-908`), after the shared trailing logic (line ~902-908), emit `parallel.worker_completed` using flat dict format with `"event"` and `"ts"` keys
4. Thread `event_bus` from both CLI construction sites:
   - `cli/parallel.py:224` — primary `ll-parallel` entry point
   - `cli/sprint/run.py:387` — sprint runner entry point
5. Add tests following existing patterns in `test_orchestrator.py` (fixture at line 131, `_on_worker_complete` tests at line 1231) using list-collector + lambda pattern from `test_events.py:97-168`
6. Run `python -m pytest scripts/tests/test_orchestrator.py scripts/tests/test_events.py -v`

## Scope Boundaries

- **In scope**: Emitting `parallel.worker_completed` from `_on_worker_complete()` with worker metadata; adding optional `event_bus` parameter to orchestrator
- **Out of scope**: Emitting events from other orchestrator lifecycle points (start, queue, retry); building consumer extensions; modifying worktree management logic

## Success Metrics

- `parallel.worker_completed` event fires for every worker completion (success and failure)
- Event payload contains all four required fields (issue_id, worker_name, status, duration_seconds)
- No performance regression in parallel orchestrator (event emission is fire-and-forget)

## Acceptance Criteria

- [x] ENH-470 conflict risk assessed before implementation
- [x] `ParallelOrchestrator.__init__()` accepts optional `event_bus: EventBus | None` parameter
- [x] `_on_worker_complete()` emits `parallel.worker_completed` event using flat dict format with `"event"` and `"ts"` keys
- [x] Event payload includes `issue_id`, `worker_name`, `status`, and `duration_seconds`
- [x] Both CLI construction sites thread `event_bus` (`cli/parallel.py:224`, `cli/sprint/run.py:387`)
- [x] Tests verify emission on success and failure paths
- [x] No emission when `event_bus` is `None` (backward compatibility)

## Impact

- **Priority**: P4 - Nice-to-have observability; parallel runs work without events
- **Effort**: Small - Single function modification plus optional parameter threading
- **Risk**: Low - Additive change behind optional parameter; no behavior change when EventBus absent
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `__init__()` at line 60 (add `event_bus` param), `_on_worker_complete()` at line 830 (add emission)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py:224` — `main_parallel()` constructs `ParallelOrchestrator`; needs to thread `event_bus`
- `scripts/little_loops/cli/sprint/run.py:387` — sprint runner constructs `ParallelOrchestrator`; also needs `event_bus`
- `scripts/little_loops/parallel/worker_pool.py:188-190` — `_handle_completion()` calls `_on_worker_complete()` as done-callback from thread pool

### Similar Patterns
- `scripts/little_loops/fsm/persistence.py:344,394` — `PersistentExecutor` owns EventBus, emits via `_handle_event()` (primary FEAT-911 pattern)
- `scripts/little_loops/cli/loop/_helpers.py:484-489` — CLI registers observer onto executor's bus via `executor.event_bus.register(display_progress)`
- ENH-919 (EventBus in issue lifecycle) and ENH-920 (EventBus in StateManager) — follow same optional injection wiring pattern

### Tests
- `scripts/tests/test_orchestrator.py:131` — existing orchestrator fixture with mocked subcomponents
- `scripts/tests/test_orchestrator.py:1231` — existing `_on_worker_complete` test class (add emission assertions here)
- `scripts/tests/test_events.py:97-168` — EventBus test patterns (list-collector + lambda)

### Documentation
- `docs/reference/API.md` — document `parallel.worker_completed` event

### Configuration
- N/A

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Parallel orchestrator design |
| architecture | docs/reference/API.md | EventBus API reference |

## Labels

`enhancement`, `captured`, `extension-system`

---

## Resolution

**Completed** | 2026-04-02

### Changes Made
- Added `event_bus: EventBus | None = None` parameter to `ParallelOrchestrator.__init__()` (`orchestrator.py:68`)
- Added `parallel.worker_completed` event emission in `_on_worker_complete()` after shared trailing logic (`orchestrator.py:912-920`)
- Threaded `EventBus` through `cli/parallel.py` and `cli/sprint/run.py` construction sites
- Added 3 tests: success emission, failure emission, backward compatibility (no bus)

### Verification
- 108 tests pass, lint clean, mypy clean

## Status

**Completed** | Created: 2026-04-02 | Completed: 2026-04-02 | Priority: P4

## Session Log
- `/ll:confidence-check` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b679f3b-da40-413e-ade8-ef41c109581e.jsonl`
- `/ll:refine-issue` - 2026-04-02T18:55:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/562ae113-f540-4eb1-854f-8e2587153d41.jsonl`
- `/ll:format-issue` - 2026-04-02T18:47:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/41b7e13f-e7a5-4e5d-9839-ca0cca6a202b.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ec33f5e-0af1-4604-bdc4-0c4331282e3e.jsonl`

- `/ll:ready-issue` - 2026-04-02T20:47:27 - `unknown-session`
