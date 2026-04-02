---
discovered_date: 2026-04-01
discovered_by: capture-issue
---

# FEAT-911: Extension Architecture — little-loops as a Protocol, not a Product

## Summary

Design and implement an explicit extension point into the plugin: a published schema/event bus that external packages can hook into. The OSS plugin emits structured data (loop state, issue history, FSM transitions); external tools consume it. Each experiment lives in its own repo but is a "first-class ll extension."

## Current Behavior

little-loops has no formal extension API. All integrations must live inside the plugin repo, making the OSS/commercial boundary a directory boundary rather than an API surface.

## Expected Behavior

External packages can hook into little-loops via a stable, published schema/event bus. The plugin emits structured events (loop state changes, issue history updates, FSM transitions); consumers subscribe without forking or patching the core. New experiments ship as independent repos that are recognized as first-class ll extensions.

## Motivation

Forces clean architectural thinking — the OSS/commercial boundary becomes the API surface, not a directory. This is the correct long-term shape for a plugin that wants to stay lean at its core while supporting a growing ecosystem of specialized tooling.

## Proposed Solution

Define and publish an event/schema contract:
- Identify emission points: FSM transitions, loop lifecycle hooks, issue state changes
- Design a structured payload format (JSON Schema or dataclass protocol)
- Decide transport: file-based (append-only log), in-process callbacks, or IPC
- Define extension discovery mechanism (e.g., entry points, config key, directory convention)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical insight: the FSM event system already exists.** `FSMExecutor` (`scripts/little_loops/fsm/executor.py:103`) already defines `EventCallback = Callable[[dict[str, Any]], None]` and emits 11 named events via `_emit()` at line 1000. All events are persisted to `.loops/.running/<name>.events.jsonl` via `PersistentExecutor.append_event()` at `fsm/persistence.py:216`. The extension API for the FSM layer is already there structurally — it just isn't exposed publicly.

**What does NOT exist yet:**
- `ll-auto` and `ll-parallel` emit **zero events** — they update JSON state files but fire no callbacks
- Issue lifecycle (close/complete/defer in `issue_lifecycle.py`) has no event emission — all state changes are filesystem moves
- `PersistentExecutor._on_event` (line 342) is a single-slot observer (direct attribute assignment) — not a registration API
- No `[project.entry-points]` group in `scripts/pyproject.toml` — no mechanism for external packages to self-register as extensions

**Transport decision (informed by existing code):** File-based JSONL is already the established pattern (`persistence.py:216-242`). A unified `.ll/events.jsonl` append-only log is the lowest-friction approach — external tools can tail/watch it without in-process coupling. In-process callbacks (`EventCallback`) can coexist for latency-sensitive consumers.

**Recommended design:**
1. Create `scripts/little_loops/events.py` — `LLEvent` dataclass + `EventBus` (multi-observer, replaces the single `_on_event` slot)
2. Create `scripts/little_loops/extension.py` — `LLExtension` Protocol + `ExtensionLoader` using `importlib.metadata.entry_points(group="little_loops.extensions")`
3. Wire `EventBus` into `PersistentExecutor` (FSM), `StateManager` (ll-auto), `OrchestratorState` (ll-parallel), and `issue_lifecycle.py`
4. Publish schema as JSON Schema derived from `LLEvent` dataclass

## Integration Map

### Files to Modify

**New files to create:**
- `scripts/little_loops/events.py` — `LLEvent` dataclass + `EventBus` class (typed multi-observer registration, JSONL file sink to `.ll/events.jsonl`)
- `scripts/little_loops/extension.py` — `LLExtension` Protocol + `ExtensionLoader` (discovers extensions via `importlib.metadata.entry_points(group="little_loops.extensions")` or `ll-config.json`)

