# Plan: FEAT-1312 OTelTransport with Trace and Span Mapping

## Summary

Add `OTelTransport` that maps ll loop executions → OpenTelemetry traces/spans, exporting via OTLP.

## Decision: loop_start root span context

Root span is created with the default (empty) context — no explicit `otel_context.Context()` needed since there's no active span on the `OTelTransport` thread. Child spans use `trace.set_span_in_context(parent)` explicitly so we never rely on thread-local context propagation.

## Decision: _tracer_provider injection for tests

`OTelTransport.__init__` accepts optional `_tracer_provider` kwarg (underscore-prefixed, for testing only). When provided, the OTLP imports are still checked but the given provider is used instead of the OTLP-backed one. This allows `InMemorySpanExporter` tests without a running collector.

## Decision: Status codes

`loop_complete` with `outcome` in `{"error", "failed", "exhausted"}` → `StatusCode.ERROR`. All other outcomes → `StatusCode.OK`.

## Implementation Steps

1. `config/features.py` — Add `OTelEventsConfig` after `SocketEventsConfig`; add `otel` field to `EventsConfig`
2. `config/__init__.py` — Add `OTelEventsConfig` to import + `__all__`
3. `config/core.py` — Add `otel` sub-dict to `to_dict()` events block
4. `transport.py` — Add `OTelTransport`, `"otel": "otel"` in `_TRANSPORT_REGISTRY`, `elif name == "otel":` in `wire_transports()`; update module docstring
5. `scripts/little_loops/__init__.py` — Add `OTelTransport` to import + `__all__`
6. `config-schema.json` — Add `otel` sub-object under `events.properties`
7. `scripts/pyproject.toml` — Add `otel` optional-dependencies entry
8. `scripts/tests/test_transport.py` — OTel test class (protocol, missing-dep, end-to-end, resume, sub-loop)
9. `scripts/tests/test_config.py` — `TestOTelEventsConfig` + `EventsConfig.otel` round-trip
10. `scripts/tests/test_config_schema.py` — `otel` assertions in `test_events_in_schema()`
11. Docs: CONFIGURATION.md, API.md, ARCHITECTURE.md, EVENT-SCHEMA.md, CHANGELOG.md

## Span Machine State

```
_loop_span   : Span | None   — opened on loop_start, closed on loop_complete
_state_span  : Span | None   — opened on state_enter (closes prior), closed on loop_complete
_action_span : Span | None   — opened on action_start, closed on action_complete
```

## Event → OTel Mapping

| Event | Action |
|-------|--------|
| `loop_start` | open root span (`_loop_span`) |
| `loop_resume` | close all spans; open new root span |
| `state_enter` | close `_state_span`+`_action_span`; open child of `_loop_span` |
| `action_start` | open child of `_state_span` |
| `action_complete` | close `_action_span` |
| `loop_complete` | close `_state_span`+`_action_span`; set status on `_loop_span`; close `_loop_span` |
| `evaluate`, `route`, `retry_exhausted`, `handoff_detected`, `handoff_spawned`, `action_output` | `add_event()` on innermost open span |
| sub-loop (`depth > 0`) | single warning + no-op |
