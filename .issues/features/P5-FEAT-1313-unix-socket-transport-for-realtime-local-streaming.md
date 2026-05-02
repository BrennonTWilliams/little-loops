---
discovered_date: 2026-05-01
discovered_by: split-from-FEAT-918
confidence_score: 75
outcome_confidence: 65
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 20
---

# FEAT-1313: UnixSocketTransport for Real-Time Local Streaming

## Summary

Add a `UnixSocketTransport` that streams newline-delimited JSON events over an `AF_UNIX` socket at `.ll/events.sock`, so local consumers (TUIs, log tailers, dev dashboards) get sub-second latency without polling or filesystem watchers.

## Context

Split from the original FEAT-918 on 2026-05-01. FEAT-918 now contains only the `Transport` Protocol foundation, `JsonlTransport`, and the `wire_transports()` registry. This issue plugs in the Unix socket implementation. No external dependencies — uses `socket` and `threading` from stdlib only.

## Current Behavior

ll has no real-time push channel. Local consumers must tail `.ll/events.jsonl` (file watcher poll) or attach as an in-process observer (only works inside the ll process).

## Expected Behavior

- A `UnixSocketTransport(path, max_clients)` that satisfies `Transport` and uses stdlib `socket` only.
- On `__init__`: `unlink(path, missing_ok=True)` then `bind(path)` then `listen()` then start an accept thread (`settimeout(1.0)` so it can poll the shutdown event).
- Each accepted client gets a daemon thread + per-client `Queue`; `send()` enqueues a `\n`-terminated JSON line into every client queue (drop+log if a queue is full at `max_clients` cap; never block the FSM).
- A misbehaving / disconnecting client is removed without affecting others.
- `close()` sets a shutdown event, joins the accept thread, signals each client thread, joins them with timeout, closes the socket, and unlinks the socket file.
- Windows is not supported — the transport raises `RuntimeError` clearly when `wire_transports` runs on a platform without `AF_UNIX`.

## Motivation

- Local TUIs and dev dashboards want sub-second event latency without poll overhead.
- A socket is the simplest cross-language local pub/sub primitive (any tool with a socket client can subscribe — Python, Go, Rust, Node, shell+`nc`).

## Proposed Solution

1. Add `UnixSocketTransport` to `scripts/little_loops/transport.py` using stdlib only.
2. Extend `EventsConfig` with a nested `SocketEventsConfig(path, max_clients)` (default path: `.ll/events.sock`, default max_clients: 8).
3. Register `"socket"` in `wire_transports()`'s name → constructor map; raise `RuntimeError` on platforms without `AF_UNIX`.
4. Extend `config-schema.json` `events` block with a `socket` sub-object.

## API/Interface

```python
class UnixSocketTransport:
    def __init__(self, path: Path, max_clients: int = 8): ...
    def send(self, event: dict[str, Any]) -> None: ...   # enqueue per-client, non-blocking
    def close(self) -> None: ...                          # shutdown event, join, unlink
```

Config:

```json
{
  "events": {
    "transports": ["jsonl", "socket"],
    "socket": {
      "path": ".ll/events.sock",
      "max_clients": 8
    }
  }
}
```

## Integration Map

### Files to Modify

- `scripts/little_loops/transport.py` — add `UnixSocketTransport`; register `"socket"` constructor in `wire_transports()` (with platform guard)
- `scripts/little_loops/config/features.py` — add `SocketEventsConfig` dataclass; extend `EventsConfig` with `socket: SocketEventsConfig` field
- `config-schema.json` — extend `events` block with `socket` sub-object: `path: string (default ".ll/events.sock")`, `max_clients: integer (default 8)`. Close with `additionalProperties: false`

### Similar Patterns

- `scripts/little_loops/parallel/merge_coordinator.py:63-111` — daemon thread + `Queue` + `threading.Event` shutdown sentinel. Specifically: `_queue: Queue` (line 63), `_shutdown_event = threading.Event()` (line 65), `start()` builds the daemon thread (lines 81-93), `shutdown()` sets event then joins with timeout (lines 95-111). Use as the accept-thread template
- `scripts/little_loops/extension.py:35-57` — `@runtime_checkable class LLExtension(Protocol)` is the closest in-repo precedent for a `Transport` Protocol (FEAT-918 will follow this shape)
- `scripts/tests/test_merge_coordinator.py:1380-1395` — threading test harness pattern (queue inspection + bounded-timeout assertion)
- `scripts/tests/test_overlap_detector.py:158-184` — concurrent-thread assertion patterns

