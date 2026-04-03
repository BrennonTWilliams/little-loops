---
discovered_date: 2026-04-02
discovered_by: capture-issue
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
- `scripts/little_loops/extension.py` — No changes needed to `ExtensionLoader` currently since extensions are wired to the bus externally; however, if the loader gains bus-wiring responsibility, `load_all()` (line 114) would need to pass `event_filter`

### Dependent Files (Callers/Importers)
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
7. **Add tests** — filter matching with `fnmatch` patterns (`fsm.*`, `issue.*`), multi-pattern list, `None` filter (all events), unregister with filters, edge cases (empty string pattern, no matching events)
8. **Run full test suite**: `python -m pytest scripts/tests/test_events.py scripts/tests/test_extension.py -v`

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

### ExtensionLoader Is Not Wired to Any Live EventBus

`ExtensionLoader.load_all()` returns `list[LLExtension]` instances, but **no CLI entry point** calls `bus.register(ext.on_event)` for loaded extensions. The issue's Step 4 ("Update `ExtensionLoader` to wire filters from extensions") assumes wiring exists, but it doesn't. The `event_filter` attribute on `LLExtension` and the `ExtensionLoader` reading it are only useful once end-to-end wiring is implemented. Consider either: (a) implementing the wiring as part of this ENH, or (b) deferring the `event_filter` Protocol attribute until the wiring exists and scoping this ENH to just `EventBus.register(filter=...)`.

### PersistentExecutor Backward-Compat Accessor

`PersistentExecutor._on_event` property (`persistence.py:349`) accesses `self.event_bus._observers[0]` directly. If `_observers` changes from `list[EventCallback]` to `list[tuple[EventCallback, ...]]`, this accessor must be updated to extract the callback from the tuple. This is internal code so the change is safe.

### Current register() Call Sites

Only **two** call sites for `EventBus.register()`:
1. `scripts/little_loops/cli/loop/_helpers.py:487` — progress display callback (wants all events)
2. `scripts/little_loops/fsm/persistence.py:356` — backward-compat setter (wants all events)

Both pass no filter today, confirming that defaulting `filter=None` preserves current behavior with zero migration.

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

**Open** | Created: 2026-04-02 | Priority: P4

## Session Log
- `/ll:refine-issue` - 2026-04-03T00:31:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5913db88-19b3-455b-8448-97664c8c42f8.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/997b167f-013b-46d4-a03f-9ff27d26a2a1.jsonl`
