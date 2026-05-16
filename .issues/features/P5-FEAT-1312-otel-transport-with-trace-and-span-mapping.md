---
discovered_date: 2026-05-01
discovered_by: split-from-FEAT-918
confidence_score: 100
outcome_confidence: 75
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 18
captured_at: 2026-05-01T00:00:00Z
completed_at: 2026-05-05T05:01:40Z
status: done
---

# FEAT-1312: OTelTransport with Trace and Span Mapping

## Summary

Add an `OTelTransport` that maps ll loop executions to OpenTelemetry traces and spans (loop = trace, state = span, action = child span), exporting via OTLP so loops appear in Grafana, Jaeger, Datadog, etc. alongside application telemetry.

## Context

Split from the original FEAT-918 on 2026-05-01. FEAT-918 now contains only the `Transport` Protocol foundation, `JsonlTransport`, and the `wire_transports()` registry. This issue plugs in the OTel implementation.

The OTel transport carries the highest implementation risk of the three transport children due to the stateful span machine — it tracks span handles across `loop_start` → `state_enter` → `action_*` → `loop_complete`. Plan for iteration.

## Current Behavior

ll has no OTel integration. Loop activity is invisible in any OTel-compatible observability stack.

## Expected Behavior

Per loop run:
- `loop_start` opens a root span (the trace), stored as `_loop_span`.
- `state_enter` opens a child span under the loop, stored as `_state_span` (closes the previous state span if any).
- `action_start` opens a grandchild span under the current state, stored as `_action_span`.
- `action_complete` closes `_action_span`; `evaluate` adds the result as a span event.
- `loop_complete` closes `_state_span` and `_loop_span`; sets status (OK/ERROR) based on outcome.
- `loop_resume` re-opens the loop span using a new trace (acceptable simplification — sub-loop continuity is out of scope here).
- `retry_exhausted`, `handoff_detected`, `handoff_spawned` are recorded as span events on the current span.
- Sub-loop events (carry `depth > 0` field): no-op with a single warning per session. Full nested-trace support is deferred to a follow-on enhancement.
- `close()` calls `force_flush()` then `shutdown()` on the tracer provider.

## Motivation

OTel is the lingua franca of observability. Once ll loops appear as traces, every existing dashboard, alert, and SLO definition becomes available without per-team integration work.

## Proposed Solution

1. Add `OTelTransport` to `scripts/little_loops/transport.py` with the stateful span machine.
2. Extend `EventsConfig` with `OTelEventsConfig(endpoint, service_name)`.
3. Register `"otel"` in `wire_transports()`'s name → constructor map.
4. Add `otel` optional extras to `pyproject.toml`.
5. Extend `config-schema.json` `events` block with an `otel` sub-object.

## API/Interface

```python
class OTelTransport:
    def __init__(
        self,
        endpoint: str = "http://localhost:4317",
        service_name: str = "little-loops",
    ): ...
    def send(self, event: dict[str, Any]) -> None: ...
    def close(self) -> None: ...   # force_flush + shutdown
```

Config:

```json
{
  "events": {
    "transports": ["jsonl", "otel"],
    "otel": {
      "endpoint": "http://localhost:4317",
      "service_name": "little-loops"
    }
  }
}
```

## Integration Map

### Files to Modify

- `scripts/little_loops/transport.py` — add `OTelTransport` with `_loop_span`, `_state_span`, `_action_span`, `_loop_ctx`, `_state_ctx` attributes; add `"otel": "otel"` to `_TRANSPORT_REGISTRY`; add `elif name == "otel":` branch in `wire_transports()` reading `config.otel.endpoint` and `config.otel.service_name`
- `scripts/little_loops/config/features.py` — add `OTelEventsConfig` dataclass (pattern: `SocketEventsConfig` at line ~374); extend `EventsConfig` with `otel: OTelEventsConfig` field and `from_dict()` entry
- `config-schema.json` — add `"otel"` sub-object to existing `"events"."properties"` block; note `"events"` already has `"additionalProperties": false` so `"otel"` must be added inside `"properties"`, not alongside it
- `pyproject.toml` — add `otel = ["opentelemetry-sdk>=1.20.0", "opentelemetry-exporter-otlp-grpc>=1.20.0"]` to `[project.optional-dependencies]`
- `scripts/little_loops/__init__.py` — add `OTelTransport` to `__all__` exports (alongside existing `JsonlTransport`, `UnixSocketTransport`, `Transport`, `wire_transports`)
- `scripts/little_loops/config/__init__.py` — add `OTelEventsConfig` to the `from little_loops.config.features import (...)` block and to `__all__` (follow the `SocketEventsConfig` pattern already there) [wiring pass]

