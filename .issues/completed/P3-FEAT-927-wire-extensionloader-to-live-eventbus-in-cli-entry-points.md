---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
---

# FEAT-927: Wire ExtensionLoader to Live EventBus in CLI Entry Points

## Summary

`ExtensionLoader.load_all()` discovers and instantiates extensions, but no CLI entry point calls `bus.register(ext.on_event)` to connect loaded extensions to a live `EventBus`. This means the extension consumer path is incomplete — extensions can be defined, discovered, and loaded, but never actually receive events. This was planned as step 6 of FEAT-911 but was not implemented.

## Current Behavior

CLI entry points (`cli/loop/run.py`, `cli/loop/lifecycle.py`, `cli/parallel.py`, `cli/sprint/run.py`) create `EventBus()` instances and wire them to producers (FSMExecutor, ParallelOrchestrator, StateManager, IssueLifecycle), but never call `ExtensionLoader.load_all()` or register extension callbacks on the bus. Third-party extensions installed via entry points or configured via `ll-config.json` are silently ignored at runtime.

_Note: The loop entry point has two paths — `cli/loop/run.py:150` (fresh run) and `cli/loop/lifecycle.py:251` (resume). Both create `PersistentExecutor` which owns its own `EventBus` at `fsm/persistence.py:344`, rather than creating a standalone bus._

## Expected Behavior

CLI entry points that create an `EventBus` should also:
1. Load extensions via `ExtensionLoader.load_all(config_paths)` where `config_paths` comes from `ll-config.json`'s `extensions` key
2. Register each extension's `on_event` callback on the bus: `bus.register(ext.on_event)`
3. Handle the `LLEvent` vs raw dict boundary — `EventBus.emit()` dispatches `dict[str, Any]` but `LLExtension.on_event()` expects `LLEvent`

## Motivation

Without this wiring, the entire extension architecture (FEAT-911) is a dead API — `LLExtension`, `ExtensionLoader`, `NoopLoggerExtension`, and the entry point group `little_loops.extensions` all exist but have no runtime effect. This blocks any practical use of extensions, including ENH-926 (event filtering) and FEAT-916 (extension SDK).

## Proposed Solution

1. Add a helper function (e.g., `wire_extensions(bus, config)`) that loads extensions and registers them on a bus, wrapping `on_event` to convert raw dicts to `LLEvent`:

```python
def wire_extensions(bus: EventBus, config_paths: list[str] | None = None) -> list[LLExtension]:
    extensions = ExtensionLoader.load_all(config_paths)
    for ext in extensions:
        bus.register(lambda event, e=ext: e.on_event(LLEvent.from_dict(event)))
    return extensions
```

2. Call `wire_extensions(event_bus, config.get("extensions"))` in each CLI entry point that creates an `EventBus`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Type boundary confirmed**: `EventBus.emit()` dispatches `dict[str, Any]` (`events.py:93`), while `LLExtension.on_event()` expects `LLEvent` (`extension.py:36`). The wrapper lambda using `LLEvent.from_dict()` (`events.py:50`) is the correct approach.
- **Config access gap**: `BRConfig` does not parse the `extensions` key — `_parse_config()` (`config/core.py:95-115`) has no extensions handling. Access requires `config._raw_config.get("extensions", [])` or adding a public `extensions` property to `BRConfig`.
- **`LLEvent.from_raw_event()`** (`events.py:61`) is an alternative to `from_dict()` — it copies the dict first to avoid mutation. Prefer this for the wrapper since EventBus observers share the same dict reference.

## Use Case

A developer installs a third-party extension package that implements `LLExtension` and registers it as a `little_loops.extensions` entry point. When they run `ll-loop`, the extension's `on_event` is automatically called for each FSM state transition, action completion, and issue lifecycle event — enabling dashboards, notifications, or custom logging without modifying little-loops source.

## Acceptance Criteria

- [x] `ExtensionLoader.load_all()` is called in CLI entry points that create an `EventBus`
- [x] Extension `on_event` callbacks receive `LLEvent` instances (not raw dicts)
- [x] Extensions loaded from both config paths and entry points are wired
- [x] Failed extension loads log warnings but don't crash the CLI
- [x] `NoopLoggerExtension` produces output when configured in `ll-config.json`
- [x] Existing behavior unchanged when no extensions are configured

## API/Interface

```python
# New helper in extension.py or events.py
def wire_extensions(
    bus: EventBus,
    config_paths: list[str] | None = None,
) -> list[LLExtension]:
    """Load extensions and register them on an EventBus."""
    ...
```

```json
// ll-config.json addition
{
  "extensions": [
    "my_package.ext:MyExtension"
  ]
}
```

## Implementation Steps

1. Add `wire_extensions()` helper in `extension.py` that loads extensions and registers wrapped callbacks on an EventBus — use `LLEvent.from_raw_event()` (`events.py:61`) in the wrapper to avoid mutating the shared event dict
2. Add an `extensions` property to `BRConfig` (`config/core.py`) that returns `self._raw_config.get("extensions", [])` — or access `_raw_config` directly in callers
3. Wire into `cli/loop/run.py:150` — after `executor = PersistentExecutor(...)`, call `wire_extensions(executor.event_bus, config._raw_config.get("extensions", []))` (executor owns its bus at `fsm/persistence.py:344`)
4. Wire into `cli/loop/lifecycle.py:251` — same pattern after `executor = PersistentExecutor(...)` for the resume path
5. Wire into `cli/parallel.py:225` — after `event_bus = EventBus()`, before passing to `ParallelOrchestrator`
6. Wire into `cli/sprint/run.py:389` — after `event_bus = EventBus()`, before passing to `ParallelOrchestrator`
7. Add integration test in `tests/test_extension.py`: configure `NoopLoggerExtension` via config paths, create an `EventBus`, call `wire_extensions()`, emit a raw dict event, verify the extension received an `LLEvent`
8. Verify `config-schema.json` already has the `extensions` key (confirmed at line 896)

