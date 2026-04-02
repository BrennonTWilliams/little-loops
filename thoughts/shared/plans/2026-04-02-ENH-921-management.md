# ENH-921: Wire EventBus Emission into Parallel Orchestrator

## Status: PLANNING
Created: 2026-04-02

## Research Summary

- **EventBus** lives at `scripts/little_loops/events.py` (not `extensions/events.py`)
- **`emit()`** takes a single `dict[str, Any]` — flat dict with `"event"` and `"ts"` keys
- **`_on_worker_complete()`** at `orchestrator.py:830-908` — shared trailing logic at lines 900-908
- **`__init__()`** at `orchestrator.py:60-67` — 5 params, no `event_bus` yet
- **`WorkerResult`** has `issue_id`, `success`, `worktree_path`, `duration` — no `worker_id`
- **`_iso_now()`** pattern used in `issue_lifecycle.py:25-27`, `persistence.py:46-48` — `datetime.now(UTC).isoformat()`
- **ENH-470** (refactor parallel god classes) is still open P4 — minimal conflict risk for additive change
- **ENH-919** pattern in `issue_lifecycle.py` is the template: optional `event_bus: EventBus | None = None` + guard `if self._event_bus:`

## Implementation Plan

### Phase 0: Write Tests (Red)

Add tests to `test_orchestrator.py` in the existing `TestOnWorkerComplete` class:

1. **`test_on_worker_complete_emits_event_on_success`** — Create EventBus, register list-collector, run success path, assert `parallel.worker_completed` emitted with correct fields
2. **`test_on_worker_complete_emits_event_on_failure`** — Same but failure path, assert `status: "failure"`
3. **`test_on_worker_complete_no_emission_without_event_bus`** — No EventBus set, verify no errors (backward compat)

### Phase 1: Add EventBus to ParallelOrchestrator

**File: `scripts/little_loops/parallel/orchestrator.py`**

1. Add imports: `from datetime import UTC` and `from little_loops.events import EventBus`
2. Add `event_bus: EventBus | None = None` parameter to `__init__()` after `wave_label`
3. Store as `self._event_bus = event_bus` in `__init__` body
4. In `_on_worker_complete()`, after the shared trailing logic (line 908), emit:
   ```python
   if self._event_bus:
       self._event_bus.emit({
           "event": "parallel.worker_completed",
           "ts": datetime.now(UTC).isoformat(),
           "issue_id": result.issue_id,
           "worker_name": result.worktree_path.name,
           "status": "success" if result.success else "failure",
           "duration_seconds": result.duration,
       })
   ```

### Phase 2: Thread event_bus through CLI construction sites

1. **`scripts/little_loops/cli/parallel.py:224`** — Pass `event_bus=event_bus` (need to create/obtain EventBus instance)
2. **`scripts/little_loops/cli/sprint/run.py:387`** — Same pattern

For both CLI sites, check if an EventBus is already available in scope; if not, create one conditionally.

### Phase 3: Verify

- `python -m pytest scripts/tests/test_orchestrator.py -v`
- `ruff check scripts/`
- `python -m mypy scripts/little_loops/`

## Success Criteria

- [ ] Tests pass for success and failure emission paths
- [ ] No emission when `event_bus` is `None`
- [ ] Both CLI sites thread `event_bus`
- [ ] All verification passes (tests, lint, types)
