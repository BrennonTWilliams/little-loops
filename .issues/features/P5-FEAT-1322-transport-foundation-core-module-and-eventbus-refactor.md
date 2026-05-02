---
id: FEAT-1322
priority: P5
size: Large
---

# FEAT-1322: Transport Foundation — Core Module and EventBus Refactor

## Summary

Introduce the `Transport` Protocol abstraction, implement `JsonlTransport`, refactor `EventBus` to fan out to transports, fix the `loop_resume` bypass, and wire up the config stack (`EventsConfig`, `config-schema.json`). This is the foundation half of the FEAT-918 split; the CLI wiring pass ships in FEAT-1323.

## Parent Issue

Decomposed from FEAT-918: Transport Protocol Foundation and JsonlTransport

## Context

FEAT-918 scored 11/11 on the size heuristic (13 files, 5 subsystems, outcome_confidence 53/100). The confidence check recommended splitting into two commits: (1) core module + EventBus refactor, (2) CLI wiring pass. This issue is part 1.

The `_file_sinks` / `add_file_sink()` path on `EventBus` is dead code — zero production callers, only `test_events.py:174` and `:188` exercise it. `JsonlTransport` replaces it as an additive transport, not a migration.

## Current Behavior

- `EventBus.emit()` fans out to `_observers` and `_file_sinks` (dead). No abstraction for adding sinks.
- `loop_resume` events bypass `EventBus` entirely: `persistence.py:555` writes via `append_event()` and never calls `event_bus.emit()`.
- No `EventsConfig` in the config stack; `config-schema.json` has no `events` block.

## Expected Behavior

- `Transport(Protocol, runtime_checkable)` in `scripts/little_loops/transport.py` with `send(event: dict[str, Any]) -> None` and `close() -> None`.
- `EventBus` holds `_transports: list[Transport]`; `emit()` fans out with per-transport exception isolation.
- `JsonlTransport(path: Path)` is the only transport shipped here.
- `loop_resume` flows through `EventBus.emit()`.
- `EventsConfig(transports: list[str])` dataclass; `BRConfig.events` property exposes it.
- `config-schema.json` validates `events.transports` array.

## Proposed Solution

1. Create `scripts/little_loops/transport.py` with `Transport` Protocol, `JsonlTransport`, and `wire_transports()` (registry: `{"jsonl": JsonlTransport}`; unknown names log a warning and are skipped).
2. Refactor `EventBus` in `events.py`: remove `_file_sinks` (line 76) and `add_file_sink()` (lines 102–105); add `_transports`, `add_transport()`, `close_transports()`; replace lines 124–129 with per-transport fan-out + exception isolation.
3. Add `self.event_bus.emit(resume_event)` at `persistence.py:555` (between `append_event` and `return self.run(...)`).
4. Add `PersistentExecutor.close_transports()` delegating to `self.event_bus.close_transports()`.
5. Add `EventsConfig` to `config/features.py` (single `transports: list[str]` field). Update `config/core.py` import tuple, `_parse_config()`, and `events` property.
6. Extend `config-schema.json` with an `events` block (sibling of `extensions`, after line 1035, before root `additionalProperties: false` at line 1037).

## API/Interface

```python
# scripts/little_loops/transport.py
from typing import Protocol, runtime_checkable, Any
from pathlib import Path

@runtime_checkable
class Transport(Protocol):
    def send(self, event: dict[str, Any]) -> None: ...
    def close(self) -> None: ...

class JsonlTransport:
    def __init__(self, path: Path): ...
    def send(self, event: dict[str, Any]) -> None: ...  # append JSON line
    def close(self) -> None: ...                         # no-op

def wire_transports(bus: EventBus, config: EventsConfig) -> None: ...
```

## Integration Map

### Files to Modify

- `scripts/little_loops/events.py` — drop `_file_sinks` (line 76) and `add_file_sink()` (lines 102–105); add `_transports`, `add_transport()`, `close_transports()`; replace lines 124–129 with per-transport fan-out
- `scripts/little_loops/fsm/persistence.py:555` — add `self.event_bus.emit(resume_event)` after `append_event(resume_event)` (loop_resume bypass fix)
- `scripts/little_loops/fsm/persistence.py` — add `PersistentExecutor.close_transports()` after `_on_event.setter` at line 396
- `scripts/little_loops/config/features.py` — add `EventsConfig` after `SyncConfig` (around line 357); single `transports: list[str]` field with `from_dict()` defaulting to `[]`
- `scripts/little_loops/config/core.py` — add `EventsConfig` to imports (lines 21–27); `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))` in `_parse_config()` (line 96); add `events` property (between lines 175–177)
- `config-schema.json` — add `"events": {"type": "object", "properties": {"transports": {"type": "array", "items": {"type": "string"}, "default": []}}, "additionalProperties": false}` inside top-level `properties`, after `extensions` closes at line 1035