### Tests

- `scripts/tests/test_transport.py` — add:
  - `UnixSocketTransport` Protocol satisfaction
  - End-to-end: connect a client socket, emit events through the transport, assert client receives newline-delimited JSON
  - Multi-client: two clients connected simultaneously each receive every event
  - Client disconnect mid-stream: transport remains healthy, other clients unaffected
  - `max_clients` cap: 9th connection enqueue is dropped with a warning
  - `close()` joins all threads within timeout, unlinks socket file
  - Platform skip: `pytest.mark.skipif(not hasattr(socket, "AF_UNIX"))`
- `scripts/tests/test_config.py` — `SocketEventsConfig` defaults and full-tree parse

### Documentation

- `docs/reference/CONFIGURATION.md` — document `events.socket` block and platform support
- `docs/reference/API.md` — `UnixSocketTransport` constructor and the wire format (`\n`-delimited JSON)
- `docs/ARCHITECTURE.md` — Unix socket transport in the multi-transport list, with note on platform support

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis on 2026-05-01:_

- **Hard dependency on FEAT-918 confirmed** — `scripts/little_loops/transport.py` does not exist yet, `EventsConfig` is absent from `scripts/little_loops/config/features.py` (verified — file ends at `SyncConfig`, no `Events*` class), and `config-schema.json` has no top-level `events` block. All three are introduced by FEAT-918. FEAT-1313 must not begin until FEAT-918 lands; otherwise the wire-up site, registry, and config plumbing have nothing to attach to.
- **`EventsConfig` extension contract (per FEAT-918)** — FEAT-918 ships `EventsConfig(transports: list[str])` only. This issue extends it with `socket: SocketEventsConfig` as a sibling field. Mirror the `from_dict` parse style used by `EventsConfig` siblings in `features.py` (e.g., `IssuesConfig.from_dict` at `features.py:139`, `SyncConfig.from_dict` at `features.py:365`) — `socket=SocketEventsConfig.from_dict(data.get("socket", {}))`.
- **`wire_transports()` registration shape (per FEAT-918)** — FEAT-918's `wire_transports(bus, config.events)` walks `config.transports` and calls `bus.add_transport(constructor(...))` for each name in a `name → constructor` map. To register `"socket"`: add an entry that constructs `UnixSocketTransport(Path(config.socket.path), config.socket.max_clients)`. Unknown names already log a warning and skip — no fallback needed.
- **No `AF_UNIX` precedent in the codebase** — `grep -rn "AF_UNIX\|hasattr(socket"` returns zero hits in `scripts/`. UnixSocketTransport introduces the first socket-server code path. Implication: the `pytest.mark.skipif(not hasattr(socket, "AF_UNIX"))` guard is also a new pattern, with no in-repo example to copy. Place the platform guard at the top of `test_transport.py`'s socket tests as a module-level marker, not at each test function, to keep collection clean on Windows CI.
- **Protocol satisfaction template** — `extension.py:35-57` defines `@runtime_checkable class LLExtension(Protocol)` — this is the closest in-repo precedent for the FEAT-918 `Transport` Protocol. `UnixSocketTransport` does not need to inherit from `Transport`; structural typing via `runtime_checkable` `isinstance` is sufficient (see `test_extension.py:19-32` which FEAT-918 references).
- **Daemon-thread shutdown template (verified line numbers)** — Issue originally cited `merge_coordinator.py:57-111`; actual pattern starts at line 63: `_queue: Queue` (line 63), `_thread: threading.Thread | None = None` (line 64), `_shutdown_event = threading.Event()` (line 65), `start()` builds `daemon=True` thread (lines 81-93), `shutdown(wait, timeout)` sets event then joins (lines 95-111). Mirror this exactly for the accept thread; add an inner per-client thread layer (which `MergeCoordinator` does not need — it's single-threaded).
- **Socket-file cleanup hazard** — `unlink(path, missing_ok=True)` on `__init__` AND `close()` is required because crash-without-close leaves a stale socket file that prevents `bind()` on the next run. Idempotent-unlink guards both startup and shutdown. Confirm `close()` is invoked from `EventBus.close_transports()` (FEAT-918 wires this into `run.py:172 finally`, `lifecycle.py finally`, and `orchestrator._cleanup():1248`).
- **`EventBus.add_transport()` is the integration seam** — `UnixSocketTransport` does not need to know about `EventBus`. `wire_transports()` constructs the transport and passes it to `bus.add_transport(...)` (added by FEAT-918 to `events.py`). All event fan-out happens via FEAT-918's per-transport `emit()` loop with exception isolation — `UnixSocketTransport.send()` raising will not affect `JsonlTransport` or future transports.
- **Config schema closure** — `config-schema.json` uses `"additionalProperties": false` on the root and on `extensions` (per FEAT-918 findings). Apply the same closure to the new `events.socket` sub-object so unknown keys fail validation early.

## Use Case

A developer runs `ll-parallel` and opens a TUI in another terminal that connects to `.ll/events.sock`. As loops progress, the TUI shows live state transitions, action durations, and evaluations — no polling, sub-second latency. They can pipe `nc -U .ll/events.sock | jq` into a one-liner for ad-hoc grepping.

## Acceptance Criteria

- [ ] `UnixSocketTransport` implemented and satisfies `isinstance(t, Transport)`
- [ ] No external dependencies (stdlib `socket` + `threading` + `queue` + `json` only)
- [ ] Accept thread uses `settimeout(1.0)` so it polls the shutdown event and exits within ~1s of `close()`
- [ ] Each connected client gets its own daemon thread + bounded `Queue`
- [ ] Client disconnect / write failure removes the client without affecting others or the FSM
- [ ] `send()` is non-blocking — never blocks the FSM thread on slow clients (drop + warn if a queue is full)
- [ ] `close()` unlinks the socket file (`missing_ok=True`) and joins all threads within a 10s timeout
- [ ] On platforms without `AF_UNIX` (Windows), `wire_transports` raises a clear `RuntimeError` directing the user to a different transport
- [ ] Config schema validates `events.socket.path` and `max_clients`
- [ ] All transport tests pass; tests skip cleanly on platforms without `AF_UNIX`

## Implementation Steps

1. Add `SocketEventsConfig` dataclass to `config/features.py` (`path: str = ".ll/events.sock"`, `max_clients: int = 8`); extend `EventsConfig` with `socket` field.
2. Extend `config-schema.json` `events` block with `socket` sub-object.
3. Add `UnixSocketTransport` to `scripts/little_loops/transport.py` (accept thread + per-client queue/thread + shutdown event + socket unlink on close + platform guard).
4. Register `"socket"` in `wire_transports()` constructor map; raise `RuntimeError` if `AF_UNIX` is unavailable.
5. Write tests in `test_transport.py` (Protocol, end-to-end, multi-client, disconnect, max_clients drop, close cleanup, platform skip) and `test_config.py`.
6. Update docs.

## Impact

- **Priority**: P5 — depends on FEAT-918 foundation
- **Effort**: Medium-Large — multi-threaded socket server with shutdown coordination
- **Risk**: Medium — threading shutdown timing and socket-file cleanup are the main hazards
- **Breaking Change**: No (additive, optional, no platform support changes)
- **Depends On**: FEAT-918

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Multi-transport event fan-out |
| reference | docs/reference/CONFIGURATION.md | `events.socket` config block |
| reference | docs/reference/API.md | `UnixSocketTransport` constructor and wire format |

## Labels

`feat`, `observability`, `extension-api`

## Status

**Open** | Created: 2026-05-01 (split from FEAT-918) | Priority: P5

## Session Log
- `/ll:refine-issue` - 2026-05-01T20:59:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1a27e94-952b-4a2d-adc7-4cec048a5642.jsonl`

- Split from FEAT-918 - 2026-05-01
