---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 70
score_complexity: 12
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 18
---

# FEAT-918: Transport Protocol Foundation and JsonlTransport

## Summary

Refactor `EventBus` to fan events out across a configurable list of `Transport` implementations. This is the load-bearing groundwork that unblocks webhook (FEAT-1314), OpenTelemetry (FEAT-1312), and Unix socket (FEAT-1313) transports — none of which ship in this issue.

## Context

Originally part of FEAT-918 ("cross-process event streaming with webhook and OTel"). After 30+ refinement passes the issue had ballooned to ~1200 lines and ~22 files of change surface. Split on 2026-05-01: foundation kept here; each transport extracted to its own issue.

## Current Behavior

- `EventBus.emit()` fans out to `_observers` (filtered by glob) and `_file_sinks` (unfiltered, raw `Path` objects). `_file_sinks` is dead code — `add_file_sink()` has zero production callers; only `test_events.py` exercises it (`test_events.py:170`, `test_events.py:184`).
- The actual JSONL log at `.ll/events.jsonl` is written by `PersistentExecutor.append_event()` (`fsm/persistence.py:373`) directly, not through `EventBus`.
- `loop_resume` events bypass the bus entirely: `persistence.py:506` writes via `append_event()` and never calls `event_bus.emit()`.
- No abstraction exists for adding a new event sink (HTTP, socket, OTel, etc.) — every new sink would have to be hand-wired into the bus.

## Expected Behavior

- A `Transport(Protocol, runtime_checkable)` abstraction in `scripts/little_loops/transport.py` with `send(event: dict[str, Any]) -> None` and `close() -> None`.
- `EventBus` holds `_transports: list[Transport]`; `emit()` fans out via per-transport exception isolation (matches existing observer isolation pattern).
- `JsonlTransport` is the only transport shipped in this issue — additive to the existing `PersistentExecutor.append_event()` write path (it does not replace it).
- `loop_resume` events flow through `EventBus.emit()` so any transport sees them.
- `wire_transports(bus, EventsConfig)` is called at all four `EventBus` construction sites (`run.py`, `lifecycle.py`, `parallel.py`, `sprint/run.py`).
- `EventBus.close_transports()` is called from CLI `finally` blocks and `ParallelOrchestrator._cleanup()`.

## Motivation

- Locks down the contract every transport must satisfy.
- Resolves the `loop_resume` bypass once, so future transports don't each have to fix it.
- Establishes the wiring + teardown paths so transport issues become drop-in additions, not rewiring exercises.
- Removes dead `_file_sinks` code so the next reader doesn't waste time tracing it.

## Proposed Solution

1. Define `Transport` Protocol in a new `scripts/little_loops/transport.py` module.
2. Refactor `EventBus`: remove `_file_sinks`/`add_file_sink()`, add `_transports`, `add_transport()`, `close_transports()`.
3. Implement `JsonlTransport(path: Path)` (mkdir + append-write on `send`, no-op `close`).
4. Add `EventsConfig(transports: list[str])` dataclass — only the `transports` array is in scope here. `webhook` and `otel` sub-blocks are added by their respective issues when those transports land.
5. Add `wire_transports(bus, EventsConfig)` with a single registry mapping `"jsonl"` → `JsonlTransport`. Other names log a warning and are skipped (they get registered when their issue ships).
6. Wire it at all four CLI entry points and in `ParallelOrchestrator._cleanup()`.
7. Fix the `loop_resume` bypass.

## API/Interface