**Emission points to add (none currently exist outside FSM):**
- `scripts/little_loops/fsm/persistence.py:342,353` — Replace single `_on_event` slot with `EventBus` multi-observer; fire `EventBus` from `_handle_event()`
- `scripts/little_loops/issue_lifecycle.py:525` — `close_issue()` — add event emission on issue close
- `scripts/little_loops/issue_lifecycle.py:604` — `complete_issue_lifecycle()` — add event emission on completion
- `scripts/little_loops/issue_lifecycle.py:697` — `defer_issue()` — add event emission on defer
- `scripts/little_loops/issue_lifecycle.py:437` — `create_issue_from_failure()` — add event emission on new bug creation
- `scripts/little_loops/state.py:175,189` — `StateManager.mark_completed()` / `mark_failed()` — add ll-auto issue events
- `scripts/little_loops/parallel/orchestrator.py` — Add event emission when worker results are recorded (ll-parallel)
- `scripts/pyproject.toml:48-62` — Add `[project.entry-points."little_loops.extensions"]` group for extension discovery

**Config/schema files:**
- `config-schema.json` — Add `extensions: array of string` for module-path-based extension loading
- `.claude-plugin/plugin.json` — Possibly add `schema` key pointing to published event schema

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/_helpers.py:484-486` — Currently directly assigns `executor._on_event`; must update when `PersistentExecutor` moves to `EventBus`
- `scripts/little_loops/cli/loop/run.py:150` — Creates `PersistentExecutor`; will need to register extensions at startup
- `scripts/little_loops/cli/auto.py` — Creates `AutoManager`; will need to initialize `EventBus` and attach extension observers
- `scripts/little_loops/cli/parallel.py` — Creates `ParallelOrchestrator`; same as auto

### Similar Patterns

- `scripts/little_loops/fsm/executor.py:103-127` — `EventCallback` type alias + `ActionRunner` Protocol — direct model for `LLExtension` Protocol design
- `scripts/little_loops/fsm/executor.py:1000-1008` — `_emit()` method pattern — replicate verbatim for issue lifecycle and ll-auto/parallel emission points
- `scripts/little_loops/fsm/persistence.py:216-242` — `append_event()` / `read_events()` JSONL pattern — reuse/extend for unified event log
- `scripts/little_loops/subprocess_utils.py:21-28` — Typed `Callable` aliases (`OutputCallback`, `ProcessCallback`) — follow same naming convention for `EventCallback`
- `scripts/little_loops/parallel/types.py:51-135` — `WorkerResult.to_dict()` / `from_dict()` — use for `LLEvent` serialization
- `scripts/tests/test_fsm_executor.py:26-77` — `MockActionRunner` dataclass pattern — model for `MockExtension` in new tests

### Tests

- `scripts/tests/test_fsm_executor.py` — Add tests for extension observers wired through `FSMExecutor`
- `scripts/tests/test_fsm_persistence.py` — Add tests for `EventBus` in `PersistentExecutor` (replacing single-slot `_on_event`)
- `scripts/tests/test_issue_lifecycle.py` — Add tests for event emission on `close_issue`, `defer_issue`, etc.
- New: `scripts/tests/test_events.py` — Unit tests for `LLEvent` dataclass + `EventBus` multi-observer
- New: `scripts/tests/test_extension.py` — Unit tests for `LLExtension` Protocol + `ExtensionLoader`

### Documentation

- `docs/ARCHITECTURE.md` — Add extension API section
- `docs/reference/API.md` — Document `LLEvent`, `LLExtension`, `EventBus` public API
- New: `docs/guides/EXTENSION_GUIDE.md` — How to build an ll extension
- `docs/reference/CONFIGURATION.md` — Document `extensions` config key

### Configuration

- `config-schema.json` + `.ll/ll-config.json` — Add `extensions: list[str]` for module-path-based extension loading (e.g., `"my_package.MyExtension"`)
- Alternative: `[project.entry-points."little_loops.extensions"]` in `scripts/pyproject.toml` for pip-installable extensions

## Implementation Steps

1. Audit current emission points (FSM executor, ll-loop, ll-auto, ll-parallel, issue lifecycle)
2. Design event schema and transport layer (start minimal: file-based event log)
3. Define extension discovery convention
4. Implement emitter in core with a no-op default consumer
5. Build one reference extension to validate the API surface
6. Publish schema as part of plugin manifest

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps with file references:_

1. **Create `LLEvent` + `EventBus`** in `scripts/little_loops/events.py` — follow `WorkerResult` dataclass pattern (`parallel/types.py:51`) with `to_dict()`/`from_dict()`; model the bus's `emit()` on `_emit()` at `fsm/executor.py:1000`; use `append_event()` pattern from `fsm/persistence.py:216` for JSONL sink

2. **Create `LLExtension` Protocol** in `scripts/little_loops/extension.py` — follow `ActionRunner` Protocol at `fsm/executor.py:106-127` exactly; add `ExtensionLoader` using `importlib.metadata.entry_points(group="little_loops.extensions")`

3. **Migrate `PersistentExecutor._on_event`** (`fsm/persistence.py:342`) from single-slot to `EventBus` — update `_helpers.py:484-486` to call `executor.event_bus.register(display_progress)` instead of direct attribute assignment

4. **Add emission to issue lifecycle** (`issue_lifecycle.py:437,525,604,697`) — copy `_emit()` pattern; emit `{"event": "issue.closed", "ts": ..., "issue_id": ..., "resolution": ...}` etc.

5. **Add emission to `StateManager`** (`state.py:175,189`) for ll-auto; add emission to parallel orchestrator for ll-parallel results

6. **Wire extension loading** in CLI entry points — `cli/loop/run.py:150`, `cli/auto.py`, `cli/parallel.py` — load extensions from config before creating executor/manager, register each with the `EventBus`

7. **Add tests** following `MockActionRunner` pattern (`tests/test_fsm_executor.py:26-77`) — implement `MockExtension` with `recorded_events: list[dict]` and assert event sequences

8. **Run test suite**: `python -m pytest scripts/tests/test_events.py scripts/tests/test_extension.py scripts/tests/test_fsm_persistence.py scripts/tests/test_issue_lifecycle.py -v`

## Use Case

A commercial tool wants to consume loop state transitions to update a dashboard. It runs alongside ll without touching plugin source — it simply subscribes to the event stream ll emits.

## API/Interface

```python
# Conceptual extension hook
class LLExtension(Protocol):
    def on_event(self, event: LLEvent) -> None: ...

