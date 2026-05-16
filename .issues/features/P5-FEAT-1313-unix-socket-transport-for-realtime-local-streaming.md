---
discovered_date: 2026-05-01
discovered_by: split-from-FEAT-918
confidence_score: 100
outcome_confidence: 84
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 27
score_change_surface: 18
completed_at: 2026-05-02T17:20:11Z
status: done
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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — add `UnixSocketTransport` to `from little_loops.transport import ...` line and `__all__` list (follows existing `JsonlTransport` pattern at lines 33, 61–62)
- `scripts/little_loops/config/__init__.py` — add `SocketEventsConfig` to `from little_loops.config.features import (...)` block and `__all__` (follows existing `EventsConfig` pattern at lines 37, 68)
- `scripts/little_loops/config/core.py` — update `BRConfig.to_dict()` `"events"` section (lines 454–456) to serialize the `socket` sub-object alongside `transports`; current code silently omits `socket`, making the sub-config unreachable via `{{config.events.socket.path}}` template substitution

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
  - New `TestWireTransports` tests: `test_socket_registered_by_name`, `test_socket_uses_socket_path_from_config`, `test_socket_and_jsonl_both_registered`
- `scripts/tests/test_config.py` — `SocketEventsConfig` defaults and full-tree parse

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — extend `test_events_in_schema()` to assert `events.socket` sub-object structure (no current assertion guards the new schema key; add a case analogous to `test_commands_rate_limits_block()` which validates `additionalProperties: false` on a nested object)

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

### Codebase Research Findings — 2026-05-02 update (FEAT-918 landed)

_Added by `/ll:refine-issue --auto` — supersedes stale 2026-05-01 claims:_

