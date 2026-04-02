# ENH-920: Wire EventBus Emission into StateManager — Implementation Plan

## Issue Summary
Add EventBus event emission to `StateManager.mark_completed()` and `StateManager.mark_failed()` so extensions can observe processing state transitions during ll-auto runs.

## Research Findings

- `StateManager` (`state.py:78-197`) has no event infrastructure — only `state_file`, `logger`, `_state`
- `mark_completed` (`state.py:175-187`): appends to completed list, stores timing, resets phase, calls `save()`
- `mark_failed` (`state.py:189-197`): writes to failed dict, calls `save()`
- `AutoManager.__init__` (`issue_manager.py:734`) is the **only** `StateManager` construction site
- `EventBus` (`events.py:66-110`): `.emit(dict)` dispatches to observers, exceptions are caught per-observer
- `_emit` helper pattern (`fsm/executor.py:1006-1014`): builds `{"event": type, "ts": _iso_now(), **data}`
- No-op guard pattern (`fsm/executor.py:370`): `event_callback or (lambda _: None)` — but EventBus has `.emit()` not a bare callable, so we'll use `if self._event_bus:` guard instead
- `_iso_now()` is defined as module-level helper in both `executor.py:332` and `persistence.py:46`
- `state.py` imports `from datetime import datetime` (no `UTC`) — needs `UTC` added

## Design Decisions

1. **Guard style**: Use `if self._event_bus:` guard in `_emit` helper rather than no-op pattern, since EventBus is an object with `.emit()` method (not a bare callable like `event_callback`)
2. **Timestamp**: Define `_iso_now()` as module-level helper in `state.py` matching the pattern in `executor.py:332-334`
3. **Event names**: `state.issue_completed` and `state.issue_failed` with `state.` namespace prefix
4. **Payload format**: Flat dict `{"event": type, "ts": ts, ...payload}` matching `LLEvent.to_dict()` convention

## Phase 0: Write Tests (Red)

Add to `scripts/tests/test_state.py`:

1. **`test_mark_completed_emits_event`** — Create `EventBus`, register spy, construct `StateManager(file, logger, event_bus=bus)`, call `mark_completed("BUG-001")`, assert `received[0]["event"] == "state.issue_completed"` and `received[0]["issue_id"] == "BUG-001"`
2. **`test_mark_failed_emits_event`** — Same spy setup, call `mark_failed("BUG-002", "Timeout")`, assert `received[0]["event"] == "state.issue_failed"` and `received[0]["reason"] == "Timeout"`
3. **`test_no_event_bus_no_error`** — Construct `StateManager(file, logger)` (no bus), call both methods, assert no errors (backward compat)
4. **`test_event_payload_format`** — Verify flat dict has `"event"`, `"ts"`, `"issue_id"`, `"status"` keys

## Phase 1: Modify `state.py`

### 1a. Update imports (line 12)
Add `UTC` to datetime import: `from datetime import UTC, datetime`

### 1b. Add `_iso_now()` helper (after imports, before classes)
```python
def _iso_now() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()
```

### 1c. Add `EventBus` import
Add conditional import or direct import of `EventBus` from `little_loops.events`

### 1d. Modify `StateManager.__init__` (line 85)
Add `event_bus: EventBus | None = None` parameter, store as `self._event_bus = event_bus`

### 1e. Add `_emit` helper method
```python
def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
    if self._event_bus:
        self._event_bus.emit({"event": event_type, "ts": _iso_now(), **payload})
```

### 1f. Emit in `mark_completed` (after `self.save()` at line 187)
```python
self._emit("state.issue_completed", {"issue_id": issue_id, "status": "completed"})
```

### 1g. Emit in `mark_failed` (after `self.save()` at line 197)
```python
self._emit("state.issue_failed", {"issue_id": issue_id, "reason": reason, "status": "failed"})
```

## Phase 2: Wire in `issue_manager.py`

### 2a. Add EventBus import
Add `from little_loops.events import EventBus` to imports

### 2b. Create EventBus in `AutoManager.__init__` (around line 734)
```python
self.event_bus = EventBus()
self.state_manager = StateManager(config.get_state_file(), self.logger, event_bus=self.event_bus)
```

Expose as `self.event_bus` so CLI consumers can register observers.

## Success Criteria
- [x] Tests written (Red phase)
- [ ] `mark_completed()` emits `state.issue_completed` event
- [ ] `mark_failed()` emits `state.issue_failed` event
- [ ] Events include issue ID and relevant metadata
- [ ] EventBus wired from `AutoManager.__init__`
- [ ] Backward compatible (no bus = no error)
- [ ] All tests pass
- [ ] Lint clean
- [ ] Type check clean