### Similar Patterns

- `scripts/little_loops/issue_history/formatting.py:94-100` — `try/except ImportError` optional-dep guard pattern (defer import inside `__init__`, raise `RuntimeError` when absent)
- `scripts/little_loops/transport.py:64-81` — `JsonlTransport` class — minimal Protocol satisfaction template (`send` + `close`)
- `scripts/little_loops/config/features.py` — `SocketEventsConfig` + `EventsConfig.from_dict()` — exact pattern to mirror for `OTelEventsConfig` and `EventsConfig.otel` field
- `scripts/tests/test_issue_history_formatting.py:137-154` — `test_yaml_fallback_to_json()` — `builtins.__import__` side-effect mock for missing-dep `RuntimeError` tests

### Tests

- `scripts/tests/test_transport.py` — add:
  - `pytest.importorskip("opentelemetry.sdk")` skip-decorator on the OTel test class
  - `OTelTransport` Protocol satisfaction
  - missing-dep `RuntimeError` test via `builtins.__import__` mock (pattern: `test_issue_history_formatting.py:137-154`)
  - End-to-end span test: install `InMemorySpanExporter` + `SimpleSpanProcessor`, feed a synthetic event sequence (`loop_start`, `state_enter`, `action_start`, `action_complete`, `loop_complete`), assert exported spans have correct parent/child structure and names
  - `loop_resume` test — opens a new trace, does not orphan
  - Sub-loop event with `depth > 0` — single warning, no span emitted
- `scripts/tests/test_config.py` — `OTelEventsConfig` defaults and full-tree parse

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — add `otel` sub-object assertions inside existing `test_events_in_schema()` (assert `events_props["otel"]` is present, check `endpoint` and `service_name` defaults, check `additionalProperties: false` — mirror the `socket` block assertion pattern at lines ~155–163)

### Documentation

- `docs/reference/CONFIGURATION.md` — document `events.otel` block and `pip install little-loops[otel]` install
- `docs/reference/API.md` — `OTelTransport` constructor params and span semantics
- `docs/ARCHITECTURE.md` — OTel mapping (loop=trace, state=span, action=child span)
- `docs/reference/EVENT-SCHEMA.md` — OTel field schemas

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add `### Added` entry under the next concrete version section (per project convention, no `[Unreleased]` entries)
- `CONTRIBUTING.md` — optional: note the `scripts[otel]` install extra for contributors who want to run OTel tests locally (tests skip gracefully with `pytest.importorskip` when SDK absent)

### Dependent Files (Callers/Importers)

**`wire_transports()` call sites** — all four already wired per FEAT-1323; adding `"otel"` to config is sufficient to activate:
- `scripts/little_loops/cli/loop/run.py` — calls `wire_transports(executor.event_bus, config.events)`
- `scripts/little_loops/cli/loop/lifecycle.py` — calls `wire_transports(executor.event_bus, config.events)` on resume path
- `scripts/little_loops/cli/parallel.py` — calls `wire_transports(event_bus, config.events)` before constructing `ParallelOrchestrator`
- `scripts/little_loops/cli/sprint/run.py` — calls `wire_transports(event_bus, config.events)` per wave

**`close_transports()` — OTel `close()` will be triggered automatically:**
- `scripts/little_loops/parallel/orchestrator.py` — calls `event_bus.close_transports()` in `_cleanup()`
- `scripts/little_loops/events.py` — `EventBus.close_transports()` iterates all registered transports; each `transport.close()` wrapped in `try/except`