### Tests

- `scripts/tests/test_events.py` — rewrite `test_file_sink` (line 174) and `test_file_sink_reads_back` (line 188) to use `bus.add_transport(JsonlTransport(path))`. Other 23 tests unaffected.
- `scripts/tests/test_transport.py` (new) — Protocol satisfaction (pattern: `test_extension.py:19-32`), `JsonlTransport` lifecycle, error isolation when one transport raises (pattern: `test_events.py:140-154`)
- `scripts/tests/test_config.py` — `EventsConfig` defaults + nested-key parsing (pattern: `temp_project_dir` fixture, `BRConfig(temp_project_dir)`)
- `scripts/tests/test_fsm_persistence.py:745` — extend `test_resume_emits_resume_event` to assert `EventBus.emit` was called for `loop_resume`
- `scripts/tests/test_config_schema.py` — assert `"events"` in `data["properties"]` and `"transports"` in `data["properties"]["events"]["properties"]`; pattern: `test_learning_tests_in_schema`

### Codebase Research Notes (from FEAT-918)

- **`_on_event` shim** at `persistence.py:387–396` reads `self.event_bus._observers[0][0]`. Do not reorder/remove `_observers` entries during `_file_sinks` removal or this breaks silently.
- **`emit()` two-pass structure** — Pass 1 iterates `_observers` with glob filtering. New transports match pass-2 behavior (unfiltered).
- **Pattern anchors** — `Transport` Protocol: model after `LLExtension` at `extension.py:36`. `EventsConfig.from_dict()`: model after `ScanConfig.from_dict` at `config/features.py:ScanConfig.from_dict`. `JsonlTransport.send()`: `path.parent.mkdir(parents=True, exist_ok=True)` in `__init__`, then `with open(path, "a", encoding="utf-8") as f: f.write(json.dumps(event) + "\n")` in `send()`.

### Dependent Files (informational, no changes needed here)

- `scripts/little_loops/state.py` — imports `EventBus` for type annotation only; unaffected
- `scripts/little_loops/testing.py` — `LLTestBus`; does not call `add_file_sink`; unaffected
- `scripts/little_loops/issue_lifecycle.py` — emits events; unaffected
- `scripts/little_loops/issue_manager.py` — bare `EventBus()`; explicitly out of scope

## Acceptance Criteria

- [ ] `Transport(Protocol, runtime_checkable)` defined in `scripts/little_loops/transport.py`
- [ ] `EventBus._file_sinks` and `add_file_sink()` removed; `_transports`, `add_transport()`, `close_transports()` added
- [ ] Per-transport exception isolation in `EventBus.emit()` — one transport raising does not stop others
- [ ] `JsonlTransport` implemented and satisfies `isinstance(t, Transport)`
- [ ] `loop_resume` events flow through `EventBus.emit()` (`persistence.py:555` fix)
- [ ] `EventsConfig` dataclass with `transports: list[str]` field; `BRConfig.events` property exposes it
- [ ] `config-schema.json` validates `events.transports` array
- [ ] Unknown transport names in config emit a warning and are skipped
- [ ] All existing tests pass; new `test_transport.py`, updated `test_events.py` (2 tests), `test_config.py`, `test_config_schema.py`, `test_fsm_persistence.py` extension added

## Implementation Steps

1. Create `scripts/little_loops/transport.py` with `Transport` Protocol, `JsonlTransport`, and `wire_transports()`.
2. Refactor `EventBus` in `events.py`: remove `_file_sinks`/`add_file_sink()`; add transport infrastructure; replace fan-out loop.
3. Fix `loop_resume` bypass: add `self.event_bus.emit(resume_event)` at `persistence.py:555`.
4. Add `PersistentExecutor.close_transports()` delegating to `self.event_bus.close_transports()`.
5. Add `EventsConfig` to `config/features.py`; wire into `config/core.py` (`_parse_config` + `events` property).
6. Extend `config-schema.json` with `events` block.
7. Write tests: `test_transport.py` (new), update `test_events.py` (2 tests), extend `test_fsm_persistence.py`, add `test_config.py` + `test_config_schema.py` assertions.

## Impact

- **Priority**: P5
- **Effort**: Medium
- **Risk**: Low — `_file_sinks` is dead code; observer path untouched; transports additive
- **Breaking Change**: No
- **Depends On**: FEAT-911 (completed)
- **Blocks**: FEAT-1323 (CLI wiring pass)

## Status

**Open** | Created: 2026-05-02 | Priority: P5

## Session Log
- `/ll:issue-size-review` - 2026-05-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19344c8e-9db2-4d37-b7f7-d6bf19e299d8.jsonl`
