---
id: FEAT-1322
priority: P5
size: Large
decision_needed: false
missing_artifacts: true
confidence_score: 100
outcome_confidence: 54
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
completed_at: 2026-05-02T15:59:58Z
---

# FEAT-1322: Transport Foundation — Core Module and EventBus Refactor

## Summary

Introduce the `Transport` Protocol abstraction, implement `JsonlTransport`, refactor `EventBus` to fan out to transports, fix the `loop_resume` bypass, and wire up the config stack (`EventsConfig`, `config-schema.json`). This is the foundation half of the FEAT-918 split; the CLI wiring pass ships in FEAT-1323.

## Parent Issue

Decomposed from FEAT-918: Transport Protocol Foundation and JsonlTransport

## Context

FEAT-918 scored 11/11 on the size heuristic (13 files, 5 subsystems, outcome_confidence 53/100). The confidence check recommended splitting into two commits: (1) core module + EventBus refactor, (2) CLI wiring pass. This issue is part 1.

## Motivation

The `_file_sinks` / `add_file_sink()` path on `EventBus` is dead code (zero production callers), creating confusion about the intended event routing contract. This refactor:
- Replaces dead code with a typed `Transport` Protocol — enabling additive transport implementations without `EventBus` modification
- Fixes the `loop_resume` bypass in `persistence.py` where resume events are written directly, bypassing `EventBus` and any registered transports
- Establishes the foundation required by FEAT-1323 (CLI wiring pass)

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
- `scripts/little_loops/config/core.py` — add `EventsConfig` to imports (lines 21–28); `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))` in `_parse_config()` (line 96); add `events` property (before `extensions` property at line 187; after `refine_status` property at lines 182–184)
- `config-schema.json` — add `"events": {"type": "object", "properties": {"transports": {"type": "array", "items": {"type": "string"}, "default": []}}, "additionalProperties": false}` inside top-level `properties`, after `extensions` closes at line 1035
- `scripts/little_loops/config/__init__.py` — add `EventsConfig` to `from little_loops.config.features import (...)` block and `__all__` list; currently exports all config dataclasses explicitly; `test_config.py` imports from `little_loops.config` (line 11), so this export is required [Wiring pass]

### Tests

- `scripts/tests/test_events.py` — rewrite `test_file_sink` (line 170) and `test_file_sink_reads_back` (line 184) to use `bus.add_transport(JsonlTransport(path))`. Other 23 tests unaffected.
- `scripts/tests/test_transport.py` (new) — Protocol satisfaction (pattern: `test_extension.py:19-32`), `JsonlTransport` lifecycle, error isolation when one transport raises (pattern: `test_events.py:140-154`)
- `scripts/tests/test_config.py` — `EventsConfig` defaults + nested-key parsing (pattern: `temp_project_dir` fixture, `BRConfig(temp_project_dir)`)
- `scripts/tests/test_fsm_persistence.py:749` — extend `test_resume_emits_resume_event` to assert `EventBus.emit` was called for `loop_resume`
- `scripts/tests/test_config_schema.py` — assert `"events"` in `data["properties"]` and `"transports"` in `data["properties"]["events"]["properties"]`; pattern: `test_learning_tests_in_schema`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py::TestBRConfig::test_to_dict` (line 701) — add `assert "events" in result`; existing test checks individual known keys but does not cover the new `events` top-level key [Agent 3 finding]
- `scripts/tests/test_config.py` — add `TestBRConfigEventsIntegration` class (4-test pattern from `TestBRConfigSyncIntegration`): `test_events_property_exists`, `test_events_property_with_defaults`, `test_events_property_loads_from_config`, `test_events_in_to_dict`; the issue text's reference to `temp_project_dir` fixture and `BRConfig(temp_project_dir)` implies BRConfig-level integration tests, not just `from_dict()` unit tests [Agent 3 finding]

### Codebase Research Notes (from FEAT-918)

- **`_on_event` shim** at `persistence.py:387–396` reads `self.event_bus._observers[0][0]`. Do not reorder/remove `_observers` entries during `_file_sinks` removal or this breaks silently.
- **`emit()` two-pass structure** — Pass 1 iterates `_observers` with glob filtering (lines 113–122). New transports match pass-2 behavior (unfiltered).
- **Pattern anchors** — `Transport` Protocol: model after `LLExtension` at `extension.py:35–56`. `EventsConfig.from_dict()`: model after `ScanConfig.from_dict` at `config/features.py:226–235`. `JsonlTransport.send()`: `path.parent.mkdir(parents=True, exist_ok=True)` in `__init__`, then `with open(path, "a", encoding="utf-8") as f: f.write(json.dumps(event) + "\n")` in `send()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Dead code confirmed**: `add_file_sink()` has zero production callers — only `test_events.py:174` and `test_events.py:188` call it. Safe to remove.
- **`_on_event` shim detail**: getter at `persistence.py:387` returns `self.event_bus._observers[0][0]` (first callback of first tuple); setter clears `_observers` and re-registers. The `_observers` list must remain in place through transport refactor — only `_file_sinks` and its fan-out (lines 124–129) are being replaced.
- **`close_transports()` exact insertion**: between `_on_event.setter` end (line 396) and `request_shutdown()` start (line 398) in `PersistentExecutor`.
- **`config-schema.json` insertion structure**: `extensions` closes at line 1035, outer `properties` object closes at line 1036, `additionalProperties: false` at line 1037. New `events` key inserts between lines 1035–1036 as a sibling of `extensions`.
- **`EventsConfig` test pattern**: For pure dataclass tests, model after `TestScanConfig` at `scripts/tests/test_config.py:486–509` — call `from_dict()` directly, no fixtures needed. Use `temp_project_dir` fixture only for `BRConfig`-level integration tests that read from disk.
- **JSONL write pattern**: Three consistent implementations confirm the pattern (`EventBus.emit:124–129`, `NoopLoggerExtension.on_event` at `extension.py:109–116`, `StatePersistence.append_event` at `persistence.py:257–264`). All use `open(path, "a", encoding="utf-8")` + `json.dumps(obj) + "\n"` with `path.parent.mkdir(parents=True, exist_ok=True)` at init time, not per-write.

