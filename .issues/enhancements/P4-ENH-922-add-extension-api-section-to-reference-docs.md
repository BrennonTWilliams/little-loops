---
discovered_date: 2026-04-02
discovered_by: capture-issue
testable: false
confidence_score: 100
outcome_confidence: 85
---

# ENH-922: Add Extension API Section to Reference Documentation

## Summary

Add a dedicated Extension API section to `docs/reference/API.md` documenting the public interfaces introduced by FEAT-911: `LLEvent`, `EventBus`, `LLExtension` Protocol, `ExtensionLoader`, and `NoopLoggerExtension`.

## Context

Identified from FEAT-911 session continuation prompt. FEAT-911 introduced the extension architecture but deferred documentation updates. The new public API surface (`events.py`, `extension.py`) needs reference documentation for extension authors.

## Current Behavior

`docs/reference/API.md` documents existing modules but has no section covering the extension system APIs introduced in FEAT-911.

## Expected Behavior

A new "Extension API" section in `docs/reference/API.md` covering:
- `LLEvent` dataclass — fields, `to_dict()`/`from_dict()` serialization
- `EventBus` — `register()`, `unregister()`, `emit()`, file sink configuration
- `LLExtension` Protocol — required methods, `@runtime_checkable` usage
- `ExtensionLoader` — `from_config()`, `from_entry_points()`, `load_all()`
- `NoopLoggerExtension` — reference implementation for extension authors
- Configuration format for `extensions` array in config-schema.json
- Entry point format for `little_loops.extensions` in pyproject.toml

## Motivation

Extension authors need clear API documentation to build on the extension architecture. Without docs, the only reference is reading source code, which raises the barrier to creating extensions.

## Scope Boundaries

- **In scope**: Adding API reference documentation for `LLEvent`, `EventBus`, `LLExtension`, `ExtensionLoader`, `NoopLoggerExtension`, config format, and entry point format to `docs/reference/API.md`
- **Out of scope**: Tutorial or guide content for extension development; inline code docstrings in source files; changes to `docs/ARCHITECTURE.md` beyond what FEAT-911 already added

## Implementation Steps

1. **Add module overview rows** — Insert two rows into the module overview table at `docs/reference/API.md:20-54`:
   - `little_loops.events` — Structured events and EventBus dispatcher
   - `little_loops.extension` — Extension protocol, loader, and reference implementation

2. **Add `## little_loops.events` section** — Follow the established pattern:
   - Document `EventCallback` type alias (`Callable[[dict[str, Any]], None]]`)
   - Document `LLEvent` dataclass using the dataclass block pattern (see lines 303-316): fields `type`, `timestamp`, `payload`; methods `to_dict()`, `from_dict()`, `from_raw_event()`
   - Document `EventBus` class using constructor + methods pattern: `__init__()`, `register()`, `unregister()`, `add_file_sink()`, `emit()`, `read_events()` (static)
   - Add quick-usage example showing `EventBus` creation, observer registration, and `emit()`

3. **Add `## little_loops.extension` section** — Follow established patterns:
   - Document `ENTRY_POINT_GROUP` constant (`"little_loops.extensions"`)
   - Document `LLExtension` Protocol using Protocol pattern (see lines 3938-3951): `on_event(event: LLEvent) -> None`
   - Document `NoopLoggerExtension` with constructor (`log_path: Path | None = None`) and `on_event()` method
   - Document `ExtensionLoader` static methods: `from_config()`, `from_entry_points()`, `load_all()`
   - Add quick-usage example showing how to create a custom extension class

4. **Document configuration** — Add a subsection covering:
   - `extensions` config key format: `["module.path:ClassName"]` (from `config-schema.json:896-901`)
   - Entry point format for `[project.entry-points."little_loops.extensions"]` (from `pyproject.toml:64-66`)

5. **Verify** — Ensure section ordering follows the existing alphabetical/logical ordering in API.md and that `---` horizontal rules separate sections

## Integration Map

### Files to Modify
- `docs/reference/API.md` — add Extension API section and add rows to module overview table (lines 20-54)

### Dependent Files (Callers/Importers)

_These are not files to modify, but callers/importers the documentation must accurately describe:_

- `scripts/little_loops/__init__.py:8-9,29-37` — re-exports `EventBus`, `LLEvent`, `ExtensionLoader`, `LLExtension`, `NoopLoggerExtension`
- `scripts/little_loops/fsm/persistence.py:344` — instantiates `EventBus()` in `PersistentExecutor.__init__`
- `scripts/little_loops/fsm/persistence.py:367-394` — `_handle_event` calls `self.event_bus.emit(event)`
- `scripts/little_loops/cli/loop/_helpers.py:485-489` — registers `display_progress` observer via `event_bus.register()`
- `config-schema.json:896-901` — defines `extensions` array config key
- `scripts/pyproject.toml:64-66` — declares `[project.entry-points."little_loops.extensions"]` group