- **FEAT-918 / FEAT-1322 / FEAT-1323 have all landed.** `scripts/little_loops/transport.py` exists with `Transport` Protocol (line 30, `@runtime_checkable`), `JsonlTransport` (line 49), `wire_transports()` (line 72), and `_TRANSPORT_REGISTRY` (line 69). `EventsConfig` exists at `scripts/little_loops/config/features.py:374-390`. `events` block exists at `config-schema.json:1036-1048` with `additionalProperties: false`. The 2026-05-01 finding "FEAT-918 not yet landed" is now stale — the dependency in `Impact > Depends On` is **satisfied**; this issue is unblocked.
- **Registration shape is NOT a name→constructor map (correction).** `_TRANSPORT_REGISTRY: dict[str, str] = {"jsonl": "jsonl"}` at `transport.py:69` is a `dict[str, str]` (placeholder), not a `dict[str, Callable]`. Dispatch is a hard-coded `if name == "jsonl":` branch at `transport.py:93-94` that constructs `JsonlTransport(base / "events.jsonl")` and calls `bus.add_transport(...)`. **Adding `"socket"` requires both** (a) adding `"socket": "socket"` to `_TRANSPORT_REGISTRY` AND (b) adding an `elif name == "socket":` branch that constructs `UnixSocketTransport(Path(config.socket.path), config.socket.max_clients)` and calls `bus.add_transport(...)`. Optionally refactor the dispatch into a true callable map — defer unless FEAT-1312/1314 land first and force the issue.
- **Platform guard placement.** Inside the `elif name == "socket":` branch in `wire_transports()`, check `if not hasattr(socket, "AF_UNIX"):` and `raise RuntimeError("UnixSocketTransport requires AF_UNIX; not available on this platform")`. Do not raise from `UnixSocketTransport.__init__` — the wire-up site is the user-facing surface and where the clearer error message belongs. The constructor can also defensively guard, but the wire site is the primary check.
- **`close_transports()` call sites — corrected line numbers.** Prior finding cited `run.py:172`, `orchestrator._cleanup():1248`. Current truth: `cli/loop/run.py:348` (inside `finally:` at line 346, calls `executor.close_transports()` which delegates to `EventBus.close_transports()` via `persistence.py:398-400`); `cli/loop/lifecycle.py:291` (inside `finally:` at line 290); `parallel/orchestrator.py:1314` inside `_cleanup()` (guarded by `if self._event_bus is not None:`). `cli/sprint/run.py` close path goes through the same `ParallelOrchestrator._cleanup()`.
- **`wire_transports()` call sites (CLI entry points).** `cli/loop/run.py:337`, `cli/loop/lifecycle.py:268`, `cli/parallel.py:230` (constructs `EventBus` directly at line 225), `cli/sprint/run.py:405` (multi-issue parallel-wave branch only — single-issue `process_issue_inplace` path does not construct an `EventBus`). **`ll-auto` is the exception**: `cli/auto.py` does not call `wire_transports()` and does not construct an `EventBus` — `AutoManager.run()` is a sequential CLI shell that doesn't surface events. Implication for FEAT-1313: socket transport is unavailable in `ll-auto` runs by design; document this in CONFIGURATION.md if not obvious.
- **Exception isolation contract is in place.** `EventBus.emit()` at `events.py:134-138` wraps each `transport.send(event)` in `try/except Exception` with a warning log — a misbehaving `UnixSocketTransport.send()` cannot break `JsonlTransport` or break the FSM. Same isolation in `close_transports()` at `events.py:109-115`. This means `UnixSocketTransport` does **not** need to swallow exceptions internally — letting them propagate is acceptable.
- **Event payload type confirmed.** `Transport.send()` signature is `def send(self, event: dict[str, Any]) -> None` (`transport.py:40`). The bus passes raw dicts (no `LLEvent` wrapper). `UnixSocketTransport.send()` will `json.dumps(event)` directly — no field projection or schema validation needed.
- **Nested-dataclass parse pattern (canonical examples).** Closest precedents for `EventsConfig.socket: SocketEventsConfig`:
  - `SyncConfig` → `GitHubSyncConfig` at `features.py:356-371` (`github: GitHubSyncConfig = field(default_factory=GitHubSyncConfig)` + `github=GitHubSyncConfig.from_dict(data.get("github", {}))`)
  - `LoopsConfig` → `LoopsGlyphsConfig` at `features.py:308-323` (same shape)
  - `IssuesConfig` → `DuplicateDetectionConfig` at `features.py:138-168` (same shape)
  Use this exact shape — `field(default_factory=SocketEventsConfig)` + delegated `from_dict`.
- **Existing transport test scaffolding to extend.** `scripts/tests/test_transport.py` already has the 4 test classes whose patterns match what FEAT-1313 needs:
  - `TestTransportProtocol` (line 17) — `isinstance(t, Transport)` checks
  - `TestJsonlTransport` (line 48) — single-transport behavioral tests
  - `TestEventBusTransports` (line 76) — multi-transport + isolation tests (`test_transport_exception_isolated` at line 104, `test_close_transports_calls_close_on_each` at line 136)
  - `TestWireTransports` (line 158) — registry + unknown-name + empty-list tests
  Add a new `TestUnixSocketTransport` class with module-level `pytestmark = pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="AF_UNIX not available")` so collection stays clean on Windows CI. Extend `TestWireTransports` with `test_socket_registered_by_name` and `test_socket_raises_on_non_af_unix_platform`.
- **CLI wiring tests to extend.** `test_cli_loop_lifecycle.py:1108` (`TestTransportWiring.test_cmd_resume_wires_transports`), `test_cli_loop_queue.py:133` (`test_cmd_run_wires_transports`), `test_sprint_integration.py:490` (`test_sprint_wires_transports_per_wave`) all use `patch("little_loops.transport.wire_transports")` — no extension needed for FEAT-1313 unless it changes the function signature (which it should not).
- **Sibling transport issues are queued.** `FEAT-1312` (OTel) and `FEAT-1314` (Webhook) will register additional transports in the same registry. If a callable-map refactor of `_TRANSPORT_REGISTRY` is done as part of FEAT-1313, file a follow-up so the next two transports land cleanly — but do not block on it.

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

## Pinned Decisions