```python
# scripts/little_loops/transport.py
from typing import Protocol, runtime_checkable

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
- `scripts/little_loops/fsm/persistence.py:506-507` — add `self.event_bus.emit(resume_event)` after `append_event(resume_event)` (`loop_resume` bypass fix)
- `scripts/little_loops/fsm/persistence.py:306` — `PersistentExecutor.close_transports()` delegates to `self.event_bus.close_transports()`
- `scripts/little_loops/cli/loop/run.py:160` — `wire_transports(executor.event_bus, config.events)` after `wire_extensions` (line 159); `executor.close_transports()` in `finally:` block (line 172) before `lock_manager.release()`
- `scripts/little_loops/cli/loop/lifecycle.py:261` — `wire_transports()` after `wire_extensions()` (line 260); add `try/finally` wrapper around `executor.resume()` so `close_transports()` runs on exit (no current `try/finally` at this site)
- `scripts/little_loops/cli/parallel.py:229` — `wire_transports(event_bus, config.events)` after `wire_extensions` (line 228). Teardown handled by orchestrator
- `scripts/little_loops/cli/sprint/run.py:392` — per-wave `wire_transports(event_bus, config.events)` after `wire_extensions` (line 391). Teardown handled by orchestrator
- `scripts/little_loops/parallel/orchestrator.py:1248` — `if self._event_bus: self._event_bus.close_transports()` after `merge_coordinator.shutdown()` in `_cleanup()`
- `scripts/little_loops/config/features.py:287` — add `EventsConfig` dataclass (only `transports: list[str]` field in this issue)
- `scripts/little_loops/config/core.py:21-27` — add `EventsConfig` to imports; line 116: `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))`; insert `events` property between lines 175–177
- `config-schema.json` — add `"events": {"type": "object", "properties": {"transports": {"type": "array", "items": {"type": "string"}, "default": []}}, "additionalProperties": false}` inside top-level `properties`, sibling of `extensions` (after the `extensions` block closes at line 902, before root `additionalProperties` at line 903)

### Tests

- `scripts/tests/test_events.py` — rewrite 2 of 25 tests (`test_file_sink` line 170, `test_file_sink_reads_back` line 184) to use `bus.add_transport(JsonlTransport(path))`. Other 23 unaffected
- `scripts/tests/test_transport.py` (new) — Protocol satisfaction (pattern: `test_extension.py:19-32`), `JsonlTransport` lifecycle, error isolation when one transport raises (pattern: `test_events.py:140-154`)
- `scripts/tests/test_config.py` — `EventsConfig` defaults + nested-key parsing (pattern: `temp_project_dir` fixture, `BRConfig(temp_project_dir)`)
- `scripts/tests/test_fsm_persistence.py:745` — extend `test_resume_emits_resume_event` to assert `EventBus.emit` was called for `loop_resume`
- `scripts/tests/test_orchestrator.py` — add `_cleanup()` test asserting `close_transports()` is called via injected mock `EventBus`; cover `_event_bus=None` guard
- `scripts/tests/test_cli_loop_lifecycle.py` — assert `wire_transports` called in `cmd_resume`; assert `close_transports()` runs in new `finally:`

### Documentation

- `docs/reference/API.md` — document `Transport` Protocol and `EventBus.add_transport()` / `close_transports()`
- `docs/ARCHITECTURE.md` — note the multi-transport fan-out model (foundation only; transports listed when they land)
- `docs/reference/CONFIGURATION.md` — add `events.transports` block after `extensions` (line 608)
- `docs/reference/EVENT-SCHEMA.md` — annotate the `loop_resume` bypass fix in the transport-behavior section

### Codebase Research Findings

- **`add_file_sink` has zero production callers** (`events.py:102`). Only `test_events.py:174` and `:188` exercise it; runtime `_file_sinks` is always empty. Safe to delete outright — `JsonlTransport` is additive, not a migration.
- **`emit()` two-pass structure** — Pass 1 (`events.py:114-122`) iterates `_observers` with `fnmatch` glob filtering. Pass 2 (`events.py:124-129`) iterates `_file_sinks` unfiltered. New transports should match pass-2 behavior (unfiltered) — per-transport filtering is out of scope here.
- **`_on_event` backward-compat shim** at `persistence.py:346-356` reads `self.event_bus._observers[0][0]` (first observer's callback). Do not reorder/remove `_observers` entries during the `_file_sinks` removal or this breaks silently.
- **`loop_resume` bypass** — `persistence.py:506` writes `loop_resume` directly via `self.persistence.append_event()`. Must add `self.event_bus.emit(resume_event)` immediately after, before `return self.run(clear_previous=False)` at line 509.
- **4 `EventBus` construction sites** — `persistence.py:344` (loop), `parallel.py:225` (parallel CLI), `sprint/run.py:390` (sprint per-wave), `issue_manager.py:735` (issue lifecycle, **out of scope** — bare bus, no extension wiring either).
- **`run.py` `try/finally` ordering** — `try:` at line 149; `finally:` at line 172 with `lock_manager.release(fsm.name)` at line 173. `executor.close_transports()` MUST come before `lock_manager.release()` so transports flush while the loop is still locked.
- **`lifecycle.py:cmd_resume` lacks `try/finally`** — Lines 211–280 are a flat sequence. Wrapping lines 251–279 is required so transports flush on exception/`KeyboardInterrupt`.
- **`ParallelOrchestrator._cleanup()` ignores `self._event_bus`** — Stored at `orchestrator.py:85`, read at lines 920–921, never closed. Add unconditional `self._event_bus.close_transports()` at line 1248 (not guarded by `_shutdown_requested` — flush even on interrupt).
- **`EventBus.close_transports()` must live on `EventBus`** so `ParallelOrchestrator._cleanup()` can call it without a `PersistentExecutor`. `PersistentExecutor.close_transports()` delegates.
- **`config-schema.json` schema position** — `events` block belongs inside top-level `properties` (sibling of `extensions`), after `extensions` closes at line 902, before root `additionalProperties: false` at line 903.
- **Optional-import test pattern** — `test_issue_history_formatting.py:137-154` uses `with patch("builtins.__import__", side_effect=mock_import)` to simulate missing dependencies. Not directly needed in this issue (no optional deps land here) but referenced for downstream transport issues.

## Use Case

A maintainer adds a new transport (webhook, OTel, etc.) by writing a class that satisfies `Transport`, registering it in `wire_transports`'s name → constructor map, and adding the config sub-block. No bus refactor, no per-CLI rewiring, no `loop_resume` workaround.

## Acceptance Criteria

- [ ] `Transport(Protocol, runtime_checkable)` defined in `scripts/little_loops/transport.py`
- [ ] `EventBus._file_sinks` and `add_file_sink()` removed; `_transports`, `add_transport()`, `close_transports()` added
- [ ] Per-transport exception isolation in `EventBus.emit()` — one transport raising does not stop others
- [ ] `JsonlTransport` implemented and satisfies `isinstance(t, Transport)`
- [ ] `loop_resume` events flow through `EventBus.emit()` (`persistence.py:507` fix)
- [ ] `EventsConfig` dataclass with `transports: list[str]` field; `BRConfig.events` property exposes it
- [ ] `config-schema.json` validates `events.transports` array
- [ ] `wire_transports()` called at `run.py:160`, `lifecycle.py:261`, `parallel.py:229`, `sprint/run.py:392`
- [ ] `close_transports()` called in `run.py:172 finally`, new `lifecycle.py finally`, and `orchestrator._cleanup():1248`
- [ ] Unknown transport names in config emit a warning and are skipped (so future transports can register without breaking older configs)
- [ ] All existing tests pass; new `test_transport.py`, config tests, and lifecycle tests added

## Implementation Steps

1. Create `scripts/little_loops/transport.py` with `Transport` Protocol, `JsonlTransport`, and `wire_transports()` (registry containing only `"jsonl"` for now; unknown names log a warning).
2. Refactor `EventBus` in `events.py`: remove `_file_sinks` (line 76), `add_file_sink()` (lines 102–105); add `_transports`, `add_transport()`, `close_transports()`; replace lines 124–129 with per-transport fan-out + exception isolation.
3. Add `self.event_bus.emit(resume_event)` at `persistence.py:507` (between `append_event` line 506 and `return self.run(...)` line 509).
4. Add `PersistentExecutor.close_transports()` that delegates to `self.event_bus.close_transports()`.
5. Add `EventsConfig` to `config/features.py:287` (single `transports: list[str]` field). Update `config/core.py` import tuple (lines 21–27), `_parse_config()` (line 116), and `events` property (between lines 175–177).
6. Extend `config-schema.json` with an `events` block (sibling of `extensions`, with only `transports` array for now).
7. Wire transports at all four CLI sites; add the `try/finally` in `lifecycle.py:cmd_resume`; add `close_transports()` to `ParallelOrchestrator._cleanup():1248`.
8. Rewrite `test_events.py` `test_file_sink` / `test_file_sink_reads_back` to use `JsonlTransport`. Add `test_transport.py`. Extend `test_fsm_persistence.py:745`, `test_orchestrator.py`, `test_cli_loop_lifecycle.py`, `test_config.py`.

## Impact

- **Priority**: P5 — depends on FEAT-911 (completed)
- **Effort**: Medium — bounded refactor; no new external deps
- **Risk**: Low — `_file_sinks` is dead, observer path untouched, transports additive
- **Breaking Change**: No
- **Depends On**: FEAT-911
- **Blocks**: FEAT-1314 (WebhookTransport), FEAT-1312 (OTelTransport), FEAT-1313 (UnixSocketTransport)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Event persistence patterns and FSM executor design |
| architecture | docs/reference/API.md | EventBus and transport configuration |

## Labels

`feat`, `extension-api`, `observability`, `captured`, `foundation`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-02; rescoped 2026-05-01 (split out webhook/OTel/socket transports to FEAT-1311/1312/1313)

- `EventBus`, `add_file_sink()`, `_file_sinks` confirmed at expected positions ✓
- `loop_resume` bypass at `persistence.py:506` confirmed ✓
- 4 `EventBus()` construction sites confirmed ✓
- `events` config key not in `config-schema.json` ✓

## Status

**Open** | Created: 2026-04-02 | Rescoped: 2026-05-01 | Priority: P5

## Session Log

- Split from original FEAT-918 - 2026-05-01 (webhook/OTel/socket transports moved to FEAT-1314/1312/1313)
- `/ll:confidence-check` - 2026-05-01 - Outcome confidence 46/100 on the original combined issue triggered the split
- See git history of `P5-FEAT-918-cross-process-event-streaming-with-webhooks-and-otel.md` for full pre-split refinement log (36 runs)