### Similar Patterns
- `docs/reference/API.md` module overview table (lines 20-54) — add rows for `events` and `extension`
- Dataclass documentation pattern (lines 303-316, 512-533) — use for `LLEvent`
- Protocol documentation pattern (lines 3938-3951, `ActionRunner`) — use for `LLExtension`
- Class with constructor + methods (lines 61-297, `BRConfig`) — use for `EventBus`, `NoopLoggerExtension`
- Static methods pattern (lines 154-297) — use for `ExtensionLoader` methods
- Config key table pattern (lines 140-145) — use for `extensions` config key

### Tests
- N/A — documentation only (but `scripts/tests/test_events.py` and `scripts/tests/test_extension.py` confirm API behavior)

### Documentation
- `docs/ARCHITECTURE.md` — references extension architecture (read for context, no changes needed)

### Configuration
- N/A

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### API Surface: `little_loops.events` (`scripts/little_loops/events.py`)

**Type alias:** `EventCallback = Callable[[dict[str, Any]], None]` (line 24)

**`LLEvent`** (dataclass, lines 27-63):
- Fields: `type: str`, `timestamp: str`, `payload: dict[str, Any]` (default `{}`)
- `to_dict() -> dict[str, Any]` — produces `{"event": self.type, "ts": self.timestamp, **self.payload}` (flat, payload spread into root)
- `from_dict(cls, data) -> LLEvent` — pops `"event"/"type"` and `"ts"/"timestamp"`, remainder becomes payload; operates on a copy
- `from_raw_event(cls, raw) -> LLEvent` — convenience wrapper calling `from_dict(dict(raw))`

**`EventBus`** (lines 66-131):
- `__init__()` — initializes `_observers: list[EventCallback]` and `_file_sinks: list[Path]`
- `register(callback: EventCallback) -> None` — appends to observers
- `unregister(callback: EventCallback) -> None` — removes; silently ignores if not found
- `add_file_sink(path: Path) -> None` — creates parent dirs, appends to file sinks
- `emit(event: dict[str, Any]) -> None` — fans out to all observers (catches per-observer exceptions), writes JSON lines to all file sinks
- `read_events(path: Path) -> list[LLEvent]` (staticmethod) — reads JSONL file, skips invalid lines, returns `list[LLEvent]`

### API Surface: `little_loops.extension` (`scripts/little_loops/extension.py`)

**Constant:** `ENTRY_POINT_GROUP = "little_loops.extensions"` (line 25)

**`LLExtension`** (Protocol, `@runtime_checkable`, lines 28-42):
- Required method: `on_event(self, event: LLEvent) -> None`

**`NoopLoggerExtension`** (lines 45-60):
- `__init__(log_path: Path | None = None)` — defaults to `Path(".ll/extension-events.jsonl")`; creates parent dirs
- `on_event(event: LLEvent) -> None` — appends `json.dumps(event.to_dict())` to log file
- Satisfies `LLExtension` protocol (confirmed in `test_extension.py:76-79`)

**`ExtensionLoader`** (all static methods, lines 63-129):
- `from_config(extension_paths: list[str]) -> list[LLExtension]` — parses `"module:Class"` strings, imports and instantiates; skips failures with warning
- `from_entry_points() -> list[LLExtension]` — discovers via `importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)`; Python 3.11 compat fallback
- `load_all(config_paths: list[str] | None = None) -> list[LLExtension]` — combines config + entry point sources; config first

### Documentation Style Notes

- API.md uses H2 per module, H3 per class, H4 for Constructor/Properties/Methods
- Dataclasses use `@dataclass` code block + optional Attributes table
- Protocols use code block with `...` bodies + one-line usage note
- Simple methods use table format; complex methods use named subsections with Parameters/Returns/Example
- Module overview table at lines 20-54 needs new rows
- Sections separated by `---` horizontal rules

## Acceptance Criteria

- [ ] `docs/reference/API.md` has an "Extension API" section
- [ ] `LLEvent`, `EventBus`, `LLExtension`, `ExtensionLoader` are documented
- [ ] Configuration and entry point formats are described
- [ ] At least one code example for creating a custom extension

## Impact

- **Priority**: P4 — Documentation task; no functional impact, but needed for extension author onboarding
- **Effort**: Small — Single file addition following existing documentation patterns in API.md
- **Risk**: Low — Documentation only, no code changes, no breaking changes
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Target file for documentation |
| architecture | docs/ARCHITECTURE.md | Extension architecture context |

## Labels

`enhancement`, `captured`, `documentation`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P4

## Session Log
- `/ll:confidence-check` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e8f8c7c-82fc-4408-a963-218fe8d78eea.jsonl`
- `/ll:refine-issue` - 2026-04-02T18:54:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bfc51b4f-d97b-423d-a709-58690d5b4d91.jsonl`
- `/ll:format-issue` - 2026-04-02T18:47:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96cb2a22-5b05-4227-a2ab-5a4a047efa2e.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ec33f5e-0af1-4604-bdc4-0c4331282e3e.jsonl`