_Added 2026-05-02 to remove implementation ambiguity flagged by `/ll:confidence-check`. These are not open questions — implement exactly as stated:_

- **Per-client queue maxsize**: `1024` (hardcoded constant `_CLIENT_QUEUE_MAXSIZE` in `transport.py`, not configurable). Sized to absorb bursts without unbounded memory; revisit only if a real workload pushes the limit.
- **Queue-full policy**: drop **newest** via `Queue.put_nowait` catching `queue.Full`. Do not pop+push to drop oldest — preserving causal order matters more than freshness for log/event consumers.
- **Drop-log rate**: warn on the **first drop per client connection**, then summarize subsequent drops in a counter logged at most once per 5 seconds per client (`logger.warning("UnixSocketTransport: dropped %d events for slow client", count)`). Per-event WARNING would spam under load.
- **`close()` timeout budget**: total ceiling 10s. Split: accept thread join ≤2s (it polls on `settimeout(1.0)`), each client thread join ≤1s. Track remaining budget across joins; if budget exhausted, log at WARNING and continue (do not raise).
- **Socket file permissions**: `chmod 0600` immediately after `bind()`. The events stream may contain issue titles/file paths/branch names — owner-only is the safe default. Document in CONFIGURATION.md that operators wanting a wider audience should explicitly relax permissions out-of-band.
- **Listen backlog**: `socket.listen(max_clients)`. Connections beyond `max_clients` will be rejected at accept time anyway; matching backlog to cap keeps semantics simple.
- **`json.dumps()` failures**: do NOT catch `TypeError` inside `send()`. `EventBus.emit()` already wraps each `transport.send()` in try/except (`events.py:134-138`), so a non-serializable event logs a warning and isolates the failure. Letting it propagate keeps `UnixSocketTransport` simple.
- **`_TRANSPORT_REGISTRY` shape**: do NOT refactor to a callable map. Add `"socket": "socket"` and an `elif name == "socket":` branch in `wire_transports()`. The callable-map refactor is a follow-up if FEAT-1312 / FEAT-1314 force the issue.

## Pre-Implementation Spike

_Added 2026-05-02 to de-risk the highest-complexity factor (threading shutdown lifecycle). Do this before writing production code:_

Write a throwaway script `scripts/tests/spike_unix_socket_shutdown.py` that:
1. Binds an `AF_UNIX` socket at a tmp path.
2. Starts an accept thread (`settimeout(1.0)` + shutdown `Event`) plus per-client daemon thread + bounded queue.
3. Connects 2 client sockets, enqueues a few events through each client thread.
4. Sets the shutdown event, joins all threads with timeouts matching the pinned budget (≤2s accept, ≤1s per client), unlinks the socket.
5. Asserts: all threads exited within budget, socket file removed, no zombie threads via `threading.enumerate()`.

Run under `pytest --timeout=15` (or a plain `python -X dev` invocation with a wall-clock assert). If the spike runs cleanly twice in a row, delete it — its job is to validate the shutdown topology, not to ship. If it hangs or leaves zombie threads, fix the pattern in the spike before porting to `transport.py`.

## Implementation Steps

