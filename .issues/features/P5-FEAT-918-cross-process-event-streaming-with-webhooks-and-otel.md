---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 53
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

## Integration Map

### Files to Modify
- `scripts/little_loops/events.py` — add `Transport` Protocol; refactor existing `add_file_sink` / file-write path in `EventBus.emit()` into a `JsonlTransport`; update `EventBus` to hold `list[Transport]` and fan-out `send()` calls
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.__init__` (line 306–344) constructs `EventBus` at line 344; `_handle_event()` calls `self.persistence.append_event(event)` at line 373 (file write) then `self.event_bus.emit(event)` at line 394 (fan-out); transport construction and wiring should happen here or be injected from `cmd_run`
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` at lines 150–159 is the sole point where both config (`BRConfig`) and `PersistentExecutor` are available together; this is the correct injection site for transport configuration
- `config-schema.json` — add `events` top-level block (model after `sync.github` sub-object pattern at lines 776–818); include `events.transports` array enum, `events.webhook.url`, `events.webhook.batch_ms`, `events.otel.endpoint`
- `.ll/ll-config.json` — runtime transport selection and per-transport settings

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/__init__.py` — re-exports `EventBus` from top-level package
- `scripts/little_loops/parallel/orchestrator.py` — imports and uses `EventBus` for parallel run events
- `scripts/little_loops/state.py` — imports `EventBus`, wires `StateManager` emissions
- `scripts/little_loops/issue_lifecycle.py` — imports `EventBus`, wires issue lifecycle emissions
- `scripts/little_loops/issue_manager.py` — imports `EventBus`
- `scripts/little_loops/cli/sprint/run.py` — imports `EventBus`, wires sprint CLI entry point
- `scripts/little_loops/cli/parallel.py` — imports `EventBus`, wires parallel CLI entry point
- `scripts/little_loops/cli/loop/_helpers.py:484–489` — registers `display_progress` observer; has backward-compat path via `executor._on_event` property for executors without `event_bus`
- `scripts/little_loops/cli/loop/info.py` — imports `EventBus`

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/extension.py:19–49` — `LLExtension(Protocol, runtime_checkable)` — use this as the template for the new `Transport(Protocol)`; note attribute declaration style and `...` method body
- `scripts/little_loops/fsm/runners.py:17–48` — `ActionRunner(Protocol)` — simpler Protocol (no `@runtime_checkable`) for reference
- `scripts/little_loops/extension.py:139–168` — `wire_extensions()` fan-out setup loop with `_make_callback(e)` factory to avoid closure-over-loop-variable bug; reuse this pattern for wiring `list[Transport]`
- `scripts/little_loops/parallel/merge_coordinator.py:57–111` — background daemon thread with `Queue` + `threading.Event` shutdown; use for `WebhookTransport` batching loop
- `scripts/little_loops/link_checker.py:163–183` — `urllib.request` stdlib HTTP client (no extra dependency); viable fallback for `WebhookTransport` if `httpx` is absent
- `scripts/little_loops/issue_history/formatting.py:94–100` — inline `try/except ImportError` optional-dependency guard; use this pattern for `opentelemetry-sdk` and `httpx` guards
- `config-schema.json:776–818` — `sync.github` nested object as schema template for new `events` block; every nested object ends with `"additionalProperties": false`

### Tests
- `scripts/tests/test_events.py` — rewrite 2 of 25 tests calling `add_file_sink` → `add_transport(JsonlTransport(...))`
- `scripts/tests/test_transport.py` — new file: Protocol satisfaction, per-transport lifecycle, error isolation, threading, optional-dep mocks, OTel `InMemorySpanExporter`
- `scripts/tests/test_config.py` — add `EventsConfig` defaults and nested-key tests (pattern: `temp_project_dir` fixture + `BRConfig(temp_project_dir)`)
- `scripts/tests/test_fsm_persistence.py` — add `close_transports()` tests to `TestPersistentExecutor`; add EventBus assertion to `test_resume_emits_resume_event` (line 745)
- `scripts/tests/test_orchestrator.py` — add `_cleanup()` test: inject mock bus, assert `close_transports()` called; test `_event_bus=None` guard
- `scripts/tests/test_cli_loop_lifecycle.py` — update to cover `wire_transports` call added to `cmd_resume`
- Verify optional-dependency behavior (missing `opentelemetry-sdk` or `httpx` must not break core)

### Documentation
- `docs/reference/API.md` — document `EventBus` transport configuration
- `docs/ARCHITECTURE.md` — update event persistence section to reflect multi-transport model
- `docs/reference/CONFIGURATION.md` — add `events` block after `extensions` (line 608)
- `docs/reference/EVENT-SCHEMA.md` — add "Transport Behavior" section; annotate `loop_resume` bypass fix

