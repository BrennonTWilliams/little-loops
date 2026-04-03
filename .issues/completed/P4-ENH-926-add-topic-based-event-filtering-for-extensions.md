---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 86
---

# ENH-926: Add Topic-Based Event Filtering for Extensions

## Summary

Add an optional event type filter to `EventBus.register()` so extensions can subscribe to specific event namespaces (e.g., `fsm.*`, `issue.*`) instead of receiving every event from every subsystem.

## Current Behavior

`EventBus.register(callback)` registers a callback that receives **all** events from all producers. An extension that only cares about FSM state transitions still receives issue lifecycle events, parallel worker events, and state manager events. There is no filtering mechanism.

## Expected Behavior

Extensions can declare interest in specific event prefixes:

```python
# Subscribe to only FSM events
bus.register(my_callback, filter="fsm.*")

# Subscribe to FSM and issue events
bus.register(my_callback, filter=["fsm.*", "issue.*"])

# Subscribe to everything (current behavior, remains the default)
bus.register(my_callback)
```

The `LLExtension` Protocol could optionally declare a class-level `event_filter` attribute that the `ExtensionLoader` reads when wiring extensions to the bus.

## Motivation

As more subsystems emit events (now 4 producers), unfiltered dispatch has two costs:

1. **Performance** — every observer callback is invoked for every event, even when irrelevant. With cross-process transports (FEAT-918), unnecessary serialization and network I/O compounds this.
2. **Ergonomics** — extension authors must add their own `if event.type.startswith("fsm.")` guard at the top of `on_event`, which is boilerplate that the bus should handle.

## Proposed Solution

1. Add an optional `filter` parameter to `EventBus.register()` accepting a string or list of glob patterns
2. In `EventBus.emit()`, skip observers whose filter doesn't match the event type
3. Use `fnmatch` for pattern matching (already in stdlib) — supports `fsm.*`, `issue.move_to_*`, etc.
4. Optionally add an `event_filter` class attribute to the `LLExtension` Protocol (with a default of `None` meaning "all events")
5. Update `ExtensionLoader` to read `event_filter` when registering extensions

## API/Interface

```python
class EventBus:
    def register(
        self,
        callback: EventCallback,
        filter: str | list[str] | None = None,
    ) -> None: ...

class LLExtension(Protocol):
    event_filter: str | list[str] | None = None
    def on_event(self, event: LLEvent) -> None: ...
```

## Integration Map

### Files to Modify
- `scripts/little_loops/events.py` — Add `filter` param to `EventBus.register()` (line 77), add filter check in `EventBus.emit()` (line 93), store filter patterns alongside observers in `_observers` (line 74)
- `scripts/little_loops/extension.py` — Add `event_filter` attribute to `LLExtension` Protocol (line 29)
- `scripts/little_loops/extension.py` — Update `wire_extensions()` (line 158) to read `ext.event_filter` and pass it to `bus.register()` — FEAT-927 completed wiring, making this step immediately actionable

### Dependent Files (Callers/Importers)
- `scripts/little_loops/extension.py:158` — `wire_extensions()` calls `bus.register(_make_callback(ext))` — update to pass `getattr(ext, 'event_filter', None)` as filter argument
- `scripts/little_loops/cli/loop/_helpers.py:487` — calls `executor.event_bus.register(display_progress)` — no filter needed (progress display wants all events)
- `scripts/little_loops/fsm/persistence.py:356` — backward-compat `_on_event` setter calls `self.event_bus.register(callback)` — update to preserve no-filter default
- `scripts/little_loops/fsm/persistence.py:349` — `_on_event` getter accesses `_observers[0]` directly — must update if observer storage structure changes
- `scripts/little_loops/issue_manager.py:735` — creates `EventBus()` instance — no change needed
- `scripts/little_loops/cli/parallel.py:225` — creates `EventBus()` instance — no change needed

### Similar Patterns
- `scripts/little_loops/git_operations.py:303-319` — existing `fnmatch` usage for gitignore pattern matching; same stdlib module proposed for event filtering

### Tests
- `scripts/tests/test_events.py` — existing EventBus tests (14 tests covering register/emit/unregister/file_sink/isolation)
- `scripts/tests/test_extension.py` — existing extension/loader tests (11 tests)
- New tests needed for: filter matching, wildcard patterns, multi-pattern filters, default no-filter behavior, `event_filter` Protocol attribute

### Documentation
- `docs/reference/API.md` — EventBus and extension API reference; update `register()` signature
- `docs/ARCHITECTURE.md` — event persistence patterns section