0. **Run the pre-implementation spike** (see section above). Do not proceed past step 1 until the spike exits cleanly.
1. Add `SocketEventsConfig` dataclass to `config/features.py` (`path: str = ".ll/events.sock"`, `max_clients: int = 8`); extend `EventsConfig` with `socket` field.
2. Extend `config-schema.json` `events` block with `socket` sub-object.
3. Add `UnixSocketTransport` to `scripts/little_loops/transport.py` (accept thread + per-client queue/thread + shutdown event + socket unlink on close + platform guard).
4. Register `"socket"` in `wire_transports()` constructor map; raise `RuntimeError` if `AF_UNIX` is unavailable.
5. Write tests in `test_transport.py` (Protocol, end-to-end, multi-client, disconnect, max_clients drop, close cleanup, platform skip) and `test_config.py`.
6. Update docs. Include an explicit note in `CONFIGURATION.md` that `events.transports: ["socket"]` has no effect under `ll-auto` (which does not construct an `EventBus`); socket transport is available under `ll-loop run/resume`, `ll-parallel`, and `ll-sprint` parallel-wave runs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/__init__.py` — add `UnixSocketTransport` to the `from little_loops.transport import ...` line and `__all__` list (follows the `JsonlTransport` pattern already there)
8. Update `scripts/little_loops/config/__init__.py` — add `SocketEventsConfig` to imports and `__all__` (follows the `EventsConfig` pattern already there)
9. **Write failing test FIRST**, then make it pass: add a `BRConfig.to_dict()` round-trip test in `test_config.py` that constructs a `BRConfig` with a populated `events.socket` sub-config, calls `to_dict()`, and asserts `result["events"]["socket"]["path"]` and `["max_clients"]` are present with the expected values. This guards the silent-data-loss path (`{{config.events.socket.path}}` returning empty). _Then_ update `scripts/little_loops/config/core.py:BRConfig.to_dict()` — extend the `"events"` section (lines 454–456) to serialize `socket` sub-object alongside `transports`.
10. Extend `scripts/tests/test_config_schema.py:test_events_in_schema()` — assert `"socket"` is present in `events_props` and the sub-object has `path` and `max_clients` properties with `additionalProperties: false`

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

**Completed** | Created: 2026-05-01 (split from FEAT-918) | Completed: 2026-05-02 | Priority: P5

## Resolution

Implemented `UnixSocketTransport` in `scripts/little_loops/transport.py`, satisfying the `Transport` Protocol with stdlib-only dependencies (`socket`, `threading`, `queue`, `json`). The transport binds an `AF_UNIX` socket at the configured path (unlinking any stale file first, `chmod 0600` after bind), runs an accept thread polling on `settimeout(1.0)`, and gives each connected client its own daemon thread with a bounded outbound `Queue(maxsize=1024)`. `send()` is non-blocking — a full client queue causes the newest event to be dropped (preserving causal order), with a first-drop warning and a 5-second rate-limited counter for subsequent drops. `close()` enforces a 10-second total budget (≤2s accept join, ≤1s per client join), unlinks the socket file, and never raises on overrun.

Added `SocketEventsConfig(path, max_clients)` to `EventsConfig`, extended `config-schema.json` `events` block with a `socket` sub-object closed via `additionalProperties: false`, registered `"socket"` in `_TRANSPORT_REGISTRY` with an `elif name == "socket":` branch in `wire_transports()` that raises `RuntimeError` on platforms without `AF_UNIX`. Updated `BRConfig.to_dict()` to serialize `events.socket` so `{{config.events.socket.path}}` template substitution resolves correctly. Exposed `SocketEventsConfig` and `UnixSocketTransport` from the package `__init__.py` files.

Tests cover: Protocol satisfaction, init/close socket-file lifecycle (including stale-file unlink), `chmod 0600` permission, end-to-end send/receive over a real client socket, two-client multicast, mid-stream disconnect tolerance, `max_clients` cap rejection, slow-client queue-full drop with warning, `close()` thread-join + unlink within budget, registry wiring, and the `RuntimeError` raised when `AF_UNIX` is unavailable. All AF_UNIX tests use a `short_tmp_path` fixture under `/tmp/ll-...` to stay within the macOS 104-char `sun_path` limit and skip cleanly on Windows. The `BRConfig.to_dict()` round-trip is also explicitly tested per the wiring-pass guard against silent data loss.

Pre-implementation spike validated the threading shutdown topology twice (per the issue's de-risking step) before any production code was written; spike then deleted.

### Files Changed

- `scripts/little_loops/transport.py` — `UnixSocketTransport`, registry update, `_resolve_socket_path()` helper
- `scripts/little_loops/config/features.py` — new `SocketEventsConfig`, extended `EventsConfig`
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict()` serializes `events.socket`
- `scripts/little_loops/__init__.py`, `scripts/little_loops/config/__init__.py` — export the new symbols
- `config-schema.json` — `events.socket` sub-object
- `scripts/tests/test_transport.py` — `TestUnixSocketTransport` class + 4 new wire tests + `short_tmp_path` fixture
- `scripts/tests/test_config.py` — `TestSocketEventsConfig` + extended `TestEventsConfig` + `to_dict()` round-trip
- `scripts/tests/test_config_schema.py` — extended `test_events_in_schema()` to assert socket sub-object
- `docs/reference/CONFIGURATION.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md` — socket transport documented, including `ll-auto` exclusion note

