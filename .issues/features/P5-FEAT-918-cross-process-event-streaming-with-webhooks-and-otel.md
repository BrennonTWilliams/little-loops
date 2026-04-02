---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# FEAT-918: Cross-Process Event Streaming with Webhook and OpenTelemetry Support

## Summary

Move beyond file-based JSONL event persistence to support real-time cross-process event streaming: Unix socket/named pipe for local consumers, configurable HTTP webhook POST for remote consumers, and OpenTelemetry integration so loop executions appear as traces and spans in existing observability stacks.

## Context

Identified from conversation reviewing FEAT-911's "unconstrained vision." FEAT-911 uses file-based JSONL as the event transport (lowest friction, already established). This issue captures the higher-fidelity transport options needed for production-grade monitoring and remote integrations.

## Current Behavior

FSM events are persisted to `.loops/.running/<name>.events.jsonl` via `PersistentExecutor.append_event()`. FEAT-911 proposes a unified `.ll/events.jsonl` append-only log. Both are file-based — consumers must poll or use filesystem watchers.

## Expected Behavior

Three additional transport options (configurable, all optional, coexist with JSONL):

1. **Unix socket / named pipe** — real-time streaming to local consumers with sub-second latency, no polling required
2. **Webhook sink** — configurable HTTP POST endpoints; events are batched and sent to remote URLs (dashboards, Slack bots, CI systems)
3. **OpenTelemetry integration** — loop executions emit OTel traces and spans, so they appear in Grafana, Jaeger, Datadog, etc. alongside application telemetry

## Motivation

File-based JSONL works for offline analysis and simple extensions, but production monitoring needs real-time streaming. Webhook sinks enable remote dashboards and ChatOps without local processes. OTel integration means ll fits into existing observability infrastructure rather than requiring its own.

## Proposed Solution

1. Abstract event transport behind a `Transport` Protocol in `events.py` — JSONL file sink becomes one implementation
2. Add `UnixSocketTransport` — creates a socket at `.ll/events.sock`, streams newline-delimited JSON
3. Add `WebhookTransport` — configurable URL(s), batching interval, retry policy, optional auth headers
4. Add `OTelTransport` — maps loop lifecycle to OTel spans (loop = trace, states = spans, actions = child spans), exports via OTLP
5. Transport selection via `ll-config.json`:
   ```json
   {
     "events": {
       "transports": ["jsonl", "socket", "webhook"],
       "webhook": { "url": "https://...", "batch_ms": 1000 },
       "otel": { "endpoint": "http://localhost:4317" }
     }
   }
   ```

## API/Interface

```python
class Transport(Protocol):
    def send(self, event: LLEvent) -> None: ...
    def close(self) -> None: ...

class WebhookTransport:
    def __init__(self, url: str, batch_ms: int = 1000, headers: dict | None = None): ...

class OTelTransport:
    def __init__(self, endpoint: str, service_name: str = "little-loops"): ...
```

## Use Case

A team runs ll-parallel processing 10 issues. Their Grafana dashboard (fed by OTel) shows a live trace for each loop — states as spans, actions as child spans, evaluations as span events. A Slack bot receives webhook POSTs and reports loop completions to a channel. A local monitoring TUI tails the Unix socket for real-time output.

## Acceptance Criteria

- [ ] `Transport` Protocol defined; `EventBus` accepts multiple transports
- [ ] `JsonlTransport` (existing behavior) refactored to implement `Transport`
- [ ] At least one additional transport implemented (Unix socket or webhook)
- [ ] Transport selection configurable via `ll-config.json`
- [ ] OTel integration maps loop lifecycle to traces/spans correctly
- [ ] All transports are optional — missing dependencies don't break core functionality

## Impact

- **Priority**: P5 - Infrastructure; premature until event system (FEAT-911) is proven
- **Effort**: Large - OTel integration alone is significant; webhook needs retry/auth logic
- **Risk**: Medium - New dependencies (opentelemetry-sdk, httpx) increase package footprint
- **Breaking Change**: No (additive transports behind existing EventBus)
- **Depends On**: FEAT-911

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Event persistence patterns and FSM executor design |
| architecture | docs/reference/API.md | EventBus and transport configuration |

## Labels

`feat`, `extension-api`, `observability`, `captured`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P5

## Session Log
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/233246d6-aba3-4c73-842f-437f09922574.jsonl`