## Implementation Steps

1. **Update observer storage** in `EventBus.__init__()` — change `_observers: list[EventCallback]` to `_observers: list[tuple[EventCallback, list[str] | None]]` to store filter patterns alongside callbacks
2. **Add `filter` parameter** to `EventBus.register()` accepting `str | list[str] | None`; normalize to `list[str] | None` internally
3. **Add filter check** in `EventBus.emit()` — before calling observer, check if the event dict's `"event"` key matches any of the observer's filter patterns using `fnmatch.fnmatch()`; `None` filter means match all (current behavior)
4. **Update `EventBus.unregister()`** to find observer by callback identity in the tuple list
5. **Update backward-compat accessor** in `PersistentExecutor._on_event` property (persistence.py:349) to handle new tuple storage
6. **Add `event_filter` to `LLExtension` Protocol** as `event_filter: str | list[str] | None` with default `None`
7. **Update `wire_extensions()`** in `extension.py:158` — change `bus.register(_make_callback(ext))` to `bus.register(_make_callback(ext), filter=getattr(ext, 'event_filter', None))` so the Protocol attribute takes effect
8. **Add tests** — filter matching with `fnmatch` patterns (`fsm.*`, `issue.*`), multi-pattern list, `None` filter (all events), unregister with filters, edge cases (empty string pattern, no matching events); add `wire_extensions` filter test following the capture-list pattern in `test_extension.py:138-159`
9. **Run full test suite**: `python -m pytest scripts/tests/test_events.py scripts/tests/test_extension.py -v`

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Event Type Naming Inconsistency

**Critical finding**: The issue assumes `fsm.*` as a filter prefix, but FSMExecutor (`scripts/little_loops/fsm/executor.py:1006-1014`) emits **un-namespaced** event types: `loop_start`, `state_enter`, `action_start`, `action_output`, `action_complete`, `evaluate`, `route`, `loop_complete`, `handoff_detected`. Other producers are namespaced:
- StateManager: `state.issue_completed`, `state.issue_failed`
- IssueLifecycle: `issue.failure_captured`, `issue.closed`, `issue.completed`, `issue.deferred`
- ParallelOrchestrator: `parallel.worker_completed`

**Implication**: Either (a) add `fsm.` prefix to executor events in a separate ENH before this one, or (b) document that FSM events must be matched with bare names (`state_enter`, `loop_*`) while other subsystems use dotted namespaces. Option (a) is cleaner but a breaking change for existing event consumers.

### Duplicate EventCallback Type

`EventCallback` is defined in **two places**:
- `scripts/little_loops/events.py:24` — `Callable[[dict[str, Any]], None]`
- `scripts/little_loops/fsm/executor.py:103` — identical definition

Both are `Callable[[dict[str, Any]], None]` (takes raw dict, not `LLEvent`). The extension Protocol uses `LLEvent` in `on_event()`, but the EventBus dispatches raw dicts. This means filtering must operate on the raw dict's `"event"` key, not on `LLEvent.type`.

### ExtensionLoader Wiring — RESOLVED by FEAT-927

**FEAT-927 has been completed.** `wire_extensions(bus, config_paths)` at `extension.py:132-161` now wires extensions to a live `EventBus` in all CLI entry points: `loop/run.py:159`, `loop/lifecycle.py:260`, `parallel.py:228`, `sprint/run.py:391`. The `event_filter` Protocol attribute is **immediately actionable** — `wire_extensions()` uses a `_make_callback(ext)` closure factory at `extension.py:152-156` and calls `bus.register(_make_callback(ext))` at line 158, which is precisely where `ext.event_filter` should be read and forwarded to `bus.register()`.

### PersistentExecutor Backward-Compat Accessor

`PersistentExecutor._on_event` property (`persistence.py:349`) accesses `self.event_bus._observers[0]` directly. If `_observers` changes from `list[EventCallback]` to `list[tuple[EventCallback, ...]]`, this accessor must be updated to extract the callback from the tuple. This is internal code so the change is safe.

### Current register() Call Sites

**Four** production call sites for `EventBus.register()`:
1. `scripts/little_loops/extension.py:158` — `wire_extensions()` registers per-extension closure for each loaded extension (key site to add `filter=ext.event_filter`)
2. `scripts/little_loops/cli/loop/_helpers.py:487` — progress display callback (wants all events, no filter)
3. `scripts/little_loops/fsm/persistence.py:356` — backward-compat `_on_event` setter (wants all events, no filter)
4. `scripts/little_loops/events.py:79` — the definition itself