### Verification

- `python -m pytest scripts/tests/test_transport.py scripts/tests/test_config.py scripts/tests/test_config_schema.py` — 190 passed
- `python -m pytest scripts/tests/` — 5567 passed (3 pre-existing failures unrelated to this issue: `test_marketplace_top_level_version_matches_plugin`, `test_marketplace_plugin_entry_version_matches_plugin`, `test_confidence_check_routes_to_check_readiness`; all reproduce on `main` without these changes)
- `ruff check` — clean on all changed files
- `python -m mypy scripts/little_loops/transport.py scripts/little_loops/config/features.py scripts/little_loops/config/core.py` — no issues

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE _(initial)_ → 84/100 → HIGH _(after pinning decisions + spike step on 2026-05-02)_

### Outcome Risk Factors
- **Threading shutdown timing**: The accept thread + per-client thread layer is the primary implementation risk; if `close()` join timeouts are mistuned the process may hang or leak zombie threads. Mirror the `MergeCoordinator` shutdown pattern exactly (`merge_coordinator.py:95-111`) and enforce the 10s join ceiling from the acceptance criteria. _Mitigated 2026-05-02 by pinned `close()` budget split (≤2s accept, ≤1s per client, 10s ceiling) and pre-implementation spike step._
- **`BRConfig.to_dict()` socket serialization (step 9)**: No existing test guards this path. Without it, `{{config.events.socket.path}}` template substitution returns empty even when config is set. _Mitigated 2026-05-02: step 9 now requires writing the failing round-trip test before the implementation change._
- **`ll-auto` exclusion**: `cli/auto.py` does not call `wire_transports()` and has no `EventBus`; socket transport is unavailable in `ll-auto` by design. _Mitigated 2026-05-02: step 6 explicitly requires the CONFIGURATION.md note._

### Pinned Decisions (added 2026-05-02)
See the **Pinned Decisions** section above for the full list. These remove ambiguity around per-client queue maxsize, queue-full policy, drop-log rate, `close()` timeout split, socket file permissions, listen backlog, `json.dumps()` failure handling, and `_TRANSPORT_REGISTRY` dispatch shape — all previously implementer-discretion items.

## Session Log
- `/ll:manage-issue` - 2026-05-02T17:20:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ee4581b-3eff-49c4-b2e2-421a1a703829.jsonl`
- `/ll:ready-issue` - 2026-05-02T17:07:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2482c293-1d07-45a1-adb2-d5da53a231a9.jsonl`
- `/ll:confidence-check` - 2026-05-02T17:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e5721f1-ad32-42d3-b159-8e41135a2c42.jsonl`
- `/ll:wire-issue` - 2026-05-02T16:55:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e5721f1-ad32-42d3-b159-8e41135a2c42.jsonl`
- `/ll:refine-issue` - 2026-05-02T16:48:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48467571-3ea8-4dbd-9b91-f183ae524eb8.jsonl`
- `/ll:ready-issue` - 2026-05-02T16:44:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32aad54d-9610-4b9c-8508-4ec484b15073.jsonl`
- `/ll:format-issue` - 2026-05-02T16:39:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83d74176-84ac-4ea2-9c73-06de95bcdbd2.jsonl`
- `/ll:refine-issue` - 2026-05-01T20:59:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1a27e94-952b-4a2d-adc7-4cec048a5642.jsonl`

- Split from FEAT-918 - 2026-05-01