**Event sources** — all 12 mainline event types are emitted by:
- `scripts/little_loops/fsm/persistence.py` — emits `loop_start`, `loop_resume`, `loop_complete`
- `scripts/little_loops/fsm/executor.py` — emits `state_enter`, `action_start`, `action_complete`, `action_output`, `route`
- `scripts/little_loops/fsm/evaluators.py` — emits `evaluate`
- `scripts/little_loops/fsm/handoff_handler.py` — emits `handoff_detected`, `handoff_spawned`
- `scripts/little_loops/fsm/signal_detector.py` — emits `retry_exhausted`

**Public API** — `__init__.py` exports `Transport`, `JsonlTransport`, `UnixSocketTransport`, `wire_transports`; `OTelTransport` must be added alongside these.

### Configuration

- `config-schema.json` — `events.otel` sub-object (`endpoint`, `service_name`)
- `pyproject.toml` — `[project.optional-dependencies]` otel extra group

## Use Case

A team's Grafana dashboard already shows backend service traces. They run `ll-parallel`. Each loop execution shows up as a top-level trace in the same Grafana instance, with state spans as children, action spans as grandchildren. They can compare loop wall-clock to action wall-clock to spot slow steps without writing custom log queries.

## Acceptance Criteria

- [ ] `OTelTransport` implemented and satisfies `isinstance(t, Transport)`
- [ ] `opentelemetry-sdk` and `opentelemetry-exporter-otlp-grpc` are **optional** — package import succeeds without them; `OTelTransport.__init__` raises clear `RuntimeError` when constructed without them
- [ ] All 12 mainline event types map correctly to spans/span-events:
  - loop span: `loop_start` (open), `loop_complete` (close)
  - state span: `state_enter` (open new, close prior), implicit close on `loop_complete`
  - action span: `action_start` / `action_complete`
  - span events: `evaluate`, `route`, `retry_exhausted`, `handoff_detected`, `handoff_spawned`, `action_output`
- [ ] Exception-free under out-of-order or missing events (e.g., `loop_complete` without prior `loop_start` is a logged warning, not a crash)
- [ ] `loop_resume` opens a new loop span/trace
- [ ] Sub-loop events (`depth > 0`) emit a single warning per session and do not corrupt span state
- [ ] `close()` calls `force_flush()` then `shutdown()`
- [ ] Config schema validates `events.otel.endpoint` and `service_name`
- [ ] `wire_transports()` registers `"otel"` and constructs `OTelTransport(config.events.otel.endpoint, config.events.otel.service_name)`
- [ ] All transport tests pass; OTel tests skipped cleanly when SDK absent

## Implementation Steps

