---
discovered_date: 2026-05-01
discovered_by: split-from-FEAT-918
confidence_score: 75
outcome_confidence: 60
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 20
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

- `scripts/little_loops/transport.py` — add `OTelTransport` with `_loop_span`, `_state_span`, `_action_span`, `_loop_ctx`, `_state_ctx` attributes; register `"otel"` in `wire_transports()`
- `scripts/little_loops/config/features.py` — add `OTelEventsConfig` dataclass; extend `EventsConfig` with `otel: OTelEventsConfig`
- `config-schema.json` — extend `events` block with `otel` sub-object: `endpoint: string (default "http://localhost:4317")`, `service_name: string (default "little-loops")`. Close with `additionalProperties: false`
- `pyproject.toml` — add `otel = ["opentelemetry-sdk>=1.20.0", "opentelemetry-exporter-otlp-grpc>=1.20.0"]` to `[project.optional-dependencies]`

### Similar Patterns

- `scripts/little_loops/issue_history/formatting.py:94-100` — `try/except ImportError` optional-dep guard pattern
- FEAT-918 `JsonlTransport` — Protocol satisfaction template

### Tests

- `scripts/tests/test_transport.py` — add:
  - `pytest.importorskip("opentelemetry.sdk")` skip-decorator on the OTel test class
  - `OTelTransport` Protocol satisfaction
  - missing-dep `RuntimeError` test via `builtins.__import__` mock (pattern: `test_issue_history_formatting.py:137-154`)
  - End-to-end span test: install `InMemorySpanExporter` + `SimpleSpanProcessor`, feed a synthetic event sequence (`loop_start`, `state_enter`, `action_start`, `action_complete`, `loop_complete`), assert exported spans have correct parent/child structure and names
  - `loop_resume` test — opens a new trace, does not orphan
  - Sub-loop event with `depth > 0` — single warning, no span emitted
- `scripts/tests/test_config.py` — `OTelEventsConfig` defaults and full-tree parse

### Documentation

- `docs/reference/CONFIGURATION.md` — document `events.otel` block and `pip install little-loops[otel]` install
- `docs/reference/API.md` — `OTelTransport` constructor params and span semantics
- `docs/ARCHITECTURE.md` — OTel mapping (loop=trace, state=span, action=child span)
- `docs/reference/EVENT-SCHEMA.md` — OTel field schemas

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

1. Add `OTelEventsConfig` dataclass to `config/features.py` (`endpoint: str = "http://localhost:4317"`, `service_name: str = "little-loops"`); extend `EventsConfig` with `otel` field.
2. Extend `config-schema.json` `events` block with `otel` sub-object.
3. Add `OTelTransport` to `scripts/little_loops/transport.py` with optional-deps guard and stateful span machine. Use `tracer.start_span()` with manual context (not context manager) so spans live across multiple `send()` calls.
4. Register `"otel"` in `wire_transports()` constructor map.
5. Add `otel` extra to `pyproject.toml`.
6. Write tests in `test_transport.py` (Protocol, missing-dep, end-to-end with `InMemorySpanExporter`, sub-loop warning, resume-as-new-trace) and `test_config.py`.
7. Update docs.

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

**Open** | Created: 2026-05-01 (split from FEAT-918) | Priority: P5

## Session Log
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`

- Split from FEAT-918 - 2026-05-01