All call sites pass no filter today; defaulting `filter=None` preserves current behavior with zero migration at all sites except `extension.py:158` where opt-in filtering is the goal.

### Additional Direct `_observers` Access Locations

**Verified (2026-04-02)**: Only `persistence.py:349` accesses `_observers` directly. The files previously flagged for audit (`cli/loop/lifecycle.py`, `cli/loop/info.py`, `git_operations.py`, `subprocess_utils.py`) do **not** access `_observers` — the `event_filter` reference in `info.py` is a local display variable, unrelated. No additional audit needed; update only `persistence.py:349`.

### FSM Event Naming Inconsistency — Implementation Decision

FSMExecutor emits bare event types (`loop_start`, `state_enter`, `action_start`, etc.) while other producers use dotted namespaces (`state.issue_completed`, `issue.failure_captured`, `parallel.worker_completed`). A `filter="fsm.*"` glob will **not** match bare names.

**Decision**: Implement Option B — document that FSM events must be matched with bare names (e.g., `filter=["loop_start", "state_enter"]` or `filter="loop_*"`) in the API docs and implementation notes. Renaming FSM executor event types to add `fsm.` prefix is a separate breaking change and out of scope here.

## Impact

- **Priority**: P4 - Quality-of-life improvement; becomes more important as event volume and extension count grow
- **Effort**: Small - Core change is ~20 lines in `events.py` plus tests; additional complexity from backward-compat accessor update in `persistence.py`
- **Risk**: Low - Backwards compatible; no filter = current behavior. Only 2 existing `register()` call sites, both want all events.
- **Breaking Change**: No (observer storage change is internal; public API only adds optional param)
- **Depends On**: None (works with current in-process bus; benefits compound with FEAT-918)
- **Consider**: Namespacing FSM executor events with `fsm.` prefix before or alongside this work to make glob filtering consistent across all producers

## Scope Boundaries

- **In scope**: Filter on event type string only; glob-style patterns
- **Out of scope**: Content-based filtering (filtering on payload values), priority-based ordering of observers

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Event persistence patterns and FSM executor design |
| architecture | docs/reference/API.md | EventBus and extension API reference |

## Labels

`enh`, `extension-api`, `captured`

---

## Status

**Completed** | Created: 2026-04-02 | Resolved: 2026-04-02 | Priority: P4

## Resolution

Implemented topic-based event filtering for `EventBus` and the `LLExtension` Protocol.

### Changes

- **`scripts/little_loops/events.py`**: Added `filter: str | list[str] | None = None` parameter to `EventBus.register()`. Observer storage changed from `list[EventCallback]` to `list[tuple[EventCallback, list[str] | None]]`. `emit()` now uses `fnmatch.fnmatch()` to skip non-matching observers. `unregister()` finds callback by identity in tuple list.
- **`scripts/little_loops/fsm/persistence.py`**: Updated `PersistentExecutor._on_event` getter to extract callback from new tuple storage (`_observers[0][0]`).
- **`scripts/little_loops/extension.py`**: Added `event_filter: str | list[str] | None` to `LLExtension` Protocol. Updated `wire_extensions()` to pass `filter=getattr(ext, 'event_filter', None)` to `bus.register()`.
- **`docs/reference/API.md`**: Updated `register()` signature and added filter usage examples with event namespace conventions.
- **`scripts/tests/test_events.py`**: Added 8 new `TestEventBusFilter` tests (single pattern, list, None default, no match, unregister, exact match, wildcard, mixed).
- **`scripts/tests/test_extension.py`**: Added 2 new `TestWireExtensions` filter tests.

### Verification

- 44/44 tests in `test_events.py` + `test_extension.py` pass
- Full test suite: 4075 passed, 3 pre-existing failures in unrelated `test_cli.py`
- ruff lint: clean, mypy: clean

## Session Log
- `/ll:ready-issue` - 2026-04-03T01:29:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/674000f4-3c4b-4a7c-a50c-1de8dcc7434b.jsonl`
- `/ll:confidence-check` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb0c5f9d-1037-4e99-9314-fed616595469.jsonl`
- `/ll:refine-issue` - 2026-04-03T01:21:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e1d3e02-18f1-4c88-9691-b73ab942451c.jsonl`
- `/ll:refine-issue` - 2026-04-03T00:31:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5913db88-19b3-455b-8448-97664c8c42f8.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/997b167f-013b-46d4-a03f-9ff27d26a2a1.jsonl`
