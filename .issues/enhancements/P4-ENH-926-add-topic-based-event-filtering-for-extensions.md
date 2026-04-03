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

## Implementation Steps

1. Add `filter` parameter to `EventBus.register()` with internal storage of compiled patterns
2. Update `EventBus.emit()` to check filters before dispatching
3. Add `event_filter` to `LLExtension` Protocol
4. Update `ExtensionLoader` to wire filters from extensions
5. Add tests for filter matching, default behavior, and edge cases

## Impact

- **Priority**: P4 - Quality-of-life improvement; becomes more important as event volume and extension count grow
- **Effort**: Small - Core change is ~20 lines in `events.py` plus tests
- **Risk**: Low - Backwards compatible; no filter = current behavior
- **Breaking Change**: No
- **Depends On**: None (works with current in-process bus; benefits compound with FEAT-918)

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
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/997b167f-013b-46d4-a03f-9ff27d26a2a1.jsonl`
