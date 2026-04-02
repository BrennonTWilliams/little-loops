# FEAT-911: Extension Architecture — Implementation Plan

**Issue**: `.issues/features/P4-FEAT-911-extension-architecture-ll-as-protocol-not-product.md`
**Created**: 2026-04-02
**Confidence**: 95/100 (readiness) / 54/100 (outcome — mitigated by scoping to minimal acceptance criteria)

## Scope Decision

The acceptance criteria are deliberately minimal:
1. Extension contract documented as a published schema
2. At least one emission point wired to the event bus
3. Reference extension (no-op logger) demonstrates the API works
4. No breaking changes when no extensions registered

**In scope**: Core EventBus + LLExtension Protocol + FSM wiring + reference extension + config/entry points
**Deferred**: Issue lifecycle emission, StateManager emission, parallel orchestrator emission (per confidence check: avoid wide change surface; ENH-470 conflict risk on orchestrator.py)

## Architecture

```
EventBus (multi-observer, in-process)
├── PersistentExecutor._handle_event  (existing — primary: JSONL persistence + state saves)
├── display_progress closure           (existing — optional: terminal output)
├── ExtensionLoader-discovered plugins (new — entry_points or config-based)
└── File sink to .ll/events.jsonl      (new — unified append-only log)
```

**Event envelope** (unchanged from existing FSM format):
```python
{"event": "fsm.state_enter", "ts": "2026-04-02T12:00:00Z", "state": "build", "iteration": 1}
```

**Key design decision**: EventBus replaces the single `_on_event` slot on PersistentExecutor with a list of observers. The existing `_handle_event` callback remains the primary event_callback on FSMExecutor — EventBus sits inside PersistentExecutor as its mechanism for dispatching to secondary observers.

## Phase 0: Write Tests (Red)

### New test files

**`scripts/tests/test_events.py`** — Unit tests for `LLEvent` dataclass + `EventBus`:
- `test_ll_event_creation` — construct with type, timestamp, payload
- `test_ll_event_to_dict` — serializes to flat dict with event/ts/payload keys
- `test_ll_event_from_dict` — deserializes correctly
- `test_ll_event_from_raw_event` — converts existing `{"event": ..., "ts": ...}` format
- `test_event_bus_register_and_emit` — register callback, emit event, callback receives it
- `test_event_bus_multiple_observers` — all observers receive each event
- `test_event_bus_unregister` — removed observer stops receiving
- `test_event_bus_emit_no_observers` — no error when empty
- `test_event_bus_observer_exception_isolated` — one observer's exception doesn't block others
- `test_event_bus_file_sink` — events appended to JSONL file
- `test_event_bus_file_sink_reads_back` — round-trip via read_events

**`scripts/tests/test_extension.py`** — Unit tests for `LLExtension` Protocol + `ExtensionLoader`:
- `test_ll_extension_protocol_satisfied` — a class with `on_event(LLEvent)` satisfies the Protocol
- `test_ll_extension_protocol_not_satisfied` — a class missing on_event doesn't
- `test_noop_logger_extension` — the reference extension logs events
- `test_extension_loader_from_config` — loads extension by dotted module path
- `test_extension_loader_empty_config` — returns empty list when no extensions configured
- `test_extension_loader_invalid_path` — warns/skips on bad module path
- `test_extension_loader_entry_points` — discovers via importlib.metadata entry points

### Existing test files to update

**`scripts/tests/test_fsm_persistence.py`** — Add tests for EventBus in PersistentExecutor:
- `test_persistent_executor_event_bus_register` — register observer via `executor.event_bus.register()`
- `test_persistent_executor_event_bus_replaces_on_event` — backward compat: `_on_event` property delegates to bus

**`scripts/tests/test_ll_loop_display.py`** — Update mock executor `_on_event` usage:
- Mock executor classes at lines 39 and 1898 use `self._on_event` directly
- These must continue to work (backward compat for test mocks)

## Phase 1: Core — `events.py`

**Create `scripts/little_loops/events.py`**

```python
@dataclass
class LLEvent:
    type: str           # e.g. "fsm.state_enter", "fsm.loop_complete"
    timestamp: str      # ISO 8601
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"event": self.type, "ts": self.timestamp, **self.payload}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLEvent:
        event_type = data.pop("event", data.pop("type", "unknown"))
        ts = data.pop("ts", data.pop("timestamp", ""))
        return cls(type=event_type, timestamp=ts, payload=data)

    @classmethod
    def from_raw_event(cls, raw: dict[str, Any]) -> LLEvent:
        """Convert existing executor event dict to LLEvent."""
        copy = dict(raw)
        return cls.from_dict(copy)


class EventBus:
    """Multi-observer event dispatcher."""

    def __init__(self) -> None:
        self._observers: list[EventCallback] = []

    def register(self, callback: EventCallback) -> None: ...
    def unregister(self, callback: EventCallback) -> None: ...
    def emit(self, event: dict[str, Any]) -> None:
        """Dispatch to all observers. Isolate exceptions."""
        ...
```