## Integration Map

### Files to Modify
- `scripts/little_loops/extension.py` — add `wire_extensions()` helper function (place after `ExtensionLoader` class at line 129)
- `scripts/little_loops/config/core.py` — add `extensions` property to `BRConfig` returning `self._raw_config.get("extensions", [])`
- `scripts/little_loops/cli/loop/run.py:150` — wire extensions after `PersistentExecutor` creation
- `scripts/little_loops/cli/loop/lifecycle.py:251` — wire extensions after `PersistentExecutor` creation (resume path)
- `scripts/little_loops/cli/parallel.py:225` — wire extensions after `EventBus()` creation
- `scripts/little_loops/cli/sprint/run.py:389` — wire extensions after `EventBus()` creation

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py:344` — `PersistentExecutor.__init__()` creates its own `EventBus()` as `self.event_bus`
- `scripts/little_loops/cli/loop/_helpers.py:487` — existing `bus.register(display_progress)` pattern to follow for wiring style
- `scripts/little_loops/events.py:93` — `EventBus.emit()` dispatches `dict[str, Any]` (the type mismatch boundary)

### Similar Patterns
- `scripts/little_loops/cli/loop/_helpers.py:484-489` — `executor.event_bus.register(display_progress)` is the existing registration pattern for the loop entry point
- `scripts/tests/test_events.py:101` — `bus.register(lambda e: received.append(e))` test pattern for observer registration
- `scripts/tests/test_orchestrator.py:1409` — EventBus registration in orchestrator tests

### Tests
- `scripts/tests/test_extension.py` — existing tests for `ExtensionLoader`, `NoopLoggerExtension`, `LLExtension` protocol; add `wire_extensions()` integration test here
- `scripts/tests/test_events.py` — existing tests for `EventBus` registration, emit, observer error handling

### Configuration
- `config-schema.json:896` — `extensions` key already defined as `{ "type": "array", "items": { "type": "string" }, "default": [] }`
- `.ll/ll-config.json` — does **not** currently contain an `extensions` key (no change needed; empty default is correct)

## Impact

- **Priority**: P3 - Completes the extension architecture; without this, FEAT-911's consumer path is non-functional
- **Effort**: Small - ~30 lines of wiring code plus tests; all building blocks exist
- **Risk**: Low - Additive change; no extensions configured = no behavior change
- **Breaking Change**: No
- **Depends On**: None (FEAT-911 already implemented the building blocks)
- **Blocks**: ENH-926 (event filtering for extensions benefits from this), FEAT-916 (extension SDK)

## FEAT-911 Audit Context

_Added by FEAT-911 implementation audit (2026-04-02):_

This is the **only remaining gap** from FEAT-911's 9 implementation steps. All other steps are verified complete:
- Steps 1-2: `events.py` (LLEvent + EventBus) and `extension.py` (Protocol + Loader) — done in FEAT-911
- Step 3: PersistentExecutor migrated to EventBus — done in FEAT-911
- Steps 4-5: Event emission wired into issue lifecycle (ENH-919), StateManager (ENH-920), parallel orchestrator (ENH-921) — all completed
- Steps 7-8: Public exports and tests — done in FEAT-911
- ENH-922: Extension API reference docs — completed

Once FEAT-927 is implemented, the extension architecture is fully operational end-to-end.

Minor gaps also found (not blockers for FEAT-927):
- `EventCallback` is exported from `fsm/__init__.py` but not from top-level `little_loops/__init__.py` — extension authors may expect it there
- `docs/guides/EXTENSION_GUIDE.md` was planned in FEAT-911's Integration Map but never created — a separate ENH could address this once extensions are actually functional

## Scope Boundaries

- **In scope**: Wiring loaded extensions to EventBus in CLI entry points, LLEvent conversion
- **Out of scope**: Extension lifecycle management (init/shutdown hooks), event filtering (ENH-926), bidirectional hooks (FEAT-915)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Extension Architecture & Event Flow section |
| architecture | docs/reference/API.md | EventBus and extension API reference |

## Labels

`feat`, `extension-api`, `captured`

---

## Resolution

**Resolved** — 2026-04-02

### Changes Made
- Added `wire_extensions(bus, config_paths)` helper to `extension.py` that loads extensions via `ExtensionLoader.load_all()` and registers wrapped `on_event` callbacks on the bus using `LLEvent.from_raw_event()` to avoid dict mutation
- Added `extensions` property to `BRConfig` returning `_raw_config.get("extensions", [])`
- Wired extensions in all 4 CLI entry points: `cli/loop/run.py`, `cli/loop/lifecycle.py`, `cli/parallel.py`, `cli/sprint/run.py`
- Added `wire_extensions` to package `__init__.py` exports
- Added 5 tests covering: registration, no-extensions, failed loads, dict preservation, multiple extensions

### Verification
- All 34 extension+event tests pass
- Lint clean (ruff)
- Type check clean (mypy)

## Status

**Completed** | Created: 2026-04-02 | Completed: 2026-04-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-04-03T00:49:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17240d9f-c05c-4a95-8d41-67e38cfe53f4.jsonl`
- `/ll:refine-issue` - 2026-04-03T00:41:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/998ad8f8-102d-4374-80a7-c9a75706c7a7.jsonl`
- `/ll:capture-issue` - 2026-04-03T00:35:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5913db88-19b3-455b-8448-97664c8c42f8.jsonl`
- `/ll:confidence-check` - 2026-04-02T19:45:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59a96965-9adf-4cd8-9c40-8c3a7bb7b986.jsonl`