### Configuration
- `config-schema.json` — new `events` config block
- `ll-config.json` — transport selection and per-transport settings

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`loop_resume` bypasses EventBus** — `persistence.py:506` writes `loop_resume` events directly via `self.persistence.append_event()` without calling `self.event_bus.emit()`. Any `Transport` wired through EventBus will **not** receive `loop_resume` events unless this is fixed separately.
- **Config injection point** — `cmd_run` (`scripts/little_loops/cli/loop/run.py:150–159`) is where `BRConfig` is loaded and `wire_extensions` is called. This is the correct site to read `config.events` and pass transports to `PersistentExecutor` at construction time. The `PersistentExecutor` constructor itself currently receives no config object.
- **All 12 event types emitted** through `FSMExecutor._emit()`: `loop_start`, `state_enter`, `route`, `retry_exhausted`, `action_start`, `action_output`, `action_complete`, `evaluate`, `loop_complete`, `handoff_detected`, `handoff_spawned` — plus `loop_resume` (bypassed, see above). Sub-loop events carry an injected `depth` field.
- **Test patterns to follow**: `scripts/tests/test_extension.py:19–49` (Protocol satisfaction checks), `scripts/tests/test_fsm_executor.py:26–77` (`MockActionRunner` dataclass stub), `scripts/tests/test_events.py` (EventBus unit tests including file sink)
- **`EventBus` internal attributes** — `_observers: list[tuple[EventCallback, list[str] | None]]` at `events.py:75`; `_file_sinks: list[Path]` at `events.py:76`. Refactor: remove `_file_sinks`, add `_transports: list[Transport]`; add `add_transport(t: Transport)` alongside existing `add_file_sink`.
- **`emit()` two-pass structure** — Pass 1 (`events.py:114-122`): iterates `_observers` with `fnmatch.fnmatch(event_type, pattern)` glob filtering. Pass 2 (`events.py:124-129`): iterates `_file_sinks` with **no filtering** — every event hits every sink. New transports should match file-sink behavior (unfiltered) unless per-transport filtering is added explicitly.
- **`dict` vs `LLEvent` in `send()`** — `emit(event: dict)` passes raw dicts throughout. The proposed `send(event: LLEvent)` requires a `LLEvent.from_raw_event(event)` conversion inside `emit()`. Alternative: define `Transport.send(event: dict)` to avoid per-event object allocation overhead. Decide before writing the Protocol.
- **`_on_event` backward-compat shim** — `persistence.py:346-356` exposes a getter that reads `self.event_bus._observers[0][0]` (the first observer's callback). Do not remove or reorder `_observers` entries without updating this shim, or old callers of `executor._on_event = fn` will break silently.
- **`PersistentExecutor` transport injection** — Current signature at `persistence.py:306`: `__init__(self, fsm, persistence=None, loops_dir=None, **executor_kwargs)`. Add `transports: list[Transport] | None = None`; call `self.event_bus.add_transport(t)` for each after `EventBus()` is created at `persistence.py:344`. Transport construction from config belongs in `cmd_run` at `run.py:155-159`, alongside `wire_extensions(executor.event_bus, ...)`.
- **Test patterns** — `test_events.py` uses **no mocks** (`unittest.mock` / `pytest-mock` are absent from the file). New transport tests should follow: concrete transport instances, accumulator lists (`received: list[dict] = []`), `tmp_path` fixture for file-based transports, `caplog.at_level(logging.WARNING)` for exception-isolation assertions.
- **Config schema JSON structure** — Model the new `events` block after `config-schema.json:776-818` (`sync.github`). Pattern: every property has `"description"` + `"default"`; nullable scalars use `"type": ["string", "null"]`; enum-constrained strings use `"enum": [...]` alongside `"type": "string"`; every nested object closes with `"additionalProperties": false`.

## Use Case

A team runs ll-parallel processing 10 issues. Their Grafana dashboard (fed by OTel) shows a live trace for each loop — states as spans, actions as child spans, evaluations as span events. A Slack bot receives webhook POSTs and reports loop completions to a channel. A local monitoring TUI tails the Unix socket for real-time output.

## Acceptance Criteria

- [ ] `Transport` Protocol defined; `EventBus` accepts multiple transports via `add_transport()`
- [ ] `JsonlTransport` (new additive transport — `_file_sinks` removed as dead code) implements `Transport`
- [ ] At least one additional transport implemented (Unix socket or webhook)
- [ ] Transport selection configurable via `ll-config.json` (`events.transports` array)
- [ ] OTel integration maps loop lifecycle to traces/spans correctly
- [ ] All transports are optional — missing dependencies don't break core functionality
- [ ] `loop_resume` events routed through `EventBus` (fixes bypass in `persistence.py:506`)
- [ ] Transport wiring (`wire_transports()`) added to `cli/loop/run.py` (line 160), `cli/loop/lifecycle.py` (line 261), `cli/parallel.py` (line 229), and `cli/sprint/run.py` (line 392)
- [ ] `EventBus.close_transports()` method added to `EventBus` directly (not just `PersistentExecutor`) — required for `ParallelOrchestrator._cleanup()` call path
- [ ] `PersistentExecutor.close_transports()` delegates to `self.event_bus.close_transports()`; called in `run.py:172` `finally:` block before `lock_manager.release()`
- [ ] Transport teardown handled via `EventBus.close_transports()` in `ParallelOrchestrator._cleanup()` at line 1248 (after `merge_coordinator.shutdown()`)

## Implementation Steps

> **Note**: The 10-step corrected implementation is in "Codebase Research Findings — All Positions Verified; Corrected Implementation Steps (run 13)" below. That version supersedes these original steps.

1. **Create `scripts/little_loops/transport.py`** — new module alongside `events.py`/`extension.py`. Define `Transport(Protocol, runtime_checkable)` with `send(event: dict[str, Any]) -> None` and `close() -> None`. All transport implementations and `wire_transports()` live here.
2. **Refactor `EventBus` in `events.py`** — remove dead `_file_sinks` (line 76) and `add_file_sink()` (lines 102–105); add `_transports: list[Transport] = []`, `add_transport()`, `close_transports()`; replace emit lines 124–129 with per-transport fan-out with exception isolation.
3. **Fix `loop_resume` bypass** — add `self.event_bus.emit(resume_event)` at `persistence.py:507` (after `append_event` at line 506, before `return self.run()` at line 509).
4. **Implement all transports in `transport.py`** — `JsonlTransport`, `UnixSocketTransport` (AF_UNIX, multi-client accept thread, per-client queue), `WebhookTransport` (batch daemon thread, exponential retry, drain-on-close), `OTelTransport` (stateful spans, `force_flush`+`shutdown` in `close()`).
5. **Add `EventsConfig` dataclasses to `config/features.py`** at line 287; update `core.py` import tuple and `_parse_config()` at line 116; add `events` property between lines 175–177.
6. **Extend `config-schema.json`** — add `"events"` inside top-level `"properties"` before `"additionalProperties": false` at line 903.
7. **Wire transports**: add `wire_transports(executor.event_bus, config.events)` in `run.py:160`, `parallel.py:229`, `sprint/run.py:392`; add `executor.close_transports()` in `run.py:172 finally:` before `lock_manager.release()`.
8. **Add `ParallelOrchestrator` teardown**: add `if self._event_bus: self._event_bus.close_transports()` at `orchestrator.py:1248` after `merge_coordinator.shutdown()`.
9. **Add optional extras to `pyproject.toml`** after line 78: `webhooks = ["httpx>=0.24.0"]` and `otel = ["opentelemetry-sdk>=1.20.0", "opentelemetry-exporter-otlp-grpc>=1.20.0"]`.
10. **Write tests** — rewrite `test_events.py` lines 170/184 to use `JsonlTransport`; add `test_transport.py` (Protocol satisfaction, lifecycle, error isolation, threading, optional-dep mocks via `builtins.__import__`, OTel via `InMemorySpanExporter`); add config tests in `test_config.py`.

### Codebase Research Findings — Refactoring Surface

_Added by `/ll:refine-issue` (run 2) — exact attributes and call sites:_

- **Step 1 detail**: Remove `_file_sinks: list[Path]` attribute (`events.py:76`); add `_transports: list[Transport]`. Replace emit pass 2 (`events.py:124-129`) — current `for path in self._file_sinks: open(path, "a")…` — with `for t in self._transports: t.send(event)`. Keep `add_file_sink()` as a convenience that wraps a `JsonlTransport`.
- **Step 2 detail**: `EventBus.__init__` takes no params (`events.py:74`); just add `self._transports: list[Transport] = []`. Existing `_observers` list and `register()`/`unregister()` are unchanged.
- **Step 3–5 detail**: Each transport class should follow `merge_coordinator.py:57-115` daemon-thread pattern for async variants (WebhookTransport batching). Guard optional imports inline: `try: import httpx / from opentelemetry…  except ImportError: raise RuntimeError("install httpx…")` inside `__init__`, matching `formatting.py:94-100`.
- **Step 6 detail**: In `cmd_run` (`run.py:155-159`), after `config = BRConfig(Path.cwd())`, read `config.events.transports`, construct transport objects, pass as `transports=[...]` to `PersistentExecutor(fsm, loops_dir=loops_dir, transports=[...])`.
- **Step 7 detail**: Protocol satisfaction test pattern — define inline class inside test, assign `_: Transport = instance` for static check (`test_extension.py:19-32`). File-sink test pattern — use `tmp_path / "out.jsonl"`, emit events, `assert (tmp_path / "out.jsonl").read_text()` (`test_events.py:153-163`).

### Codebase Research Findings — Implementation Hazards (run 3)

_Added by `/ll:refine-issue` — verified against current code:_

- **Construction order mismatch in `run.py`** — `PersistentExecutor` is constructed at `run.py:150`, but `BRConfig` is not loaded until `run.py:158`. Constructor-injection of `transports=[...]` requires reordering those lines, OR adding a post-construction `PersistentExecutor.add_transport(t: Transport)` method and calling it at line 159 alongside `wire_extensions`. The reorder approach is simpler; the method approach avoids changing the constructor signature.
- **`add_file_sink()` does `mkdir` at `events.py:102-105`** — `path.parent.mkdir(parents=True, exist_ok=True)` is called before appending the path to `_file_sinks`. Any `JsonlTransport.__init__(self, path: Path)` must replicate this mkdir call, or first-run directory creation will silently fail on paths whose parent doesn't yet exist.
- **`**executor_kwargs` forwarding at `persistence.py:340`** — `FSMExecutor` is constructed as `FSMExecutor(fsm, **executor_kwargs)`. A new `transports: list[Transport] | None = None` parameter added to `PersistentExecutor.__init__` must be consumed (popped from kwargs or declared before `**executor_kwargs`) before this forwarding line, otherwise passing `transports` would cause `TypeError: __init__() got an unexpected keyword argument 'transports'` in `FSMExecutor`.
- **`_on_event` setter is dead code for current callers** — `_helpers.py:486` checks `hasattr(executor, "event_bus")`, which is always true for `PersistentExecutor` (unconditionally set at `persistence.py:344`). The `else: executor._on_event = display_progress` branch at `_helpers.py:489` is unreachable for all current executor types. The setter at `persistence.py:351-356` can be safely deprecated once the transport system is stable.
- **`EventBus.read_events()` at `events.py:131` is unaffected** — it is a `@staticmethod` that reads from an arbitrary path; it has no dependency on `_file_sinks` or `_transports` and requires no changes during the refactor.

### Codebase Research Findings — Transport Lifecycle & Config Wiring (run 4)

_Added by `/ll:refine-issue` — verified against current code:_

- **`Transport.send()` type RESOLVED: use `dict[str, Any]`** — `EventCallback` is defined as `Callable[[dict[str, Any]], None]` at `events.py:25`; all FSM internals pass raw dicts to `emit()`. `LLEvent` is only constructed at the extension boundary (`extension.py:161` calls `LLEvent.from_raw_event(event)` inside `_make_callback`). The Transport Protocol should be `def send(self, event: dict[str, Any]) -> None: ...` with no `LLEvent` conversion — avoids per-event object allocation and stays consistent with how observers receive events.
- **`Transport.close()` lifecycle gap — no executor shutdown path exists** — `PersistentExecutor` has no `close()`, `__del__`, or `__exit__` (`persistence.py:306-394`). `request_shutdown()` at line 358 only signals the FSM loop to stop; it does not flush or close any transport. The correct injection site is the `try/finally` at `run.py:149-173`: add `executor.close()` (which fans out `t.close()` for each transport) to the `finally` block at line 172, alongside `lock_manager.release(fsm.name)`. This mirrors `orchestrator.py:169-175` where `_cleanup()` calls `merge_coordinator.shutdown(wait=True)` from a `finally` block. Without this, `WebhookTransport` background threads are daemon threads and will be killed on process exit without flushing the final batch.
- **`BRConfig` has no `events` attribute — full wiring required** — `core.py:_parse_config()` (lines 95-115) lists all current sections; `events` is absent. Implementation requires: (a) add `WebhookEventsConfig`, `OTelEventsConfig`, `EventsConfig` dataclasses to `scripts/little_loops/config/features.py`, modeled after `GitHubSyncConfig` (lines 241-267) and `SyncConfig` (lines 270-285); (b) add `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))` to `_parse_config()` at `core.py:115`; (c) expose via `@property def events(self) -> EventsConfig` at `core.py:117-175`.
- **Config nested-object template: `SyncConfig` + `GitHubSyncConfig` at `config/features.py:241-285`** — two-level nesting with `from_dict` calling sub-dataclass `from_dict` on nested key: `GitHubSyncConfig.from_dict(data.get("github", {}))`. Follow this exact pattern for `EventsConfig.from_dict(data)` calling `WebhookEventsConfig.from_dict(data.get("webhook", {}))` and `OTelEventsConfig.from_dict(data.get("otel", {}))`.
- **No threading tests in `test_events.py`** — all 21 tests are single-threaded; no `threading` import or `thread.join()` patterns exist. `WebhookTransport` and `UnixSocketTransport` tests must build threading test infrastructure from scratch. Use `threading.Event` (for shutdown signaling) + `thread.join(timeout=5.0)` for background thread cleanup. Follow `merge_coordinator.py:95-111` shutdown pattern: `_shutdown_event.set()` then `_thread.join(timeout=...)`.
- **Daemon thread behavior for transports** — `merge_coordinator.py:81-93` sets `daemon=True` on its thread. All transport background threads should also use `daemon=True` so they don't block process exit if `close()` is not called. Combined with explicit `close()` in `run.py:finally`, this gives both safe shutdown (normal case) and no-hang exit (crash/signal case).
- **`_helpers.py:484-491` shim is conditional, not dead** — `hasattr(executor, "event_bus")` at line 486 is always true for `PersistentExecutor` (confirmed: `self.event_bus` unconditionally set at `persistence.py:344`). The `else` branch at line 489 exists for non-`PersistentExecutor` executor types. Do not remove the `hasattr` guard — it protects callers that pass other executor types to `run_foreground`.

### Codebase Research Findings — Packaging, Retry, and Threading Tests (run 5)

_Added by `/ll:refine-issue` — verified against current code:_

- **`pyproject.toml` optional extras — add two new groups** (`scripts/pyproject.toml:68-78`): existing pattern has `dev = [...]` and `llm = []`. Add `webhooks = ["httpx>=0.24.0"]` and `otel = ["opentelemetry-sdk>=1.20.0", "opentelemetry-exporter-otlp-grpc>=1.20.0"]`. Core `[project.dependencies]` (lines 37-40) must not change — only `pyyaml` and `wcwidth` are required. Install with `pip install -e "./scripts[webhooks,otel]"` for full transport support.
- **`WebhookTransport` retry pattern — follow `GitLock` at `git_lock.py:110-181`**: Use `max_retries: int = 3`, `initial_backoff: float = 0.5`, `max_backoff: float = 8.0`. Cap formula: `backoff = min(backoff * 2, self.max_backoff)`. Test via patching `time.sleep` (from `test_git_lock.py:209-248`): capture sleep args, assert exact sequence `[0.5, 1.0, 2.0]` for 3 retries; cap test asserts `[2.0, 4.0, 4.0, 4.0, 4.0]` for 5 retries with `max_backoff=4.0`.
- **Threading test patterns confirmed** — `test_merge_coordinator.py:1380-1395` (inline `threading.Thread` target + `thread.join()` bracketing the assertion) and `test_overlap_detector.py:158-184` (fan-out with `errors: list[Exception]` collector — list append is GIL-safe, assert `len(errors) == 0`). Both directly applicable to `WebhookTransport` and `UnixSocketTransport` testing. Use `time.time()` elapsed assertions (`test_merge_coordinator.py:1422-1444`) to verify batching window behavior.
- **Construction order resolved via `wire_transports()` parallel function** — `wire_extensions(executor.event_bus, config.extensions)` at `run.py:159` already bridges `PersistentExecutor` (line 150) with `BRConfig` (line 158). Add a peer call `wire_transports(executor.event_bus, config.events)` at line 160. No constructor signature change needed; no reordering needed. This is simpler than both alternatives described in run 3. Define `wire_transports` in `extension.py` or a new `transport.py` module alongside the Transport Protocol.
- **`Transport` context manager** — `git_lock.py:67-79` shows `__enter__`/`__exit__` on a class. Not required on the Protocol; explicit `close()` in the Protocol is sufficient. Callers wanting `with` syntax can use `contextlib.closing(transport)` without requiring transports to implement `__enter__`.
- **`UnixSocketTransport` — no prior socket art in codebase**: No `socket` or `socketserver` imports exist anywhere in `scripts/`. Use stdlib `socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)`, `socket.bind(str(path))`, `socket.listen()` for the server. Serve each connected client via a daemon thread reading from a `Queue` (following `merge_coordinator.py:81-93` daemon thread pattern). Socket path: `.ll/events.sock` (already specified in issue).

### Codebase Research Findings — OTel Field Schemas, Error Isolation, and Webhook Body (run 6)

_Added by `/ll:refine-issue` — verified against current code:_

- **Per-transport error isolation required in fan-out loop** — `events.py:119-122` guards each observer call with `try: observer(event) / except Exception: logger.warning("EventBus observer raised an exception", exc_info=True)`. The new transport fan-out (replacing `events.py:124-129`) MUST use the same per-transport guard: `try: t.send(event) / except Exception: logger.warning("EventBus transport send failed: %s", t, exc_info=True)`. Without this, a crash in `WebhookTransport.send()` would prevent `UnixSocketTransport.send()` from receiving the event. Test pattern for transport isolation: follow `test_events.py:140-154` (`test_observer_exception_isolated`) — raise from one transport, assert second transport still received the event.

- **Complete OTel event field schemas** — All 12 event types with exact field names (needed to implement `OTelTransport`):
  - `loop_start` (line 144): `{"loop": str}` → root trace start; `loop` → `ll.loop.name` span attribute
  - `state_enter` (lines 223-229): `{"state": str, "iteration": int}` + optional `depth: int` for sub-loops → open child span; `state` → `ll.state.name`, `iteration` → `ll.state.iteration`
  - `action_start` (line 423): `{"action": str, "is_prompt": bool}` → open grandchild span; `action` → `ll.action.command`
  - `action_output` (line 426): `{"line": str}` — **highest-volume event**; map to `span.add_event("action_output", {"line": line})` on the action span, NOT a child span (to avoid OTel span explosion)
  - `action_complete` (lines 446-455): `{"exit_code": int, "duration_ms": int, "output_preview": str|None, "is_prompt": bool, "session_jsonl": str|None}` → close action span; `exit_code` → `ll.action.exit_code`, `duration_ms` → span duration attribute
  - `evaluate` (lines 584-591, 618-625): `{"type": str, "verdict": str, **details}` — details spread varies by evaluator (contains `confidence`, `error`, `exit_code`, etc.) → `span.add_event` on state span; `verdict` → `ll.evaluate.verdict`
  - `loop_complete` (lines 733-740): `{"final_state": str, "iterations": int, "terminated_by": str}` — NOTE: `error` string is NOT in the event payload, only in `ExecutionResult.error` → close root span; `terminated_by` → `ll.loop.terminated_by`
  - `route` (lines 256-262): `{"from": str, "to": str}` + optional `reason: "maintain"` → `span.add_event` on state span or link between state spans
  - `retry_exhausted` (lines 209-215): `{"state": str, "retries": int, "next": str}` → `span.add_event`
  - `handoff_detected` (lines 762-769): `{"state": str, "iteration": int, "continuation": str}` → `span.add_event`
  - `handoff_spawned` (lines 774-779): `{"pid": int, "state": str}` → `span.add_event`
  - `loop_resume` (persistence.py:496-505, BYPASSED): `{"loop": str, "from_state": str, "iteration": int}` + optional `from_handoff: True, "continuation_prompt": str` — never reaches EventBus (see run 1 note)

- **WebhookTransport HTTP POST body schema** — No existing HTTP transport or batch format in codebase. Use `json.dumps({"events": [event1, event2, ...]})` with `Content-Type: application/json`. No custom JSON encoder needed — all event field values are natively serializable (timestamps are ISO strings via `_emit()`, no `datetime` or `Path` objects reach `send()`). Single-event batches are fine (list of one dict); batch accumulation up to `batch_ms` collects multiple dicts before posting.

- **Background thread error logging levels** — Use TWO different log levels for transport background threads: (a) individual send failures → `logger.warning(..., exc_info=True)` matching `events.py:119-122` and `events.py:126-129`; (b) thread loop crashes → `logger.error(f"Transport loop error: {e}")` with `time.sleep(1.0)` backoff, matching `merge_coordinator.py:693-698`. This distinction prevents per-event send retries from being logged as errors while still surfacing thread crashes clearly.

- **`EventsConfig` belongs in `config/features.py`** — alongside `GitHubSyncConfig` (line 241) and `SyncConfig` (line 271). The `config/` package has: `core.py` (root `BRConfig` + `_parse_config()` at line 95), `features.py` (sync, loops, scan configs), `cli.py` (CLI display), `automation.py` (parallel, commands). Add `WebhookEventsConfig`, `OTelEventsConfig`, `EventsConfig` dataclasses to `features.py` after `SyncConfig`. Wire in `core.py:_parse_config()` at line 115: `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))`.

- **`transport.py` does not exist** — confirmed absent from codebase. Create as a new top-level module at `scripts/little_loops/transport.py` (alongside `events.py`, `extension.py`). The `Transport` Protocol and all transport implementations (`JsonlTransport`, `UnixSocketTransport`, `WebhookTransport`, `OTelTransport`) and `wire_transports()` function should all live here.

### Codebase Research Findings — OTelTransport State, UnixSocket Architecture, Steps Correction (run 8)

_Added by `/ll:refine-issue` — verified against current code:_

- **`PersistentExecutor` has no `close()` method** — confirmed absent from `persistence.py`. Add `def close_transports(self) -> None:` that fans out `t.close()` for each transport in `self.event_bus._transports`. Add `executor.close_transports()` to `run.py:172` (the `finally:` block at line 172, before `lock_manager.release(fsm.name)`).

- **Event ordering confirmed** — `_handle_event()` at `persistence.py:367-394` calls `self.persistence.append_event(event)` at line 373 **before** `self.event_bus.emit(event)` at line 394. Transports receive events AFTER the JSONL file write. A crash between those two lines would persist an event the transports never see — acceptable since JSONL is the durable record.

- **Step 1 correction (run 7 dead code finding)** — Current Implementation Step 1 says "refactor existing `_file_sinks` / file-append path into `JsonlTransport`." Run 7 confirmed `_file_sinks` is dead code (zero production callers). Correct Step 1: **(a)** remove `_file_sinks: list[Path]` attribute (line 76) and `add_file_sink()` method (lines 102–105) from `EventBus`; **(b)** add `_transports: list[Transport] = []` attribute and `add_transport(t: Transport) -> None` method; **(c)** replace `emit()` lines 124–129 (file-sink loop) with a per-transport fan-out matching the observer exception isolation pattern. `JsonlTransport` is optional-additive, not a migration of existing behavior.

- **OTelTransport internal span state** — `send(event: dict)` is called once per event; span lifecycle is stateful across calls. Required instance attributes: `_tracer: Tracer` (one `TracerProvider` + `OTLPSpanExporter` + `BatchSpanProcessor`, constructed in `__init__`); `_loop_span: Span | None`; `_loop_ctx: Context | None`; `_state_span: Span | None`; `_state_ctx: Context | None`; `_action_span: Span | None`. Routing: `if/elif` on `event["event"]`. Use `tracer.start_span(name, context=parent_ctx)` for manual span creation (not `start_as_current_span` — incompatible with event-driven model). Call `span.end()` explicitly. Span lifecycle: `loop_start` → open `_loop_span`, set `_loop_ctx = trace.set_span_in_context(_loop_span)`; `state_enter` → close prior `_state_span` if open, open new `_state_span` with `context=_loop_ctx`; `action_start` → open `_action_span` with `context=_state_ctx`; `action_complete` → close `_action_span`; `loop_complete` → close `_state_span`, close `_loop_span`.

- **OTelTransport `close()`** — must call `self._provider.force_flush()` then `self._provider.shutdown()` to ensure `BatchSpanProcessor` flushes pending spans before process exit. Without this, final-loop spans may be dropped silently.

- **UnixSocketTransport multi-client broadcast architecture** — no prior socket code in codebase. Design: `__init__` creates `socket.socket(AF_UNIX, SOCK_STREAM)`, calls `bind(str(path))`, `listen(5)`, sets `settimeout(1.0)` so `accept()` returns periodically; starts a daemon `_accept_thread`. `_accept_loop` calls `socket.accept()` in a while loop; for each connection spawns a per-client daemon thread with its own `queue.Queue`; adds `(conn, q, thread)` to `_clients: list` under `_clients_lock: threading.Lock`. `_client_loop(conn, q)` calls `q.get()`, sends `json.dumps(event).encode() + b"\n"` via `conn.sendall()`; on `BrokenPipeError`/`OSError` removes self from `_clients` and exits; `None` sentinel signals shutdown. `send(event)` serializes to string, acquires `_clients_lock`, calls `q.put_nowait(data)` for each client. `close()` sets `_shutdown_event`, closes server socket (unblocks `accept()`), puts `None` into each client queue, calls `self._path.unlink(missing_ok=True)`.

- **`EventsConfig` dataclass pattern** — follow `SyncConfig`/`GitHubSyncConfig` at `features.py:240-285` exactly. `EventsConfig` fields: `transports: list[str] = field(default_factory=list)`, `webhook: WebhookEventsConfig = field(default_factory=WebhookEventsConfig)`, `otel: OTelEventsConfig = field(default_factory=OTelEventsConfig)`. `WebhookEventsConfig` fields: `url: str | None = None`, `batch_ms: int = 1000`, `headers: dict[str, str] = field(default_factory=dict)`. `OTelEventsConfig` fields: `endpoint: str = "http://localhost:4317"`, `service_name: str = "little-loops"`. Wire in `core.py:_parse_config()` at line 115 as `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))`.

### Codebase Research Findings — wire_transports() Body, Socket Cleanup, close() Flush, Test Updates (run 9)

_Added by `/ll:refine-issue` — verified against current code:_

- **`wire_transports()` concrete body** — Model after `wire_extensions()` at `extension.py:139-168` (takes `bus: EventBus` + config, returns nothing, calls `bus.register()` per extension). Signature: `def wire_transports(bus: EventBus, config: EventsConfig) -> None:`. Iterate `config.transports`; for each name construct the transport and call `bus.add_transport(t)`. Guard each construction with `try/except RuntimeError` (raised by `WebhookTransport`/`OTelTransport` when optional dependency is missing), log warning, and continue. Sketch:
  ```python
  def wire_transports(bus: EventBus, config: EventsConfig) -> None:
      for name in config.transports:
          try:
              if name == "socket":
                  t = UnixSocketTransport(Path(".ll/events.sock"))
              elif name == "webhook":
                  if not config.webhook.url:
                      logger.warning("webhook transport: events.webhook.url not configured")
                      continue
                  t = WebhookTransport(config.webhook.url, config.webhook.batch_ms, config.webhook.headers)
              elif name == "otel":
                  t = OTelTransport(config.otel.endpoint, config.otel.service_name)
              elif name == "jsonl":
                  t = JsonlTransport(Path(".ll/events.transport.jsonl"))
              else:
                  logger.warning("Unknown transport: %s", name)
                  continue
              bus.add_transport(t)
          except RuntimeError as e:
              logger.warning("Failed to initialize transport %s: %s", name, e)
  ```
  Define in `transport.py` alongside the `Transport` Protocol and all transport implementations.

- **Stale socket `unlink` before `bind()`** — No codebase precedent for pre-bind file removal (all `unlink` calls in the codebase are cleanup-on-exit or rollback patterns). `UnixSocketTransport.__init__` MUST call `self._path.unlink(missing_ok=True)` immediately before `self._sock.bind(str(self._path))`. Without this, if a previous process crashed without calling `close()`, the `.ll/events.sock` file persists and `bind()` raises `OSError: [Errno 48] Address already in use`. Order: `path.unlink(missing_ok=True)` → `sock.bind(str(path))` → `sock.listen(5)` → start `_accept_thread`.

- **`WebhookTransport.close()` must drain remaining batch** — `MergeCoordinator.shutdown()` at `merge_coordinator.py:95-111` does NOT explicitly flush the queue; it relies on the thread to drain before the `_shutdown_event` is observed. For `WebhookTransport` this is insufficient: the batch thread may be sleeping (waiting for `batch_ms`) when `close()` is called, and pending events would be silently dropped. Correct pattern: in the batch thread loop, after observing `_shutdown_event`, immediately flush the remaining accumulated batch (POST the final batch) before returning. `close()` body: `(1) self._shutdown_event.set()`, `(2) self._queue.put(None)` (sentinel to wake the thread from `queue.get(timeout=batch_s)`), `(3) self._thread.join(timeout=10.0)`. Thread loop: after `while not self._shutdown_event.is_set()`, add a final `if pending: _flush(pending)` before the thread returns.

- **`loop_resume` fix is in scope** — The bypass is a one-line fix: add `self.event_bus.emit(resume_event)` at `persistence.py:507`, immediately after `self.persistence.append_event(resume_event)` at line 506 and before `return self.run(clear_previous=False)` at line 509. Include as part of Implementation Step 1. Without this, every transport misses `loop_resume` events on all resumed and handoff-resumed loops.

- **`test_events.py` lines 174 and 188 will break when `add_file_sink` is removed** — `test_file_sink` (line 170) and `test_file_sink_reads_back` (line 185) call `bus.add_file_sink(log_file)`. When `add_file_sink()` is removed from `EventBus` (per run 8 Step 1 correction), these two tests will raise `AttributeError`. Rewrite both to use `bus.add_transport(JsonlTransport(log_file))` as part of Step 7 (write tests). The remaining `TestEventBus` tests (7 of 9) and all 8 `TestEventBusFilter` tests do not call `add_file_sink` and are unaffected.

- **OTelTransport test pattern** — No `opentelemetry` or `InMemorySpanExporter` patterns exist anywhere in the codebase. Use `pytest.importorskip("opentelemetry.sdk", reason="opentelemetry-sdk required")` as a class-level skip guard. Use `opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter` with `opentelemetry.sdk.trace.export.SimpleSpanProcessor` to capture spans without a real OTLP endpoint. Inject via monkeypatching `OTelTransport.__init__` or by accepting an optional `provider` argument. Test lifecycle: `transport.send({"event": "loop_start", ...})`, `transport.send({"event": "state_enter", ...})`, `transport.close()` (to `force_flush()`), then `spans = exporter.get_finished_spans()`, assert `spans[0].name == "loop_start"` and `spans[0].attributes["ll.loop.name"] == "test-loop"`.

### Codebase Research Findings — Exact Wiring Call Sites and `__init__.py` Exports (run 10)

_Added by `/ll:refine-issue` — verified against current code:_

- **`cli/parallel.py:228-234` — exact wiring site**: `EventBus()` constructed at line 225; `wire_extensions(event_bus, config.extensions)` at line 228; `ParallelOrchestrator(...)` constructed at line 229 with `event_bus=event_bus` keyword. Add `wire_transports(event_bus, config.events)` at line 229, between `wire_extensions` and `ParallelOrchestrator(...)`. No surrounding `try/finally` in `main_parallel()` — cleanup is handled inside `orchestrator.run()` → `_cleanup()`. `config` is a `BRConfig` instance available at this callsite.

- **`cli/sprint/run.py:390-392` — exact wiring site**: Same pattern as `parallel.py`; `EventBus()` at line 390, `wire_extensions(event_bus, config.extensions)` at line 391, `ParallelOrchestrator(...)` at line 392. Add `wire_transports(event_bus, config.events)` between lines 391 and 392. A fresh `EventBus` and orchestrator are created per wave (inside a loop), so `wire_transports` must also run per wave. Sprint's outer `finally:` at line 508 only saves sprint state — transport teardown flows through `orchestrator._cleanup()` called inside each `orchestrator.run()`.

- **`parallel/orchestrator.py:_cleanup():1247` — exact teardown site**: `_cleanup()` shutdown sequence is `worker_pool.shutdown(wait=True)` at line 1246 → `merge_coordinator.shutdown(wait=True, timeout=30)` at line 1247 → conditional worktree cleanup at line 1251. Call `self.event_bus.close_transports()` at line 1248, immediately after `merge_coordinator.shutdown()`. The `event_bus` is passed to `ParallelOrchestrator.__init__` as `event_bus=event_bus` and stored as `self.event_bus`. The `_cleanup()` `finally` at `run():173` guarantees this fires on success, `KeyboardInterrupt`, and all exceptions.

- **`run.py` insertion confirmed**: `wire_transports(executor.event_bus, config.events)` at line 160 (after `wire_extensions(executor.event_bus, config.extensions)` at line 159); `executor.close_transports()` in the `finally:` block immediately before `lock_manager.release(fsm.name)` at line 172. `config` is resolved at line 158 and is available at both sites.

- **`__init__.py` export additions required** — `scripts/little_loops/__init__.py` currently exports `EventBus`, `LLEvent` from `little_loops.events` and `ExtensionLoader`, `LLExtension`, `NoopLoggerExtension`, `wire_extensions` from `little_loops.extension` (lines 9-14, added to `__all__` at lines 42-44). Add a parallel block: `from little_loops.transport import Transport, JsonlTransport, wire_transports` and add these three names to `__all__`. No other top-level modules reference `transport.py` yet — it is a new file.

- **`config-schema.json` `events` block structure** — model after `sync.github` at lines 776-818 (confirmed pattern: `type: object`, named properties each with `type`/`description`/`default`, `additionalProperties: false`). The new top-level `events` block should use `"type": ["string", "null"]` for `webhook.url`, `"type": "string"` + `"enum": ["jsonl","socket","webhook","otel"]` for each item in `transports` array. Array field: `"transports": {"type": "array", "items": {"type": "string", "enum": ["jsonl","socket","webhook","otel"]}, "default": [], "description": "..."}`. Nested objects `webhook` and `otel` each close with `"additionalProperties": false`.

- **`test_events.py:170-195` rewrite targets confirmed** — `test_file_sink` (line 170) calls `bus.add_file_sink(log_file)`; `test_file_sink_reads_back` (line 185) calls `bus.add_file_sink(log_file)`. Both will raise `AttributeError` when `add_file_sink` is removed. Rewrite: replace `bus.add_file_sink(log_file)` with `bus.add_transport(JsonlTransport(log_file))`. The `EventBus.read_events(log_file)` call at line 193 is a `@staticmethod` unaffected by the refactor. The remaining 7 `TestEventBus` tests and all 8 `TestEventBusFilter` tests have no `add_file_sink` calls — unaffected.

- **Threading test pattern confirmed** — `test_merge_coordinator.py:1405-1444` uses `threading.Thread(target=closure)` → `t.start()` → `time.sleep(0.05)` stagger → `start = time.time()` → blocking call → `elapsed = time.time() - start` → `t.join()` → `assert elapsed >= 0.05`. Directly applicable to `WebhookTransport` batching window tests (assert events accumulate for `batch_ms` before POST) and `UnixSocketTransport` connect/send tests.

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

## Verification Notes

**Verdict**: VALID — Verified 2026-04-02

- FEAT-911 is COMPLETED — `EventBus` exists; events written to `.ll/events.jsonl` via `fsm/persistence.py:394` ✓
- No `Transport` Protocol, `UnixSocketTransport`, `WebhookTransport`, or `OTelTransport` defined ✓
- `events` config key not in `config-schema.json` ✓
- Issue accurately describes the file-only transport gap

---

### Codebase Research Findings — Corrections and Precision Details (run 10)

_Added by `/ll:refine-issue` — verified against current code:_

- **`test_events.py` has 27 methods, not 21** — Run 9 stated "21 tests." The actual count is 27 methods across lines 18-307. Exactly 2 of the 27 call `add_file_sink`: `test_file_sink` at line 170 and `test_file_sink_reads_back` at line 184. The remaining 25 tests are unaffected by the `_file_sinks` removal.

- **`pyproject.toml` optional extras exact state** — `[project.optional-dependencies]` block is at lines 68-78. Current extras: `dev = [pytest, pytest-cov, hypothesis, mutmut, ruff, mypy, hatch]` (lines 69-77) and `llm = []` (line 78). Add `webhooks = ["httpx>=0.24.0"]` and `otel = ["opentelemetry-sdk>=1.20.0", "opentelemetry-exporter-otlp-grpc>=1.20.0"]` as new lines after line 78 within the same block.

- **`config-schema.json` `extensions` array at lines 896-901** — Run 7 cited lines 897-900 as the array pattern. Actual line range is 896-901. Pattern: `{"type": "array", "items": {"type": "string"}, "default": [], "description": "..."}`. No `"enum"` constraint — runtime code validates transport names. Use this exact pattern for `events.transports`.

- **`features.py` insertion point: after line 286** — `SyncConfig` ends at line 285 with `return cls(...)`. Line 286 is a trailing blank line. New `WebhookEventsConfig`, `OTelEventsConfig`, `EventsConfig` dataclasses insert starting at line 287 with no surrounding code to navigate.

- **`core.py` `events` property insertion precision** — `_parse_config()` has 12 typed config assignments; the last is `self._refine_status = RefineStatusConfig.from_dict(...)` at lines 113-115. Add `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))` as a new line after line 115. For the property: `refine_status` property ends at line 175; `extensions` property is at lines 177-180 (reads `_raw_config` directly, not a typed dataclass — this is intentional for extension paths). Insert the new `@property def events(self) -> EventsConfig` between lines 175 and 177 (i.e., at line 176, shifting `extensions` to 179+). Do NOT model the `events` property after `extensions` — `extensions` skips `_parse_config()` and reads raw config. The `events` property must follow the typed-dataclass pattern: `return self._events`.

- **`run.py` `finally:` block ordering** — The `finally:` block at line 172 currently has exactly one statement: `lock_manager.release(fsm.name)` at line 173. When adding `executor.close_transports()`, it MUST come before `lock_manager.release()` (transports flush before lock is released). Final block: `finally: executor.close_transports(); lock_manager.release(fsm.name)`. Note: `run_foreground()` is called with `return` at line 164 — the `finally:` executes on both normal return and raised exception, so `close_transports()` is guaranteed to run in all exit paths.

### Codebase Research Findings — Schema Position, Test Count Correction, `__init__` Imports, Import Guard Tests (run 11)

_Added by `/ll:refine-issue` — verified against current code:_

- **`config-schema.json` `events` block position — OUTSIDE `"properties"`** — `extensions` (line 896) is declared OUTSIDE the root `"properties"` block (which closes at line 895), not inside it. This is a structural irregularity in the schema. The new `events` block must be added at the same level: after line 895 (closing `}` of `"properties"`), before line 903 (`"additionalProperties": false`). The `events` block is a sibling of `extensions`, not a child of `"properties"`. Adding it inside `"properties"` would be a schema structure error.

- **`test_events.py` method count correction: 25, not 27** — Run 10 corrected "21 tests" to "27." The actual confirmed count is **25** `test_` methods (file spans lines 18–321). Run 10's count of 27 is incorrect. The 2 methods calling `add_file_sink` remain correctly identified: `test_file_sink` at line 170 and `test_file_sink_reads_back` at line 184.

- **No `__init__.py` changes required for `transport.py`** — `scripts/little_loops/__init__.py` re-exports `EventBus` (line 8 + `__all__:37`) and extension utilities. The new `transport.py` does not need to be added to `__init__.py`. All CLI callers use direct module imports (e.g., `sprint/run.py` uses `from little_loops.extension import wire_extensions`, not `from little_loops import wire_extensions`). The `run.py` transport call follows the same pattern: `from little_loops.transport import wire_transports`. If future public API exposure is needed, `__init__.py` can be updated then as a separate step.

- **Optional import test pattern — `builtins.__import__` mock** — `scripts/tests/test_issue_history_formatting.py:137-154` shows the codebase pattern for testing optional dependency guards: override `builtins.__import__` inside `with patch("builtins.__import__", side_effect=mock_import)` to raise `ImportError` for the target package. Use this to test `WebhookTransport.__init__` raises `RuntimeError("install httpx...")` and `OTelTransport.__init__` raises `RuntimeError("install opentelemetry-sdk...")` when their dependencies are absent. The mock function receives `name: str` as first arg — check `if name == "httpx": raise ImportError(...)`.

### Codebase Research Findings — Schema Position Correction, Import Update, Config Test Patterns (run 12)

_Added by `/ll:refine-issue` — verified against current code:_

- **`config-schema.json` position CORRECTION (contradicts run 11)** — Run 11 stated "extensions (line 896) is declared OUTSIDE the root `"properties"` block." This is **wrong**. Independent verification confirms `extensions` at line 896 is **inside** the top-level `"properties"` object, as a sibling of all other top-level keys (`project`, `issues`, `automation`, `sync`, `cli`, etc.). The root `"properties"` block closes at the `"additionalProperties": false` at line 903. Add `"events": { ... }` after `extensions` closes (`},` at line 902), before the root `"additionalProperties": false` at line 903 — as a sibling inside `"properties"`, not outside it.

- **`core.py` import update required — not yet documented in prior runs** — `scripts/little_loops/config/core.py` lines 21–27 contain `from little_loops.config.features import (IssuesConfig, LoopsConfig, ScanConfig, SprintsConfig, SyncConfig)`. After adding `EventsConfig` to `features.py`, add `EventsConfig` to this import tuple. This is a required change in addition to `_parse_config()` and the property — omitting it causes a `NameError` at runtime.

- **`core.py` precision confirmed** — `_parse_config()` last assignment is `self._refine_status` closing at line 115. Insert `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))` at line 116. Insert `@property def events(self) -> EventsConfig: return self._events` between `refine_status` property end (line 175) and `extensions` property start (line 177). `extensions` reads `_raw_config` directly (not typed-dataclass-backed); the new `events` property must NOT follow that pattern — use `return self._events`.

- **`test_events.py` count CONFIRMED: 25** — Run 10's "27" was incorrect; run 11's "25" is confirmed by independent line-by-line count: 7 (`TestLLEvent`) + 10 (`TestEventBus`) + 8 (`TestEventBusFilter`) = 25. `add_file_sink` is called at line 174 (`test_file_sink`, defined line 170) and line 188 (`test_file_sink_reads_back`, defined line 184). Exactly 2 of 25 tests need rewriting to `bus.add_transport(JsonlTransport(log_file))`.

- **BRConfig test pattern for EventsConfig** — Follow `test_config.py` patterns: use `temp_project_dir` fixture (from `conftest.py:55`), write `json.dumps({"events": {"transports": ["jsonl", "webhook"], "webhook": {"url": "http://example.com", "batch_ms": 500}, "otel": {"endpoint": "http://localhost:4317"}}})` to `temp_project_dir / ".ll" / "ll-config.json"`, construct `BRConfig(temp_project_dir)`, assert `config.events.transports == ["jsonl", "webhook"]`, `config.events.webhook.url == "http://example.com"`. Test defaults by constructing `BRConfig` with only `.ll/` dir (no file) and asserting `config.events.transports == []`.

- **`wire_transports()` test pattern** — Unlike `wire_extensions()` (which requires `patch.object(ExtensionLoader, "load_all", ...)`), `wire_transports` constructs transports inline from config. Test by calling `wire_transports(bus, EventsConfig(transports=["jsonl"]))` directly — no patching needed for `JsonlTransport` (uses `tmp_path`). For `webhook`/`otel` transport tests, construct `EventsConfig` with those names and either provide real optional deps (via `pytest.importorskip`) or verify `RuntimeError` is caught and logged as warning (not raised to caller) when deps are missing.

- **`run.py` try/finally ordering CONFIRMED** — `try:` at line 149; `PersistentExecutor` at line 150; `BRConfig` import+construction at lines 155–158; `wire_extensions` at line 159. `finally:` at line 172 with single statement `lock_manager.release(fsm.name)` at line 173. Add `executor.close_transports()` at line 172 **before** `lock_manager.release()`. Add `wire_transports(executor.event_bus, config.events)` at line 160, after `wire_extensions` at line 159.

### Codebase Research Findings — Parallel/Sprint Transport Wiring Gap (run 14)

_Added by `/ll:refine-issue` — verified against current code:_

- **`cli/parallel.py` needs transport wiring** — `main_parallel()` at `cli/parallel.py:225` creates `EventBus()` directly and calls `wire_extensions(event_bus, config.extensions)` at line 226, then passes the bus into `ParallelOrchestrator`. There is **no `wire_transports()` call and no `try/finally` block** around the orchestrator run. The current Implementation Step 7 only covers `loop/run.py`. Add a peer call `wire_transports(event_bus, config.events)` at line 227, immediately after `wire_extensions`. Since there is no `try/finally` in `main_parallel()`, transport teardown must happen either by adding one or by relying on `ParallelOrchestrator._cleanup()` (which currently ignores `self._event_bus` at `orchestrator.py:1238`). Cleanest fix: add a `try/finally` wrapper around `return orchestrator.run()` at line 237, closing transports in the `finally` clause (pattern mirrors `loop/run.py:172-173`). Alternatively, add a `close_transports(bus: EventBus)` helper in `transport.py` and call it in `ParallelOrchestrator._cleanup()` at line 1238 after `merge_coordinator.shutdown()`.

- **`cli/sprint/run.py` needs per-wave transport wiring** — The multi-issue wave loop at `sprint/run.py:387-399` creates a **new `EventBus()` per wave** at line 390, calls `wire_extensions(event_bus, ...)` at line 391, and passes the bus into `ParallelOrchestrator`. There is **no `wire_transports()` call** and no transport teardown after `orchestrator.run()` returns at line 397. The per-wave `EventBus` is never referenced again after line 397. Fix: add `wire_transports(event_bus, config.events)` at line 392 (after `wire_extensions`). For teardown, the sprint outer `try/finally` at lines 287-511 saves state only — no bus teardown. Since each wave `EventBus` is scoped to a single `orchestrator.run()` call, transport teardown can be handled by adding a `with contextlib.closing(event_bus)` wrapper (or delegating to `_cleanup()` as above). Note: `EventBus.close_transports()` would need to be added to `EventBus` (or used via `PersistentExecutor.close_transports()`'s fan-out) — same method needed by Implementation Step 8.

- **`ParallelOrchestrator._cleanup()` transport gap** — `orchestrator.py:1238-1251` calls `worker_pool.shutdown()` and `merge_coordinator.shutdown(wait=True)` but does **nothing** with `self._event_bus`. If transport teardown is delegated here (instead of at the CLI caller), add `if self._event_bus: self._event_bus.close_transports()` at line 1251 (after `merge_coordinator.shutdown()`). This covers both `cli/parallel.py` and `cli/sprint/run.py` in one change, since both pass their bus via `event_bus=event_bus` to `ParallelOrchestrator.__init__` (confirmed `orchestrator.py:61-85`). However, this means `EventBus` must gain a `close_transports()` method (not just `PersistentExecutor`). Consider exposing `EventBus.close_transports()` directly (callable from both `PersistentExecutor.close_transports()` and `ParallelOrchestrator._cleanup()`).

- **All prior file positions confirmed unchanged** — Independent verification of 15 file positions from runs 1-13 against current codebase: all confirmed accurate. No code has changed since run 13.

### Codebase Research Findings — Teardown Decision and Parallel/Sprint Wiring (run 15)

_Added by `/ll:refine-issue` — verified against current code:_

- **Teardown approach RESOLVED: use `EventBus.close_transports()` in `ParallelOrchestrator._cleanup()`** — Run 14 listed three approaches; this is the cleanest. `ParallelOrchestrator.run()` has its own `try/finally` at lines 140–175 that unconditionally calls `self._cleanup()`. `_cleanup()` (lines 1238–1251) already shuts down `worker_pool` and `merge_coordinator` but ignores `self._event_bus` (stored at line 85, read at lines 920–921 but never closed). Adding `if self._event_bus: self._event_bus.close_transports()` at `orchestrator.py:1247` (after `merge_coordinator.shutdown()`) covers both `cli/parallel.py` and `cli/sprint/run.py` in one change — no `try/finally` wrappers at CLI callers needed. `EventBus.close_transports()` must be added as a method on `EventBus` (not just on `PersistentExecutor`) to support this call path.

- **`parallel.py` wiring positions confirmed** — `EventBus()` at line 225, `wire_extensions()` at line 228. Add `wire_transports(event_bus, config.events)` at line 229. `orchestrator.run()` at line 237 (`return orchestrator.run()`, bare, no `try/finally` in `main_parallel()`). Transport teardown handled by `orchestrator._cleanup()` — no caller-side changes needed.

- **`sprint/run.py` wiring positions confirmed** — Within the multi-issue wave loop (`else:` branch at line 363): `EventBus()` at line 390, `wire_extensions()` at line 391. Add `wire_transports(event_bus, config.events)` at line 392. `orchestrator.run()` at line 399 (`result = orchestrator.run()`). Transport teardown handled by `orchestrator._cleanup()` — no per-wave `try/finally` needed.

- **`orchestrator._cleanup()` confirmed complete at line 1251** — Method ends at line 1251 with `self.worker_pool.cleanup_all_worktrees()`. The `if not self._shutdown_requested:` guard (line 1250) applies only to worktree cleanup, not to transport teardown. Add `if self._event_bus: self._event_bus.close_transports()` at line 1248, after `merge_coordinator.shutdown()` (line 1247) and before worktree cleanup (line 1250). Unconditional (not guarded by `_shutdown_requested`) — transports should flush on both clean and interrupted shutdowns.

- **`EventBus.close_transports()` required as a method on `EventBus`** — `PersistentExecutor.close_transports()` fans out through `self.event_bus._transports` (or a method call). For `ParallelOrchestrator._cleanup()` to call it via `self._event_bus.close_transports()`, the method must live on `EventBus` directly. Expose as `EventBus.close_transports() -> None: for t in self._transports: try: t.close() except Exception: logger.warning(...)`. `PersistentExecutor.close_transports()` can then delegate: `self.event_bus.close_transports()`.

- **Corrected Implementation Steps addendum (supersedes step 7/8 from run 13):**
  - **Step 7 (extended)**: Wire transports in `run.py` at line 160 (after `wire_extensions` at line 159), `parallel.py` at line 229 (after `wire_extensions` at line 228), and `sprint/run.py` at line 392 (after `wire_extensions` at line 391). All three use `wire_transports(event_bus, config.events)` with `from little_loops.transport import wire_transports`.
  - **Step 8 (extended)**: Add `EventBus.close_transports()` method that fans out `t.close()` for each transport with per-transport exception isolation. `PersistentExecutor.close_transports()` delegates to `self.event_bus.close_transports()`. Add call in `run.py:172` `finally:` block (before `lock_manager.release()`). Add call in `orchestrator._cleanup()` at line 1248 as `if self._event_bus: self._event_bus.close_transports()`.

### Codebase Research Findings — `lifecycle.py` Wiring Gap in Step 7 (run 16)

_Added by `/ll:refine-issue` — verified against current code:_

- **`lifecycle.py:261` missing from corrected Step 7** — The acceptance criteria (issue line 148) lists `cli/loop/lifecycle.py` line 261 as a required `wire_transports()` call site. The corrected Step 7 addendum (run 14/15) covers only `run.py`, `parallel.py`, and `sprint/run.py` — `lifecycle.py` is absent. `cmd_resume` at `lifecycle.py:180` follows an identical setup pattern to `cmd_run`: constructs `PersistentExecutor(fsm, loops_dir=loops_dir)` at line 251 (which internally creates `EventBus` at `persistence.py:344`), loads `BRConfig(Path.cwd())` at line 259, calls `wire_extensions(executor.event_bus, config.extensions)` at line 260. Line 261 is a blank line between `wire_extensions` and `result = executor.resume()` at line 262. **Add `wire_transports(executor.event_bus, config.events)` at line 261** and add `from little_loops.transport import wire_transports` to the import block at lines 255–260 alongside the existing `wire_extensions` import.

- **`cmd_resume` has no `try/finally` — teardown requires wrapping** — Unlike `cmd_run` (`run.py:149-173` wraps executor creation through execution in a `try/finally` that releases the lock), `cmd_resume` (lines 211–280) is a flat sequence with no enclosing `try/finally` and no lock manager. To guarantee transport teardown on clean return, `KeyboardInterrupt`, and any exception from `executor.resume()`, wrap lines 251–279 in a `try/finally` and add `executor.close_transports()` in the `finally`. Without this, `WebhookTransport` daemon threads are killed on exception without flushing the final batch.

- **`test_cli_loop_lifecycle.py` update required** — Issue line 106 already notes this test file needs updating "to cover `wire_transports` call added to `cmd_resume`." Confirm test invokes `cmd_resume` with an `EventsConfig`-bearing config, asserts `wire_transports` is called on `executor.event_bus`, and asserts `close_transports()` is called in the teardown path.

- **Step 7 final form** (supersedes run 14/15 addendum): Wire `wire_transports(executor.event_bus, config.events)` in four files: `run.py:160` (after `wire_extensions:159`), `lifecycle.py:261` (after `wire_extensions:260`), `parallel.py:229` (after `wire_extensions:228`), `sprint/run.py:392` (after `wire_extensions:391`). All four use `from little_loops.transport import wire_transports`. Teardown: `executor.close_transports()` in `run.py:172 finally:` and `lifecycle.py` new `finally:`; `self._event_bus.close_transports()` in `orchestrator._cleanup():1248`.

### Codebase Research Findings — All Positions Verified; Corrected Implementation Steps (run 13)

_Added by `/ll:refine-issue` — verified against current code:_

**Verification pass (run 13)**: All file positions from prior runs confirmed still accurate. No code changes since last refinement. Confirmed positions: `run.py:150` (PersistentExecutor), `run.py:159` (wire_extensions), `run.py:172-173` (finally/lock_manager.release), `events.py:76` (_file_sinks), `events.py:102-105` (add_file_sink), `events.py:124-129` (file-sink emit loop), `features.py:286` (SyncConfig.from_dict end), `core.py:21-27` (features import tuple), `core.py:113-115` (_refine_status assignment), `core.py:175` (refine_status property end), `core.py:177` (extensions property start).

**Corrected Implementation Steps** (supersede the Implementation Steps section above — synthesized from runs 1-12):

1. **Create `scripts/little_loops/transport.py`** — new module alongside `events.py`/`extension.py`. Define `Transport(Protocol, runtime_checkable)` with `def send(self, event: dict[str, Any]) -> None: ...` and `def close(self) -> None: ...` (model after `extension.py:19-49`). All transport implementations (`JsonlTransport`, `UnixSocketTransport`, `WebhookTransport`, `OTelTransport`) and `wire_transports()` live here.

2. **Refactor `EventBus` in `events.py`** — (a) Remove `_file_sinks: list[Path]` (line 76) and `add_file_sink()` (lines 102–105) — dead code, zero production callers; (b) Add `_transports: list[Transport] = []` and `add_transport(t: Transport) -> None`; (c) Replace lines 124–129 with per-transport fan-out matching observer exception isolation pattern: `try: t.send(event) / except Exception: logger.warning(...)`.

3. **Fix `loop_resume` bypass** — Add `self.event_bus.emit(resume_event)` at `persistence.py:507`, immediately after `self.persistence.append_event(resume_event)` (line 506) and before `return self.run(clear_previous=False)` (line 509).

4. **Implement transports in `transport.py`** — `JsonlTransport.__init__(path)`: replicate `add_file_sink()` mkdir call then append-write on `send()`. `UnixSocketTransport`: AF_UNIX SOCK_STREAM server, `settimeout(1.0)`, `_accept_thread` spawning per-client daemon threads with `Queue`, `unlink(missing_ok=True)` before `bind()`. `WebhookTransport`: daemon batch thread with `Queue`, exponential retry (pattern: `git_lock.py:110-181`, max_retries=3, backoff 0.5→8.0), `close()` sets shutdown, puts `None` sentinel, joins with `timeout=10.0`, final batch flush. `OTelTransport`: stateful spans (`_loop_span`, `_state_span`, `_action_span`, `_loop_ctx`, `_state_ctx`), `start_span()` with manual context, `close()` calls `force_flush()` + `shutdown()`. Guard optional deps with `try/except ImportError` in `__init__`.

5. **Add `EventsConfig` dataclasses** — In `features.py` starting at line 287: `WebhookEventsConfig` (fields: `url: str | None = None`, `batch_ms: int = 1000`, `headers: dict[str, str] = field(default_factory=dict)`), `OTelEventsConfig` (fields: `endpoint: str = "http://localhost:4317"`, `service_name: str = "little-loops"`), `EventsConfig` (fields: `transports: list[str] = field(default_factory=list)`, `webhook: WebhookEventsConfig = field(default_factory=WebhookEventsConfig)`, `otel: OTelEventsConfig = field(default_factory=OTelEventsConfig)`). In `core.py`: add `EventsConfig` to import tuple at lines 21–27; add `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))` at line 116; add `@property def events(self) -> EventsConfig: return self._events` between line 175 and 177.

6. **Extend `config-schema.json`** — Add `"events"` inside top-level `"properties"` (sibling of `extensions`, before `"additionalProperties": false` at line 903). Use plain array (`{"type": "array", "items": {"type": "string"}, "default": []}`) for `events.transports` — no enum constraint. Nested `webhook` and `otel` objects following `sync.github` pattern; every nested object closes with `"additionalProperties": false`.

7. **Wire transports in `run.py`** — Add `from little_loops.transport import wire_transports` alongside `wire_extensions` import at line 156. Add `wire_transports(executor.event_bus, config.events)` at line 160. Add `executor.close_transports()` as first statement in the `finally:` block (before `lock_manager.release(fsm.name)` at line 173).

8. **Add `close_transports()` to `PersistentExecutor`** — New method fans out `t.close()` for each transport via `self.event_bus._transports` (or a new `EventBus.close_transports()` method).

9. **Add optional extras to `pyproject.toml`** — After line 78 in `[project.optional-dependencies]`: `webhooks = ["httpx>=0.24.0"]` and `otel = ["opentelemetry-sdk>=1.20.0", "opentelemetry-exporter-otlp-grpc>=1.20.0"]`.

10. **Write tests** — (a) Rewrite `test_events.py` lines 170 and 184 (`test_file_sink`, `test_file_sink_reads_back`) to use `bus.add_transport(JsonlTransport(log_file))`; 23 of 25 tests unaffected. (b) Add `test_transport.py`: Protocol satisfaction tests (pattern: `test_extension.py:19-32`), per-transport lifecycle, error-isolation test (pattern: `test_events.py:140-154`). (c) Config tests in `test_config.py` (pattern: `temp_project_dir` fixture, assert `config.events.transports`). (d) Optional-dependency guard tests via `builtins.__import__` mock (pattern: `test_issue_history_formatting.py:137-154`). (e) Threading tests (patterns: `test_merge_coordinator.py:1380-1395`, `test_overlap_detector.py:158-184`). (f) OTel tests: `pytest.importorskip("opentelemetry.sdk")`, `InMemorySpanExporter` + `SimpleSpanProcessor`.

### Codebase Research Findings — Sprint Single-Issue Path & Final Verification (run 16)

_Added by `/ll:refine-issue` — verified against current code:_

- **Single-issue sprint path has no EventBus** — `cli/sprint/run.py:320-362` (the `if len(wave) == 1 or is_contention_subwave:` branch) delegates to `process_issue_inplace()` which has no `EventBus` reference. Transport wiring in `sprint/run.py` is ONLY needed in the multi-issue `else:` branch at line 390 (confirmed: run 15 positions are accurate). No change needed for the single-issue path.

- **`issue_manager.py:735` EventBus** — `AutoManager.__init__` constructs `EventBus()` bare and passes it only to `StateManager`. No `wire_extensions` call exists; no `wire_transports` needed. Confirmed out of scope (consistent with run 7 decision).

- **All implementation artifacts confirmed absent** — as of 2026-04-03: `transport.py` does not exist; `EventsConfig`/`WebhookEventsConfig`/`OTelEventsConfig` do not exist in `features.py`; `wire_transports` symbol does not exist anywhere in `scripts/`; `EventBus.close_transports()` and `PersistentExecutor.close_transports()` do not exist. No partial implementations. Implementation starts from scratch.

- **Confidence check concerns now resolved** — The `/ll:confidence-check` notes at bottom of file cite "acceptance criteria are incomplete" (missing parallel/sprint wiring and loop_resume fix). These were added in runs 14-15 and ARE present in the Acceptance Criteria section. Teardown ambiguity (three approaches) was resolved in run 15: use `EventBus.close_transports()` in `ParallelOrchestrator._cleanup()`. Research contradiction (runs 11-12 on schema position) resolved in run 12: `events` block is inside top-level `"properties"`, confirmed in run 13. All confidence check concerns addressed.

- **Test count CONFIRMED: 25** — 7 (`TestLLEvent`) + 10 (`TestEventBus`) + 8 (`TestEventBusFilter`) = 25. Exactly 2 tests call `add_file_sink`: `test_file_sink` (line 170) and `test_file_sink_reads_back` (line 184). `test_transport.py` does not exist.

### Codebase Research Findings — Import Locations and Final Position Verification (run 17)

_Added by `/ll:refine-issue` — verified against current code:_

- **`wire_transports` import positions (missing from all prior runs)** — Each CLI file uses inline lazy imports for `wire_extensions`. Follow the same pattern for `wire_transports`:
  - `run.py:156-157`: current code is `from little_loops.extension import wire_extensions` at line 156. Add `from little_loops.transport import wire_transports` as a new line 157 (immediately after).
  - `parallel.py:226-227`: current code is `from little_loops.extension import wire_extensions` at line 226, blank line at 227, then `wire_extensions(event_bus, config.extensions)` at line 228. Add `from little_loops.transport import wire_transports` at line 227 (replacing the blank line, or as a new line between import and call).
  - `sprint/run.py:388-389`: current code is `from little_loops.extension import wire_extensions` at line 388, then `event_bus = EventBus()` at line 390. Add `from little_loops.transport import wire_transports` as a new line 389 (between the import at 388 and `event_bus = EventBus()` at 390).

- **Run 7 line-226 correction for `parallel.py`** — Run 7 stated `wire_extensions(event_bus, config.extensions)` is "at line 226." This is incorrect. Line 226 is `from little_loops.extension import wire_extensions` (the import statement). The actual call `wire_extensions(event_bus, config.extensions)` is at line 228. Run 15's positions were correct all along.

- **`sprint/run.py` confirmed positions (run 17)** — EventBus construction at line 390; `wire_extensions(event_bus, config.extensions)` at line 391; `orchestrator = ParallelOrchestrator(...)` at line 392. Insert `wire_transports(event_bus, config.events)` as a new line between 391 and 392 (before orchestrator construction).

- **`orchestrator._cleanup()` confirmed positions (run 17)** — `worker_pool.shutdown(wait=True)` at line 1246; `merge_coordinator.shutdown(wait=True, timeout=30)` at line 1247; blank line at 1248; `# Clean up worktrees if not interrupted` comment at 1249; `if not self._shutdown_requested:` at 1250; `self.worker_pool.cleanup_all_worktrees()` at 1251. Insert `if self._event_bus: self._event_bus.close_transports()` at line 1248 (after `merge_coordinator.shutdown()`, before worktree comment). `self._event_bus` confirmed stored at line 85.

- **All positions from runs 1–16 confirmed unchanged** — No code changes since run 16. Implementation starts from scratch; no partial progress in codebase.

### Codebase Research Findings — EventBus Insertion Points and Test Impact (run 18)

_Added by `/ll:refine-issue` — verified against current code:_

- **`add_transport()` and `close_transports()` exact insertion point in `events.py`** — `EventBus` method inventory confirmed: `__init__` (74–76), `register` (78–93), `unregister` (95–100), `add_file_sink` (102–105), `emit` (107–129), `read_events` (staticmethod, 131–150). The class ends at line 150 (last line of `read_events`, also last line of file). Insert `add_transport(t: Transport) -> None` and `close_transports() -> None` between lines 105 and 107 — directly after `add_file_sink()` ends and before `emit()` begins. This placement groups mutation methods together and keeps them adjacent to the `_transports` attribute init in `__init__`.

- **`EventBus.close_transports()` method body**: `def close_transports(self) -> None:` fanout: `for t in self._transports: try: t.close() / except Exception: logger.warning("EventBus transport close failed: %s", t, exc_info=True)`. This mirrors the `emit()` observer exception isolation at lines 119–122.

- **`loop_resume` fix precision** — Line 506: `self.persistence.append_event(resume_event)`; line 507: `# Continue execution (don't clear previous events)` (a comment, NOT a statement); line 509: `return self.run(clear_previous=False)`. Insert `self.event_bus.emit(resume_event)` between lines 506 and 507 (i.e., as the new line 507, shifting the comment to 508 and `return` to 510). Prior runs cited "line 507" as the insertion target — that is correct for the resulting position, as the comment was previously at 507.

- **`test_fsm_persistence.py:745` — `loop_resume` test exists but doesn't cover EventBus** — `test_resume_emits_resume_event` at line 745 verifies `loop_resume` is written to the JSONL persistence file but does NOT assert the event reaches `EventBus`. When the bypass is fixed, consider adding an assertion: attach an accumulator observer to `executor.event_bus`, run resume, assert the accumulator received a `loop_resume` event. Follow the `received: list[dict] = []` pattern from `test_events.py`.

- **No `test_fsm_persistence.py` updates required for `close_transports()` addition** — `TestPersistentExecutor` (line ~550) and `TestAcceptanceCriteriaPersistence` (line ~1044) have zero references to `EventBus`, `event_bus`, `add_file_sink`, `add_transport`, or `close_transports`. Adding `PersistentExecutor.close_transports()` requires no changes to existing persistence tests — only new tests in `test_transport.py`.

- **All positions from runs 1–17 confirmed unchanged** — No code changes since run 17.

### Codebase Research Findings — Path Correction and Missing Test Coverage (run 19)

_Added by `/ll:refine-issue` — verified against current code:_

- **`git_lock.py` PATH CORRECTION (affects runs 5, 8, 13)** — Runs 5, 8, and Implementation Step 4 (run 13) cite `git_lock.py:110-181` as the retry pattern reference. The actual path is `scripts/little_loops/parallel/git_lock.py`, not `scripts/little_loops/git_lock.py`. The file lives in the `parallel/` subdirectory alongside `merge_coordinator.py` and `orchestrator.py`. Correct reference: `scripts/little_loops/parallel/git_lock.py:110-181` for the exponential retry pattern used to model `WebhookTransport` retry logic.

- **`test_orchestrator.py` missing from Integration Map Tests** — `scripts/tests/test_orchestrator.py` tests `ParallelOrchestrator`, including `_cleanup()` behavior. FEAT-918 modifies `_cleanup()` at line 1248 to call `self._event_bus.close_transports()`. New tests should follow `test_orchestrator.py` patterns: mock `EventBus` passed as `event_bus=mock_bus` to `ParallelOrchestrator.__init__`, assert `mock_bus.close_transports()` is called during `_cleanup()`. This file was not previously listed in the Tests section.

- **`docs/reference/EVENT-SCHEMA.md` missing from Documentation** — This doc describes the EventBus event schema and is relevant for documenting Transport behavior and new transport-specific event routing (particularly the `action_output` high-volume event note from run 6). May need updating when the Transport system ships to describe which events each transport receives.

- **All positions from runs 1–18 confirmed unchanged** — No code changes since run 18. `transport.py` does not exist; `EventsConfig` not in `features.py` or `core.py`; no partial implementation exists.

### Codebase Research Findings — `test_orchestrator.py` Pattern and `EVENT-SCHEMA.md` Gap (run 20)

_Added by `/ll:refine-issue` — verified against current code:_

- **`TestCleanup._cleanup` test pattern for transport teardown** — `TestCleanup` class starts at `test_orchestrator.py:1726`. Existing `test_cleanup_shuts_down_components` (lines 1759–1771) calls `orchestrator._cleanup()` and asserts `orchestrator.worker_pool.shutdown.assert_called_once()` and `orchestrator.merge_coordinator.shutdown.assert_called_once()`. New FEAT-918 test: inject mock bus via `orchestrator._event_bus = MagicMock()` (same injection pattern as `test_on_worker_complete_emits_event_on_success` at lines 1409–1414 which uses `orchestrator._event_bus = bus`), call `orchestrator._cleanup()`, assert `orchestrator._event_bus.close_transports.assert_called_once()`. No `side_effect` needed — just verify the call was made. The `if self._event_bus:` guard in `_cleanup()` protects the `None` default case; test the guard separately: `orchestrator._event_bus = None`, call `_cleanup()`, assert no `AttributeError`.

- **`orchestrator` fixture creates instance WITHOUT `event_bus=`** — Confirmed at lines 143–148: `ParallelOrchestrator(parallel_config=..., br_config=..., repo_path=..., verbose=False)` — no `event_bus=` keyword. Default `_event_bus` is `None`. The `if self._event_bus:` guard in `_cleanup()` is therefore the normal case for the base fixture — new tests that need a bus must inject it directly via `orchestrator._event_bus = ...`.

- **`EVENT-SCHEMA.md` has no transport section — update required when FEAT-918 ships** — `docs/reference/EVENT-SCHEMA.md` ends with a Quick Reference table (line 500+) listing all 12 FSM events plus `loop_resume`, `state.issue_completed`, etc. No mention of transports, transport routing behavior, or `action_output` volume guidance. Add a "Transport Behavior" section to `EVENT-SCHEMA.md` when FEAT-918 ships, noting: (a) unfiltered fan-out — all events reach all transports (unlike observer pattern which supports `fnmatch` glob filtering); (b) `action_output` is high-volume (hundreds per state) — OTel transport maps it to span events on the action span rather than child spans to avoid span explosion; (c) `loop_resume` was previously bypassed by `PersistentExecutor` (writing only to JSONL, not through `EventBus`) and is now routed through `EventBus` as part of this feature. The `## Quick Reference` table at line 500 should also annotate `loop_resume` with a note that it required a bypass fix.

- **All positions from runs 1–19 confirmed unchanged** — No code changes since run 19. `transport.py` does not exist; `EventsConfig` not in `features.py` or `core.py`; no partial implementation exists.

### Codebase Research Findings — Consolidated Implementation Checklist and Test Patterns (run 24)

_Added by `/ll:refine-issue` — all positions verified against current code; no changes since run 23:_

**This section is the authoritative implementation reference.** It supersedes the original Implementation Steps (line 153), the corrected steps (run 13), and all subsequent addenda. Read this section first; treat all prior step lists as supporting research only.

#### Consolidated Implementation Checklist

**Step 1 — Create `scripts/little_loops/transport.py`**
- New module alongside `events.py`/`extension.py`
- `Transport(Protocol, runtime_checkable)`: `def send(self, event: dict[str, Any]) -> None: ...` and `def close(self) -> None: ...` — model after `extension.py:19-49`
- Implement `JsonlTransport`, `UnixSocketTransport`, `WebhookTransport`, `OTelTransport` (see runs 4, 8, 9 for full architecture of each)
- Implement `wire_transports(bus: EventBus, config: EventsConfig) -> None` — see run 9 for full body

**Step 2 — Refactor `EventBus` in `events.py`**
- Add `from typing import TYPE_CHECKING` after `from typing import Any` at line 20; add `if TYPE_CHECKING: from little_loops.transport import Transport` (circular import guard — `from __future__ import annotations` at line 12 makes the runtime annotation safe)
- Remove `_file_sinks: list[Path]` (line 76) and `add_file_sink()` (lines 102–105) — dead code, zero production callers
- Add `_transports: list[Transport] = []` to `__init__` (line 75 region)
- Insert between lines 105 and 107: `add_transport(t: Transport) -> None` and `close_transports() -> None` (fan-out with per-transport exception isolation matching observer pattern at `events.py:119-122`)
- Replace lines 124–129 (file-sink loop) with per-transport fan-out: `for t in self._transports: try: t.send(event) / except Exception: logger.warning(...)`

**Step 3 — Fix `loop_resume` bypass in `persistence.py`**
- Insert `self.event_bus.emit(resume_event)` at line 507 (after `append_event` at line 506, before comment at line 507/508)

**Step 4 — Implement transports in `transport.py`**
- `JsonlTransport.__init__(path)`: mkdir (replicate `add_file_sink` mkdir), append-write in `send()`; use `.ll/events.jsonl` in `wire_transports`
- `UnixSocketTransport`: `unlink(missing_ok=True)` before `bind()`, `settimeout(1.0)`, daemon `_accept_thread`, per-client daemon threads with `Queue`, `None` sentinel in `close()`
- `WebhookTransport`: daemon batch thread, exponential retry (model: `scripts/little_loops/parallel/git_lock.py:110-181`, max_retries=3, backoff 0.5→8.0), drain-on-close (final flush after `_shutdown_event.set()`)
- `OTelTransport`: stateful spans (`_loop_span`, `_state_span`, `_action_span`, `_loop_ctx`, `_state_ctx`), `start_span()` with manual context, `close()` calls `force_flush()` + `shutdown()`; guard with `try/except ImportError` in `__init__`
- `wire_transports`: iterate `config.transports`, construct transport, `bus.add_transport(t)`, `try/except RuntimeError` with `logger.warning(...)` on missing dep

**Step 5 — Add `EventsConfig` to `config/features.py`** (insert starting at line 287, end of file)
- `WebhookEventsConfig`: `url: str | None = None`, `batch_ms: int = 1000`, `headers: dict[str, str]`
- `OTelEventsConfig`: `endpoint: str = "http://localhost:4317"`, `service_name: str = "little-loops"`
- `EventsConfig`: `transports: list[str]`, `webhook: WebhookEventsConfig`, `otel: OTelEventsConfig`
- Model `from_dict` after `SyncConfig`/`GitHubSyncConfig` at `features.py:241-285`

**Step 6 — Wire `EventsConfig` into `config/core.py`**
- Add `EventsConfig` to import tuple at lines 21–27
- Add `self._events = EventsConfig.from_dict(self._raw_config.get("events", {}))` at line 116 (after `_refine_status` at lines 113–115)
- Insert `@property def events(self) -> EventsConfig: return self._events` between lines 175 and 177

**Step 7 — Extend `config-schema.json`**
- Add `"events"` inside root `"properties"` before `"additionalProperties": false` at line 903
- `events.transports`: plain array, no enum constraint — pattern: `extensions` at lines 896-901
- Nested `webhook` and `otel` objects each close with `"additionalProperties": false`

**Step 8 — Wire transports in all 4 CLI entry points**
- `run.py`: add `from little_loops.transport import wire_transports` at line 157; add `wire_transports(executor.event_bus, config.events)` at line 160; add `executor.close_transports()` as first statement in `finally:` at line 172 (before `lock_manager.release(fsm.name)`)
- `lifecycle.py`: add `from little_loops.transport import wire_transports` at line 258 (after `wire_extensions` import at line 257); add `wire_transports(executor.event_bus, config.events)` at line 261 (blank line); add `atexit.register(executor.close_transports)` at line 262 (before `result = executor.resume()`)
- `parallel.py`: add `from little_loops.transport import wire_transports` at line 227 (blank line between import at 226 and call at 228); add `wire_transports(event_bus, config.events)` at line 229 (before `orchestrator = ParallelOrchestrator(...)`)
- `sprint/run.py`: add `from little_loops.transport import wire_transports` at line 389 (between import at 388 and `event_bus = EventBus()` at 390); add `wire_transports(event_bus, config.events)` between lines 391 and 392 (after `wire_extensions`, before `orchestrator = ParallelOrchestrator(...)`)

**Step 9 — Add teardown in `orchestrator._cleanup()` at `orchestrator.py:1248`**
- Add `if self._event_bus: self._event_bus.close_transports()` after `merge_coordinator.shutdown()` at line 1247 (covers both `parallel.py` and `sprint/run.py` entry points)

**Step 10 — Add optional extras to `pyproject.toml`** (after line 78)
- `webhooks = ["httpx>=0.24.0"]`
- `otel = ["opentelemetry-sdk>=1.20.0", "opentelemetry-exporter-otlp-grpc>=1.20.0"]`

**Step 11 — Write tests**
- `test_events.py` lines 174 and 188: replace `bus.add_file_sink(log_file)` with `bus.add_transport(JsonlTransport(log_file))`; 23 of 25 tests unaffected
- `test_transport.py` (new): Protocol satisfaction, per-transport lifecycle, error-isolation (pattern: `test_events.py:140-154`), threading (pattern: `test_merge_coordinator.py:1380-1395`), optional-dep mocks (pattern: `test_issue_history_formatting.py:137-154`), OTel via `pytest.importorskip` + `InMemorySpanExporter` + `SimpleSpanProcessor`
- `test_config.py`: `EventsConfig` defaults and nested-key tests (pattern: `temp_project_dir` fixture + `BRConfig(temp_project_dir)`)
- `test_cli_loop_lifecycle.py`: Add `wire_transports` assertion to `cmd_resume` tests (patch `little_loops.cli.loop.lifecycle.wire_transports`, assert `called_once_with(executor.event_bus, config.events)`); add `close_transports` registration assertion using `side_effect=registered.append` on `atexit.register` (pattern: `test_cli_loop_lifecycle.py:547-560`), assert `registered[-1] == mock_exec_cls.return_value.close_transports`; add equivalent coverage in `TestCmdRunHandoffThreshold`/`TestCmdRunYAMLConfigOverrides` at lines 679-855 for `cmd_run` wiring
- `test_orchestrator.py` (`TestCleanup` at line 1726): inject mock bus via `orchestrator._event_bus = MagicMock()`, call `_cleanup()`, assert `mock_bus.close_transports.assert_called_once()`; also test `_event_bus = None` guard (no `AttributeError`)
- `test_fsm_persistence.py`: add accumulator observer to `test_resume_emits_resume_event` at line 745, assert `loop_resume` event reaches `EventBus` (not only JSONL)

#### New Findings — `atexit` Test Pattern with Exact References

- **Capturing `atexit.register` calls**: `test_cli_loop_lifecycle.py:547-560` — `registered: list = []` + `patch("little_loops.cli.loop.lifecycle.atexit.register", side_effect=registered.append)` → assert `len(registered) == N` and `registered[0] == <expected_callable>`. This is the direct template for asserting `atexit.register(executor.close_transports)` in FEAT-918.
- **Silencing without asserting**: `test_cli_loop_lifecycle.py:631-632` — plain `patch("little_loops.cli.loop.lifecycle.atexit.register")` when only need call to not fail.
- **`cmd_run` test location**: No `test_cli_loop_run.py` file exists. `cmd_run` is tested in `test_cli_loop_lifecycle.py:679-855` via `TestCmdRunHandoffThreshold` and `TestCmdRunYAMLConfigOverrides` (use real YAML loops with `dry_run=True`). Neither class currently mocks `wire_extensions`. FEAT-918 `wire_transports` assertions for `cmd_run` should be added to these classes.
- **`wire_extensions` unit test location**: `test_extension.py:135-258` — function-level tests using `patch.object(ExtensionLoader, "load_all", ...)`. The `wire_transports` unit tests follow a simpler pattern (no loader class) — pass `EventsConfig(transports=["jsonl"])` directly; no patching needed for `JsonlTransport`.

### Codebase Research Findings — `cmd_resume` 4th Wiring Site and CONFIGURATION.md Gap (run 22)

_Added by `/ll:refine-issue` — verified against current code:_

- **`cli/loop/lifecycle.py:cmd_resume` is the 4th CLI wiring site — missed in all prior runs** — `cmd_resume()` (lines 180-280) creates a `PersistentExecutor` at line 251, calls `wire_extensions(executor.event_bus, config.extensions)` at line 260, then calls `executor.resume()` at line 262. This mirrors `cmd_run`'s structure exactly, but was not identified in any of runs 1-21. `wire_transports(executor.event_bus, config.events)` must be added at line 261 (after `wire_extensions`). Unlike `cmd_run`, there is **no `try/finally` block and no `lock_manager`** in `cmd_resume` — transport teardown must be added via a new `try/finally` wrapping `executor.resume()` at line 262, with `executor.close_transports()` in the `finally` block. Alternatively, `atexit.register(executor.close_transports)` after line 261 avoids restructuring; `cmd_resume` already uses `atexit.register(_cleanup_pid)` at line 209 for PID cleanup — the same pattern applies.

- **`docs/reference/CONFIGURATION.md` needs `events` section** — Line 608 documents the `extensions` array config field (relationship to `LLEvent`/`EventBus`). When FEAT-918 ships, add an `events` section after `extensions` documenting `events.transports`, `events.webhook.url`, `events.webhook.batch_ms`, `events.otel.endpoint`. This is in addition to updating `docs/reference/API.md` and `docs/ARCHITECTURE.md` (already in Documentation section).

- **Implementation Step 7 extended — add `lifecycle.py` as 4th wiring site**: Add `from little_loops.transport import wire_transports` at line 258 (after `from little_loops.extension import wire_extensions` at line 257); add `wire_transports(executor.event_bus, config.events)` at line 261 (after `wire_extensions` at line 260); add teardown via `atexit.register(executor.close_transports)` at line 262 (after wiring, before `executor.resume()` at line 262 which shifts to 263). This covers all four CLI entry points: `cmd_run` (run.py), `cmd_resume` (lifecycle.py), `main_parallel` (parallel.py), wave loop (sprint/run.py).

- **`test_cli_loop_lifecycle.py` and `test_fsm_persistence.py` belong in Tests section** — `test_cli_loop_lifecycle.py` patches `little_loops.fsm.persistence.PersistentExecutor` across 13 test methods and tests `cmd_resume`; it must be updated to cover `wire_transports` call in `cmd_resume`. `test_fsm_persistence.py` tests `TestPersistentExecutor` (80+ cases) including `close_transports()` once added. Both were absent from the Integration Map Tests section.

- **All positions from runs 1–21 confirmed unchanged** — No code changes since run 21. `transport.py` does not exist; `EventsConfig` not in `features.py` or `core.py`; no partial implementation exists.

### Codebase Research Findings — Circular Import Resolution, Logger, and JsonlTransport Path (run 21)

_Added by `/ll:refine-issue` — verified against current code:_

- **Circular import: use `TYPE_CHECKING` guard in `events.py`** — `transport.py` will import `EventBus` from `events.py` (for `wire_transports(bus: EventBus, ...)`). If `events.py` also imports `Transport` from `transport.py` at runtime, there is a circular import. Resolution: `events.py` already has `from __future__ import annotations` at line 12, which makes all annotations lazy strings at runtime. Add to `events.py` (after line 20, before line 22):
  ```python
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      from little_loops.transport import Transport
  ```
  Then `def add_transport(self, t: "Transport") -> None:` works without a runtime import (mypy resolves it via `TYPE_CHECKING`). The `from __future__ import annotations` on line 12 makes the `Transport` annotation a string automatically, so no explicit quoting is required in practice — use `Transport` directly in the signature. This pattern is used extensively in the codebase (40+ files use `TYPE_CHECKING` guards, e.g., `work_verification.py:12-13`, `sprint.py:13-15`). `extension.py` avoids this problem entirely because it imports `EventBus` from `events.py` (one-directional; `events.py` currently has zero imports from other `little_loops` modules).

- **Logger already present in `events.py`** — `events.py:22` already declares `logger = logging.getLogger(__name__)`. It is already in active use at lines 122 and 129 (observer and file-sink exception guards in `emit()`). No new logger declaration needed in `close_transports()` or `add_transport()` — use `logger.warning(...)` directly, identical to the existing usage pattern.

- **`JsonlTransport` path decision — use `.ll/events.jsonl`** — Run 9's `wire_transports()` body proposes `Path(".ll/events.transport.jsonl")`. However, the API docs examples (`docs/reference/API.md:4932`, `:4989`) use `.ll/events.jsonl` as the unified event log path — consistent with FEAT-911's proposed unified log. Neither path exists in production code today (confirmed: zero matches for both across `scripts/little_loops/`). The existing `NoopLoggerExtension` writes to `.ll/extension-events.jsonl` (`extension.py:61`). Use `.ll/events.jsonl` in `wire_transports()` for the `jsonl` transport name to align with FEAT-911's intention and the API documentation examples. The per-loop `.loops/.running/<name>.events.jsonl` files written by `PersistentFSMPersistence.append_event()` are separate and unaffected.

- **All positions from runs 1–20 confirmed unchanged** — No code changes since run 20. `transport.py` does not exist; `EventsConfig` not in `features.py` or `core.py`; no partial implementation exists.

### Codebase Research Findings — Final Position Verification (run 23)

_Added by `/ll:refine-issue` — verified against current code:_

- **`events.py` ends at line 151, not 150** — Run 18 stated "The class ends at line 150 (last line of `read_events`, also last line of file)." Correction: `read_events` returns at line 150 (`return events`); line 151 is a trailing blank line. The insertion of `add_transport()` and `close_transports()` between lines 105–107 is unaffected. However, any instruction to "append after line 150" should read "append after line 150 (or before the trailing blank at line 151)."

- **`events.py` has no `TYPE_CHECKING` block — must be added** — Run 21 describes adding a `TYPE_CHECKING` guard to avoid a circular import between `events.py` and `transport.py`. Confirmed: no `from typing import TYPE_CHECKING` or `if TYPE_CHECKING:` block exists anywhere in `events.py` as of this run. Add after line 20 (`from typing import Any`): `from typing import TYPE_CHECKING` then `if TYPE_CHECKING: from little_loops.transport import Transport`. With `from __future__ import annotations` at line 12, annotation references to `Transport` in `add_transport(self, t: Transport)` are safe without quoting.

- **`lifecycle.py` run 22 positions CONFIRMED** — File is 281 lines. Exact verified positions for `cmd_resume()`: `PersistentExecutor` at line 251; lazy `BRConfig` import at line 256; lazy `wire_extensions` import at line 257; `config = BRConfig(Path.cwd())` at line 259; `wire_extensions(executor.event_bus, config.extensions)` at line 260; blank line at 261; `result = executor.resume()` at line 262. `atexit.register(_cleanup_pid)` confirmed at line 209 — the same pattern for transport teardown. No `try/finally` exists in `cmd_resume` (only a `try/except` at lines 211–218 for FSM load errors). **Insertion plan**: add `from little_loops.transport import wire_transports` at line 258 (between lines 257 and 259); add `wire_transports(executor.event_bus, config.events)` as new line 261; add `atexit.register(executor.close_transports)` as new line 262; `result = executor.resume()` shifts to line 264.

- **`features.py` insertion point confirmed** — `SyncConfig.from_dict` closing paren at line 285; line 286 is a trailing blank line (last line of file). New `WebhookEventsConfig`, `OTelEventsConfig`, `EventsConfig` dataclasses insert at line 287 (appended at end of file).

- **All positions from runs 1–22 confirmed unchanged** — No code changes since run 22. `transport.py` does not exist; `EventsConfig` not in `features.py` or `core.py`; no partial implementation exists.

### Codebase Research Findings — Position Corrections and Confirmations (run 25)

_Added by `/ll:refine-issue` — verified against current code; all positions from runs 1–24 still valid except corrections noted here:_

- **`persistence.py:507` is a BLANK LINE, not the comment** — Run 18 described "line 507: `# Continue execution (don't clear previous events)` (a comment, NOT a statement)." This is incorrect. Actual structure: `506` = `self.persistence.append_event(resume_event)`, `507` = blank line, `508` = `# Continue execution (don't clear previous events)`, `509` = `return self.run(clear_previous=False)`. Insert `self.event_bus.emit(resume_event)` after line 506 (blank shifts to 508, comment to 509, return to 510). The resulting line 507 is the new emit call. All prior guidance to "insert at line 507" remains correct in terms of resulting position.

- **`run.py` line 160 is `cli_colors = config.cli.colors`, not a blank line** — After `wire_extensions(executor.event_bus, config.extensions)` at line 159, line 160 is immediately `cli_colors = config.cli.colors`. Inserting `wire_transports(executor.event_bus, config.events)` at line 160 means it goes between `wire_extensions` and `cli_colors = config.cli.colors` (which shifts to line 161). No issue with implementation — this is the correct insertion point.

- **`run.py` `finally:` block confirmed** — `finally:` at line 172; sole statement `lock_manager.release(fsm.name)` at line 173. Add `executor.close_transports()` as new line 173 (before `lock_manager.release`, which shifts to line 174). Matches all prior descriptions.

- **`events.py` ends at line 150, no trailing blank** — Run 23 stated "line 151 is a trailing blank line." The current file ends at line 150 (`return events`). No line 151 exists. `add_transport()` and `close_transports()` insertion between lines 105–107 is unaffected.

- **`features.py` ends at line 285, no trailing blank** — Run 23 stated "line 286 is a trailing blank line (last line of file)." The file ends at line 285 (closing `)` of `SyncConfig.from_dict`). New `WebhookEventsConfig`, `OTelEventsConfig`, `EventsConfig` dataclasses append after line 285 — no line 286 exists.

- **`atexit` already imported in `lifecycle.py`** — `import atexit` at line 6 (top-level, not lazy). Run 22 proposed `atexit.register(executor.close_transports)` without confirming availability. Confirmed: no new import needed for the `atexit.register(executor.close_transports)` call at line 262.

- **`events.py` has no `TYPE_CHECKING` block** — Confirmed absent. Only `from typing import Any` at line 20. Add `from typing import TYPE_CHECKING` after line 20, then `if TYPE_CHECKING: from little_loops.transport import Transport` as a guard block (run 21/23 guidance unchanged).

- **All other positions from runs 1–24 confirmed unchanged** — `events.py`: `add_file_sink` at lines 102–105, `emit` at line 107. `core.py`: import tuple at lines 21–27; `_refine_status` at lines 113–115; blank at line 116; `@property` at line 117; `refine_status` ends at line 175; `extensions` at line 177. `lifecycle.py`: `wire_extensions` import at line 257, call at line 260, blank at line 261, `executor.resume()` at line 262.

### Codebase Research Findings — Position Verification (run 26)

_Added by `/ll:refine-issue` — verified against current code; all positions from runs 1–25 still valid except corrections noted here:_

- **`features.py` ends at line 286 (blank), NOT 285** — Run 25 stated "The file ends at line 285 (closing `)` of `SyncConfig.from_dict`). No line 286 exists." Independent verification confirms line 286 IS a blank line (trailing newline after the closing `)`). The new `WebhookEventsConfig`, `OTelEventsConfig`, `EventsConfig` dataclasses should be appended starting at line **287** — restoring the original position from runs 12/23 that run 25 incorrectly overrode.

- **`events.py` ends at line 151 (trailing newline)** — Run 25 stated "The current file ends at line 150. No line 151 exists." Independent verification: line 150 is `return events`; line 151 is a trailing newline. This does not affect any insertion point (insertions are between lines 105–107, not at end of file).

- **All other positions from runs 1–25 confirmed unchanged** — `transport.py` does not exist; `EventsConfig` not in `features.py` or `core.py`; no partial implementation exists. `persistence.py:506-509` structure confirmed (`append_event` at 506, blank at 507, comment at 508, `return self.run` at 509). `lifecycle.py:261` confirmed blank (after `wire_extensions` at 260, before `executor.resume()` at 262). `run.py:160` confirmed as `cli_colors = config.cli.colors` (after `wire_extensions` at 159). `features.py` import tuple at `core.py:21-27` confirmed unchanged.

### Codebase Research Findings — Final Position Reconfirmation (run 27)

_Added by `/ll:refine-issue` — all positions from runs 1–26 verified directly via Read tool against current file content:_

- **All positions from runs 1–26 confirmed unchanged** — No code changes since run 26. `transport.py` does not exist; `EventsConfig` not in `features.py` or `core.py`; no partial implementation exists.
- **`run.py` positions CONFIRMED via direct read** — Lazy imports block: `from little_loops.config import BRConfig` at line **155**; `from little_loops.extension import wire_extensions` at line **156**; blank at line **157**; `config = BRConfig(Path.cwd())` at line **158**; `wire_extensions(executor.event_bus, config.extensions)` at line **159**; `cli_colors = config.cli.colors` at line **160**; `finally:` at line **172**; `lock_manager.release(fsm.name)` at line **173**. The run 24 consolidated Step 8 positions are accurate: `wire_transports` import inserts at line 157 (replacing blank, or as new line after 156); `wire_transports(executor.event_bus, config.events)` call inserts at line 160 (before `cli_colors`, which shifts to 161); `executor.close_transports()` inserts at line 173 (before `lock_manager.release`, which shifts to 174).
- **The run 24 Consolidated Implementation Checklist remains the authoritative reference** — No corrections required.

### Codebase Research Findings — TestCleanup Patterns and Position Corrections (run 28)

_Added by `/ll:refine-issue` — all positions from runs 1–27 verified via direct file read; corrections noted here:_

- **`TestCleanup` at line 1725, not 1726** — Run 20 stated "TestCleanup class starts at `test_orchestrator.py:1726`." The actual position is **line 1725**. `test_cleanup_shuts_down_components` is at line 1759 (matches run 20 ✓). This 1-line correction does not affect implementation — new tests are still added to `TestCleanup`.

- **Queue setup required in ALL `TestCleanup` tests** — Every existing test in `TestCleanup` sets three attributes before calling `orchestrator._cleanup()`:
  ```python
  orchestrator.queue.completed_ids = []    # type: ignore[misc]
  orchestrator.queue.failed_ids = []       # type: ignore[misc]
  orchestrator.queue.in_progress_ids = []  # type: ignore[misc]
  ```
  The `orchestrator` fixture (line 132) sets `completed_ids = []` and `failed_ids = []` at lines 150–151 but does **not** set `in_progress_ids`. Each test must set it independently or `_save_state(force=True)` will fail. New FEAT-918 tests in `TestCleanup` must include all three assignments.

- **Exact FEAT-918 test skeleton for `TestCleanup`** (modeled after `test_cleanup_cleans_worktrees_when_not_shutdown` at line 1773, which injects `orchestrator._shutdown_requested = False` — same attribute-injection pattern):
  ```python
  def test_cleanup_closes_transports(
      self, orchestrator: ParallelOrchestrator,
  ) -> None:
      """_cleanup closes EventBus transports."""
      mock_bus = MagicMock()
      orchestrator._event_bus = mock_bus
      orchestrator.queue.completed_ids = []        # type: ignore[misc]
      orchestrator.queue.failed_ids = []           # type: ignore[misc]
      orchestrator.queue.in_progress_ids = []      # type: ignore[misc]
      orchestrator._cleanup()
      mock_bus.close_transports.assert_called_once()

  def test_cleanup_handles_none_event_bus(
      self, orchestrator: ParallelOrchestrator,
  ) -> None:
      """_cleanup with None event_bus raises no AttributeError."""
      orchestrator._event_bus = None
      orchestrator.queue.completed_ids = []        # type: ignore[misc]
      orchestrator.queue.failed_ids = []           # type: ignore[misc]
      orchestrator.queue.in_progress_ids = []      # type: ignore[misc]
      orchestrator._cleanup()  # must not raise
  ```

- **`parallel.py` `return orchestrator.run()` confirmed at line 237** — blank at 236, return at 237. After inserting `wire_transports(event_bus, config.events)` at new line 229 (before current `orchestrator = ParallelOrchestrator(...)` at line 229), `return orchestrator.run()` shifts to line 238. No `try/finally` exists in `main_parallel()` — transport teardown via `_cleanup()` only. ✓

- **All positions from runs 1–27 confirmed unchanged** — No code changes since run 27. `transport.py` does not exist; `EventsConfig` not in `features.py` or `core.py`; no partial implementation exists. The run 24 Consolidated Implementation Checklist remains the authoritative reference.

### Codebase Research Findings — cmd_run Test Pattern and Position Reconfirmation (run 29)

_Added by `/ll:refine-issue` — verified against current code; all positions from runs 1–28 confirmed unchanged:_

- **`TestCmdRunHandoffThreshold`/`TestCmdRunYAMLConfigOverrides` are integration tests, not unit tests** — Both classes (lines 679–855 of `test_cli_loop_lifecycle.py`) call `cmd_run(...)` directly with a real FSM loop on disk. Neither class mocks `PersistentExecutor`, `wire_extensions`, or `atexit`. Step 11 of the Consolidated Checklist says "add equivalent coverage in these classes for `cmd_run` wiring" — but adding mock-based `wire_transports` assertions to integration tests requires `monkeypatch.setattr("little_loops.cli.loop.run.wire_transports", ...)` inline per test, which is awkward and couples transport testing to FSM execution behavior. **Better approach**: add a NEW dedicated unit test class `TestCmdRunTransportWiring` (pattern: `TestCmdRunHandoffThreshold._make_args()` / `TestCmdRunYAMLConfigOverrides._make_args()` for arg construction, but mock `PersistentExecutor` and `wire_transports`). Use `monkeypatch.setattr` or `patch` for: `little_loops.cli.loop.run.PersistentExecutor`, `little_loops.cli.loop.run.wire_transports`, `little_loops.cli.loop.run.wire_extensions`. Assert `mock_wire_transports.assert_called_once_with(mock_executor.event_bus, mock_config.events)` and `mock_executor.close_transports.assert_called_once()` (from finally block). Place the class after `TestCmdRunYAMLConfigOverrides` (line 855+).

- **All file positions from runs 1–28 confirmed unchanged by direct read** — `lifecycle.py`: `atexit.register(_cleanup_pid)` at line 209 ✓; `PersistentExecutor` at line 251 ✓; `from little_loops.config import BRConfig` at line 256 ✓; `from little_loops.extension import wire_extensions` at line 257 ✓; `config = BRConfig(Path.cwd())` at line 259 ✓; `wire_extensions(executor.event_bus, config.extensions)` at line 260 ✓; blank at line 261 ✓; `result = executor.resume()` at line 262 ✓. `events.py`: `_file_sinks: list[Path] = []` at line 76 ✓; `add_file_sink()` at lines 102–105 (def 102, docstring 103, mkdir 104, append 105) ✓; file-sink loop in `emit()` at lines 124–129 ✓. `transport.py` does not exist; no partial implementation present.

## Status

**Open** | Created: 2026-04-02 | Priority: P5

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-03_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 53/100 → LOW

### Outcome Risk Factors
- **Complexity ceiling**: 12+ source files across 6 subsystems (transport, events, FSM persistence, 4 CLI entry points, config, packaging). OTel span state machine (`_loop_span`, `_state_span`, `_action_span` with manual context threading) and Unix socket multi-client broadcast are independently complex — plan for iteration on these two specifically.
- **Navigation hazard**: The issue has multiple "Implementation Steps" sections at different precedence levels. **Start from the run 24 consolidated checklist** ("Consolidated Implementation Checklist and Test Patterns") — it supersedes the original steps (line 153), run 13 corrected steps, and all addenda.

## Session Log
- `/ll:refine-issue` - 2026-04-03T13:07:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T12:59:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T12:53:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T12:45:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T12:36:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T12:29:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T20:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T12:22:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T12:13:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T12:05:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:format-issue` - 2026-04-03T12:00:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T11:48:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T19:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T11:36:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T11:26:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T11:19:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T11:11:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T11:04:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T11:00:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:52:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T18:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:46:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:format-issue` - 2026-04-03T10:43:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:38:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:26:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:19:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:14:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T16:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:07:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T15:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:58:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T10:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:50:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:43:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:format-issue` - 2026-04-03T09:39:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:34:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:27:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:18:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
### Codebase Research Findings — `add_file_sink` Scope, Schema Pattern, EventBus Wiring (run 7)

_Added by `/ll:refine-issue` — verified against current code:_

- **`add_file_sink` has zero production callers** — `events.py:102` defines the method; only `test_events.py:174` and `test_events.py:188` call it. `self._file_sinks` is **always empty at runtime**. The existing JSONL write path is `PersistentExecutor.append_event()` (`persistence.py`, direct file append), which is completely separate from `EventBus._file_sinks`. **Implication**: `JsonlTransport` is not a migration of existing behavior — it introduces a new transport that reproduces `PersistentExecutor.append_event()` via EventBus. Alternatively, `_file_sinks` / `add_file_sink` can be removed entirely (dead code) and the issue's refactor step skipped. The JSONL log at `.ll/events.jsonl` (FEAT-911) is written by `persistence.py` directly; `JsonlTransport` would be additive, not a refactor.

- **`events.transports` config schema pattern** — No existing `transports`, `sinks`, `webhook`, `otel`, or `socket` keys exist anywhere in `config-schema.json`. The correct schema pattern for `events.transports` is a plain string array matching `extensions` at line 897–900: `{"type": "array", "items": {"type": "string"}}` with no `"enum"` constraint. Runtime code (not schema) should validate transport name values (`"jsonl"`, `"socket"`, `"webhook"`, `"otel"`). This is consistent with all other array properties in the schema (`scan.focus_dirs`, `parallel.worktree_copy_files`, etc.).

- **4 production `EventBus()` construction sites** — `persistence.py:344` (loop executor), `parallel.py:225` (ll-parallel), `sprint/run.py:390` (ll-sprint), `issue_manager.py:735` (issue lifecycle). Only `persistence.py:344` is targeted for `wire_transports()` in the current plan. `parallel.py:225` and `sprint/run.py:390` also call `wire_extensions()` post-construction — if transport streaming is desired for parallel/sprint runs, they will need `wire_transports()` calls as well. `issue_manager.py:735` creates a bare `EventBus()` with no wiring; it is out of scope. Scope decision: initial implementation targets `persistence.py` only (loop runs); parallel/sprint can be added in a follow-on.

- `/ll:refine-issue` - 2026-04-03T09:20:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:13:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:07:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:02:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:55:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T10:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T11:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:50:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:44:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:format-issue` - 2026-04-03T08:40:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/233246d6-aba3-4c73-842f-437f09922574.jsonl`
- `/ll:refine-issue` - 2026-04-03T12:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-04-03T13:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T14:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:07:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:26:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T10:52:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T19:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-04-03T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-04-03T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-04-03T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
