# ENH-926: Add Topic-Based Event Filtering for Extensions

**Date**: 2026-04-02  
**Issue**: ENH-926  
**Action**: improve  
**Status**: Complete

---

## Summary

Add optional `filter` parameter to `EventBus.register()` so extensions can subscribe to specific event namespaces via glob patterns. Update `LLExtension` Protocol with `event_filter` attribute. Update `wire_extensions()` to read it.

## Confidence Gate

Score: 90/100 (threshold 70) — PASS

## Research Findings

- `_observers`: `list[EventCallback]` at `events.py:74`
- `register()`: `events.py:77-79`, no filter param
- `unregister()`: `events.py:81-86`, removes by identity
- `emit()`: `events.py:93-110`, iterates all observers unconditionally
- `PersistentExecutor._on_event` getter: `persistence.py:349`, accesses `_observers[0]` directly
- `PersistentExecutor._on_event` setter: `persistence.py:354`, calls `_observers.clear()` then `register()`
- `wire_extensions()`: `extension.py:158`, `bus.register(_make_callback(ext))`
- FSM events are bare (no namespace), others use dotted namespaces
- Decision: Document Option B (FSM bare names), no renaming in scope

## Implementation Steps

### Phase 0: Write Tests (Red)

New tests in `test_events.py`:
1. `test_filter_single_pattern` — filter="issue.*" receives `issue.closed`, blocks `state_enter`
2. `test_filter_list_of_patterns` — filter=["issue.*", "parallel.*"] receives both, blocks `state_enter`
3. `test_filter_none_is_default_receives_all` — no filter arg → receives every event
4. `test_filter_no_match_skips_callback` — filter="issue.*" on `state_enter` → 0 calls
5. `test_unregister_with_filter` — register with filter, unregister by callback, stops receiving
6. `test_filter_exact_match_no_wildcard` — filter="state_enter" matches exactly, blocks `state_exit`
7. `test_filter_wildcard_prefix` — filter="state_*" matches state_enter and state_exit

New tests in `test_extension.py`:
8. `test_wire_extensions_passes_event_filter` — ext with `event_filter="issue.*"` only receives matching events
9. `test_wire_extensions_no_event_filter_receives_all` — ext without `event_filter` receives all events

### Phase 1: Update events.py

1. Add `import fnmatch` at top
2. Change `_observers: list[EventCallback]` → `list[tuple[EventCallback, list[str] | None]]`
3. Update `register()` — add `filter: str | list[str] | None = None`, normalize to `list[str] | None`, store tuple
4. Update `unregister()` — iterate tuples, find by callback identity, del by index
5. Update `emit()` — unpack `(observer, filter_patterns)`, skip if not matching

### Phase 2: Update persistence.py

1. `_on_event` getter (line 349): `_observers[0]` → `_observers[0][0]`
2. `_on_event` setter (line 354): `_observers.clear()` still works; `register()` call unchanged

### Phase 3: Update extension.py

1. Add `event_filter: str | list[str] | None` to `LLExtension` Protocol
2. Update `wire_extensions()` line 158: pass `filter=getattr(ext, 'event_filter', None)` to `bus.register()`

### Phase 4: Update docs

- `docs/reference/API.md`: update `register()` signature and add filter note
- `docs/ARCHITECTURE.md`: add event filtering note

## Success Criteria

- [x] All new filter tests pass (8 new event filter + 2 new extension filter = 10 new tests)
- [x] All existing EventBus tests (14) still pass
- [x] All existing extension tests (11) still pass
- [x] `PersistentExecutor._on_event` getter/setter work correctly with new storage
- [x] `wire_extensions()` forwards `event_filter` from extension to bus
- [x] API docs updated with filter param
- [x] Lint: clean
- [x] mypy: clean

## Design Decisions

- **Filter shadowing built-in**: `filter` as param name shadows Python's `filter()` built-in, matching the issue spec exactly. Acceptable for API clarity.
- **FSM events**: Not renaming bare FSM event names (out of scope). Documented in API.
- **getattr fallback**: `getattr(ext, 'event_filter', None)` used in `wire_extensions()` for runtime-checkable Protocol safety.