### Documentation
- `docs/reference/API.md` — update `EventBus` API: document removal of `add_file_sink`, addition of `add_transport()` and `close_transports()`; add `Transport` Protocol and `JsonlTransport` entries

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` (line 473) — EventBus row in components table: "Multi-observer dispatcher with optional JSONL file sink" → update to reflect transport abstraction [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` (line 6) — cross-reference description says "bus registration, file sinks, filter patterns"; update "file sinks" to "transports" [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — no `events` section exists; add `events.transports` array documentation (sibling of the `extensions` section) since this is a user-facing config key [Agent 2 finding]

### Configuration
- `config-schema.json` — add `events.transports` array block (in scope; see Files to Modify)
- `.ll/ll-config.json` — no changes needed; new `events` key is optional with default `[]`

### Dependent Files (informational, no changes needed here)

- `scripts/little_loops/state.py` — imports `EventBus` for type annotation only; unaffected
- `scripts/little_loops/testing.py` — `LLTestBus`; does not call `add_file_sink`; unaffected
- `scripts/little_loops/issue_lifecycle.py` — emits events; unaffected
- `scripts/little_loops/issue_manager.py` — bare `EventBus()`; explicitly out of scope

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py` — calls `self._event_bus.emit()` at line 976; uses bare `EventBus()`, no `add_file_sink` calls; unaffected by transport refactor [Agent 1 finding]
- `scripts/little_loops/cli/loop/_helpers.py` — accesses `executor.event_bus.register(display_progress)` at line 539; coupled to `PersistentExecutor.event_bus` remaining a public attribute; no changes needed for FEAT-1322 [Agent 2 finding]
- `scripts/little_loops/__init__.py` — add `Transport`, `JsonlTransport`, and `wire_transports` to the `from little_loops.transport import (...)` block and `__all__` (under a `# transport` comment, sibling of `# events`). Decision: consistent with the extension system pattern — `LLExtension` (Protocol), `NoopLoggerExtension` (impl), and `wire_extensions()` are all exported; `Transport`, `JsonlTransport`, and `wire_transports` follow the same contract [Agent 2 finding, resolved 2026-05-02]

## Use Case

**Who**: A little-loops maintainer or contributor

**Context**: When refactoring `EventBus` to support pluggable event sinks and removing the dead `_file_sinks` path

**Goal**: Introduce a `Transport` Protocol that makes `EventBus` extensible without modification, fix the `loop_resume` bypass so all events flow uniformly through `EventBus`, and wire the config stack to support transport configuration

**Outcome**: `EventBus.emit()` fans out to registered `Transport` instances with per-transport exception isolation; `loop_resume` events are no longer bypassed; `BRConfig.events.transports` exposes the configured transport list; `JsonlTransport` is the first concrete implementation

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Export `Transport`, `JsonlTransport`, and `wire_transports` in `scripts/little_loops/__init__.py` — add `from little_loops.transport import (Transport, JsonlTransport, wire_transports)` and add all three to `__all__` under a `# transport` comment (sibling of `# events`)
9. Export `EventsConfig` in `scripts/little_loops/config/__init__.py` — add to `from little_loops.config.features import (...)` block and `__all__` list (after `SyncConfig`)
10. Update `scripts/tests/test_config.py::TestBRConfig::test_to_dict` (line 701) — add `assert "events" in result` for completeness check
11. Add `TestBRConfigEventsIntegration` class to `test_config.py` — 4-test pattern: `test_events_property_exists`, `test_events_property_with_defaults`, `test_events_property_loads_from_config`, `test_events_in_to_dict` (follow `TestBRConfigSyncIntegration` starting line 1117)
12. Update `docs/ARCHITECTURE.md` (line 473) — EventBus components table row: replace "optional JSONL file sink" with transport abstraction description
13. Update `docs/reference/EVENT-SCHEMA.md` (line 6) — replace "file sinks" with "transports" in cross-reference description
14. Update `docs/reference/CONFIGURATION.md` — add `events.transports` array section (sibling of `extensions`)

## Impact

- **Priority**: P5 — Infrastructure foundation with no immediate user-visible capability; FEAT-1323 depends on this but both are non-critical
- **Effort**: Medium — Touches 5 subsystems across 6 files with a new module, new test file, and config schema extension; patterns are well-established
- **Risk**: Low — `_file_sinks` is dead code; observer path untouched; transports additive
- **Breaking Change**: No
- **Depends On**: FEAT-911 (completed)
- **Blocks**: FEAT-1323 (CLI wiring pass)

## Labels

`transport`, `events`, `refactor`, `infrastructure`

## Status

**Completed** | Created: 2026-05-02 | Completed: 2026-05-02 | Priority: P5

## Resolution

Shipped the transport foundation as scoped:

- **New module** `scripts/little_loops/transport.py` — `Transport` Protocol (runtime-checkable), `JsonlTransport` (parent dir created at construction; `send()` appends a JSON line; `close()` is a no-op), and `wire_transports()` with a registry of built-in names (`{"jsonl": ...}`); unknown names log a warning and are skipped.
- **EventBus refactor** in `events.py` — removed `_file_sinks` and `add_file_sink()`; added `_transports`, `add_transport()`, and `close_transports()`; `emit()` fans out per-transport with exception isolation.
- **`loop_resume` bypass fix** at `scripts/little_loops/fsm/persistence.py:555` — resume events now flow through `EventBus.emit()` in addition to `append_event()`. Added `PersistentExecutor.close_transports()` after the `_on_event.setter`.
- **Config stack** — `EventsConfig(transports: list[str])` dataclass added in `config/features.py`; imported and parsed in `config/core.py` (`_parse_config`, `events` property, `to_dict`); exported from `config/__init__.py`.
- **Schema** — `config-schema.json` extended with an `events.transports` array as a sibling of `extensions`.
- **Public API** — `scripts/little_loops/__init__.py` re-exports `Transport`, `JsonlTransport`, and `wire_transports`.
- **Tests** — new `scripts/tests/test_transport.py` (14 tests covering Protocol satisfaction, `JsonlTransport` lifecycle, EventBus transport fan-out, exception isolation, `close_transports`, and `wire_transports` registry); two file-sink tests in `test_events.py` rewritten to use `add_transport(JsonlTransport(...))`; `test_fsm_persistence.py:749` extended to assert `EventBus.emit()` for resume events; `TestEventsConfig` and `TestBRConfigEventsIntegration` added to `test_config.py`; `test_events_in_schema` added to `test_config_schema.py`.
- **Docs** — `docs/reference/API.md` gained a `little_loops.transport` section; `docs/ARCHITECTURE.md`, `docs/reference/EVENT-SCHEMA.md`, and `docs/reference/CONFIGURATION.md` updated to reflect the transport abstraction (including a new `events.transports` config section).

Verification: full `pytest scripts/tests/` shows 5533 passed with 3 pre-existing unrelated failures (marketplace.json version mismatch + builtin_loops YAML structure, confirmed via `git stash` baseline). No new lint or mypy regressions. Unblocks FEAT-1323 (CLI wiring pass).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 54/100 → LOW

### Outcome Risk Factors
- **Complexity breadth**: 15 files span events, fsm/persistence, config, tests, and docs subsystems. Each individual change is small and patterned, but the accumulated surface area raises the probability of a missed step. Work through the 13 implementation steps sequentially, running tests after each subsystem group.
- **test_transport.py does not yet exist**: The new `transport.py` module has no prior test baseline; implementation errors will surface only after new tests are written as part of this issue. Write `test_transport.py` before finalizing `transport.py` (TDD approach is configured for this project).
- **`__init__.py` exports resolved**: `Transport`, `JsonlTransport`, and `wire_transports` will be added to `__all__` (step 8), consistent with the extension system pattern. No judgment call remains.

## Session Log
- `/ll:ready-issue` - 2026-05-02T15:46:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca51ce79-fc5d-451e-b964-005cf666a01c.jsonl`
- `/ll:ready-issue` - 2026-05-02T15:46:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca51ce79-fc5d-451e-b964-005cf666a01c.jsonl`
- `/ll:confidence-check` - 2026-05-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ea8713f7-6133-46d3-a7c4-835e7fe80de1.jsonl`
- `/ll:wire-issue` - 2026-05-02T15:35:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0920c085-edd5-4d96-901f-87d998a45ed1.jsonl`
- `/ll:refine-issue` - 2026-05-02T15:27:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34a9360e-afb7-429d-aa82-7d4cf5507f1f.jsonl`
- `/ll:format-issue` - 2026-05-02T15:22:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/784c461e-af3a-415e-9ed1-30cb388a8682.jsonl`
- `/ll:issue-size-review` - 2026-05-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19344c8e-9db2-4d37-b7f7-d6bf19e299d8.jsonl`
- `/ll:manage-issue` - 2026-05-02T15:59:58Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b593866a-d3e5-4a59-9fd9-49e3382dda71.jsonl`