# Emitted event shape
@dataclass
class LLEvent:
    type: str           # "fsm.transition" | "issue.created" | "loop.complete"
    timestamp: str
    payload: dict       # type-specific data
```

## Acceptance Criteria

- [ ] Extension contract documented as a published schema
- [ ] At least one emission point wired to the event bus
- [ ] Reference extension (even a no-op logger) demonstrates the API works
- [ ] No breaking changes to existing ll behavior when no extensions are registered

## Impact

- **Priority**: P4 - Strategic architecture; no current blocker; significant upfront design cost
- **Effort**: Large - New cross-cutting abstraction affecting multiple subsystems
- **Risk**: High - Easy to over-engineer before knowing what extensions actually need; premature abstraction risk is real
- **Breaking Change**: No (additive)

## Related Key Documentation

- `docs/ARCHITECTURE.md` — System design overview
- `docs/generalized-fsm-loop.md` — FSM loop architecture (most relevant to extension event taxonomy)
- `docs/reference/API.md` — Python module reference
- `docs/reference/CONFIGURATION.md` — Config structure and schema
- `.issues/enhancements/P4-ENH-841-extract-fsm-executor-result-types-and-runners.md` — Related: extracting FSM result types (shares surface area with event/extension types)
- `.issues/enhancements/P4-ENH-470-refactor-parallel-god-classes.md` — Related: parallel god class refactor (cleans up the emission surface in orchestrator)
- `.issues/features/P4-FEAT-769-add-opencode-plugin-compatibility.md` — Related: alternative plugin compatibility (may share extension discovery design)

## Labels

`feat`, `architecture`, `extension-api`, `captured`

---

## Status

**Open** | Created: 2026-04-01 | Priority: P4

## Session Log
- `/ll:refine-issue` - 2026-04-01T23:56:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0ee23639-2228-4497-8647-94b597449939.jsonl`
- `/ll:capture-issue` - 2026-04-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1dc851d2-a56a-4f1d-8be1-ae404b7f7f2e.jsonl`