Follow patterns:
- `EventCallback` type from `executor.py:103`
- `_emit()` envelope shape from `executor.py:1006-1014`
- `to_dict()`/`from_dict()` from `parallel/types.py:92-135`

## Phase 2: Core — `extension.py`

**Create `scripts/little_loops/extension.py`**

```python
class LLExtension(Protocol):
    """Protocol for little-loops extensions."""
    def on_event(self, event: LLEvent) -> None: ...

class NoopLoggerExtension:
    """Reference extension that logs events to a file."""
    def __init__(self, log_path: Path) -> None: ...
    def on_event(self, event: LLEvent) -> None: ...

class ExtensionLoader:
    """Discover and load extensions from config and entry points."""
    @staticmethod
    def from_config(extension_paths: list[str]) -> list[LLExtension]: ...
    @staticmethod
    def from_entry_points() -> list[LLExtension]: ...
    @staticmethod
    def load_all(config_paths: list[str] | None = None) -> list[LLExtension]: ...
```

Follow patterns:
- `ActionRunner` Protocol from `executor.py:106-127`
- `importlib.metadata.entry_points(group="little_loops.extensions")`

## Phase 3: Wire EventBus into PersistentExecutor

**Modify `scripts/little_loops/fsm/persistence.py`**

Changes to `PersistentExecutor.__init__` (~line 343):
- Replace `self._on_event: EventCallback | None = None` with `self.event_bus = EventBus()`

Changes to `PersistentExecutor._handle_event` (~line 380-382):
- Replace `if self._on_event is not None: self._on_event(event)` with `self.event_bus.emit(event)`

Add backward-compat property:
```python
@property
def _on_event(self) -> EventCallback | None:
    return self.event_bus._observers[0] if self.event_bus._observers else None

@_on_event.setter
def _on_event(self, callback: EventCallback | None) -> None:
    # Backward compat: clear observers and add this one
    self.event_bus._observers.clear()
    if callback is not None:
        self.event_bus.register(callback)
```

This ensures `executor._on_event = display_progress` in `_helpers.py:486` and test mocks continue to work without changes.

## Phase 4: Update CLI wiring

**Modify `scripts/little_loops/cli/loop/_helpers.py`** (~line 484-486):
- Change `executor._on_event = display_progress` to `executor.event_bus.register(display_progress)`

## Phase 5: Config + Entry Points

**Modify `config-schema.json`** — Add `extensions` property (after `cli` block):
```json
"extensions": {
  "type": "array",
  "items": {"type": "string"},
  "default": [],
  "description": "Extension module paths to load (e.g. 'my_package.MyExtension')"
}
```

**Modify `scripts/pyproject.toml`** — Add entry points group between lines 62-63:
```toml
[project.entry-points."little_loops.extensions"]
# Example: my_ext = "my_package:MyExtension"
```

## Phase 6: Public Exports

**Modify `scripts/little_loops/__init__.py`** — Add imports and exports for `LLEvent`, `EventBus`, `LLExtension`

**Modify `scripts/little_loops/fsm/__init__.py`** — Add `EventCallback` to exports (already defined in executor.py, should be publicly available)

## Phase 7: Documentation

**Modify `docs/reference/API.md`** — Add Extension API section documenting `LLEvent`, `EventBus`, `LLExtension`, `ExtensionLoader`

## Success Criteria

- [x] Extension contract documented as a published schema → `LLExtension` Protocol + `LLEvent` dataclass + API docs
- [x] At least one emission point wired to the event bus → FSM events flow through EventBus
- [x] Reference extension (no-op logger) demonstrates API works → `NoopLoggerExtension`
- [x] No breaking changes → `_on_event` backward compat property; existing tests pass unchanged

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `scripts/little_loops/events.py` | CREATE | LLEvent dataclass + EventBus |
| `scripts/little_loops/extension.py` | CREATE | LLExtension Protocol + ExtensionLoader + NoopLoggerExtension |
| `scripts/little_loops/fsm/persistence.py` | MODIFY | Replace _on_event slot with EventBus; add compat property |
| `scripts/little_loops/cli/loop/_helpers.py` | MODIFY | Use event_bus.register() instead of _on_event assignment |
| `scripts/little_loops/__init__.py` | MODIFY | Add extension exports |
| `scripts/little_loops/fsm/__init__.py` | MODIFY | Export EventCallback |
| `scripts/pyproject.toml` | MODIFY | Add entry_points group |
| `config-schema.json` | MODIFY | Add extensions array property |
| `docs/reference/API.md` | MODIFY | Add Extension API section |
| `scripts/tests/test_events.py` | CREATE | EventBus + LLEvent tests |
| `scripts/tests/test_extension.py` | CREATE | Extension Protocol + Loader tests |
| `scripts/tests/test_fsm_persistence.py` | MODIFY | Add EventBus integration tests |