1. Add `OTelEventsConfig` dataclass to `config/features.py` (`endpoint: str = "http://localhost:4317"`, `service_name: str = "little-loops"`); extend `EventsConfig` with `otel: OTelEventsConfig = field(default_factory=OTelEventsConfig)` and hydrate in `from_dict()` with `otel=OTelEventsConfig.from_dict(data.get("otel", {}))` — mirrors existing `socket` field pattern at line ~374.
2. Extend `config-schema.json` `events."properties"` with `"otel"` sub-object; the block already has `"additionalProperties": false` so the new key must go inside `"properties"`, not alongside it.
3. Add `OTelTransport` to `scripts/little_loops/transport.py` with optional-deps guard (`try: import opentelemetry...` in `__init__`, raise `RuntimeError` if absent) and stateful span machine. Use `tracer.start_span()` with manual context (not context manager) so spans live across multiple `send()` calls.
4. Add `"otel": "otel"` to `_TRANSPORT_REGISTRY` dict; add `elif name == "otel":` branch in `wire_transports()` reading `config.otel.endpoint` and `config.otel.service_name`.
5. Add `otel = ["opentelemetry-sdk>=1.20.0", "opentelemetry-exporter-otlp-grpc>=1.20.0"]` to `[project.optional-dependencies]` in `scripts/pyproject.toml`.
6. Add `OTelTransport` to `scripts/little_loops/__init__.py` `__all__` list.
7. Write tests in `test_transport.py` (Protocol satisfaction, missing-dep `RuntimeError` via `builtins.__import__` mock — see `test_issue_history_formatting.py:137-154`, end-to-end with `InMemorySpanExporter` + `SimpleSpanProcessor`, sub-loop `depth > 0` warning, resume-as-new-trace) and `test_config.py` (`OTelEventsConfig` defaults, full-tree parse — mirror `TestSocketEventsConfig` pattern).
8. Update docs (`CONFIGURATION.md`, `API.md`, `ARCHITECTURE.md`, `EVENT-SCHEMA.md`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/little_loops/config/__init__.py` — add `OTelEventsConfig` to the import block and `__all__` list alongside `SocketEventsConfig` (same pattern)
10. Update `scripts/tests/test_config_schema.py` — add `otel` sub-object assertions inside existing `test_events_in_schema()`, asserting the `otel` key is present in `events_props` and that `endpoint` / `service_name` defaults and `additionalProperties: false` are correct
11. Update `CHANGELOG.md` — add `### Added` entry for `OTelTransport` under the next concrete version section

## Impact

- **Priority**: P5 — depends on FEAT-918 foundation
- **Effort**: Large — span state machine is the most complex transport
- **Risk**: Medium — out-of-order events, span lifecycle, optional-deps surface
- **Breaking Change**: No (additive, optional)
- **Depends On**: FEAT-918

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Multi-transport event fan-out |
| reference | docs/reference/CONFIGURATION.md | `events.otel` config block |
| reference | docs/reference/API.md | `OTelTransport` constructor and span semantics |
| reference | docs/reference/EVENT-SCHEMA.md | OTel field schemas |

## Labels

`feat`, `observability`, `extension-api`

## Status

**Completed** | Created: 2026-05-01 (split from FEAT-918) | Priority: P5

## Resolution

Implemented `OTelTransport` with stateful span machine (loop=trace, state=child span, action=grandchild span). All 12 mainline events mapped: `loop_start`/`loop_complete` bracket the root trace, `state_enter` opens child spans (closing prior), `action_start`/`action_complete` bracket grandchild spans, and `evaluate`, `route`, `retry_exhausted`, `handoff_detected`, `handoff_spawned`, `action_output` become OTel span events on the innermost open span. Sub-loop events (`depth > 0`) are no-ops with a single per-session warning. `loop_resume` opens a new root trace. `close()` calls `force_flush()` then `shutdown()`.

Files changed:
- `scripts/little_loops/transport.py` — `OTelTransport` class + registry + `wire_transports()` branch
- `scripts/little_loops/config/features.py` — `OTelEventsConfig` dataclass + `EventsConfig.otel` field
- `scripts/little_loops/config/__init__.py` — export `OTelEventsConfig`
- `scripts/little_loops/config/core.py` — `otel` sub-dict in `to_dict()`
- `scripts/little_loops/__init__.py` — export `OTelTransport`
- `config-schema.json` — `events.otel` sub-object
- `scripts/pyproject.toml` — `otel` optional-dependencies entry
- `scripts/tests/test_transport.py` — `TestOTelTransport` (protocol, missing-dep, end-to-end, status, resume, sub-loop, span events)
- `scripts/tests/test_config.py` — `TestOTelEventsConfig` + otel round-trip tests
- `scripts/tests/test_config_schema.py` — otel schema assertions
- `docs/reference/CONFIGURATION.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `docs/reference/EVENT-SCHEMA.md`, `CHANGELOG.md` — documentation

## Session Log
- `/ll:ready-issue` - 2026-05-05T04:46:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa034e27-eebe-4824-b0ae-28522438cc48.jsonl`
- `/ll:confidence-check` - 2026-05-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d356e53-934a-463f-a7f9-4f1e12929b26.jsonl`
- `/ll:wire-issue` - 2026-05-05T04:41:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e55127d-9324-4b9e-a00b-c05dfaa028d3.jsonl`
- `/ll:refine-issue` - 2026-05-05T04:36:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bd43be8a-d81e-4636-b354-4bdb18137e72.jsonl`
- `/ll:format-issue` - 2026-05-05T04:33:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9108e3ec-477f-44e6-a619-df7f8e94ace4.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`

- Split from FEAT-918 - 2026-05-01
- `/ll:manage-issue` - 2026-05-05T05:01:40Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
