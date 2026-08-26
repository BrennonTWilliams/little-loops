---
id: FEAT-3323
type: FEAT
title: 'Live event stream substrate: localhost SSE bridge over the EventBus'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T03:08:21Z'
relates_to:
- FEAT-3321
- FEAT-3304
depends_on:
- BUG-3324
confidence_score: 93
outcome_confidence: 69
score_complexity: 13
score_test_coverage: 16
score_ambiguity: 23
score_change_surface: 17
---

# FEAT-3323: Live event stream substrate: localhost SSE bridge over the EventBus

## Summary

Land the foundation tier for live consumption of `EventBus` events: a
localhost HTTP/SSE endpoint that relays bus events to a browser in real time.

This is the event-stream analogue of FEAT-3304. FEAT-3304 built the
substrate for *snapshot* consumption of `.ll/history.db` (export, redaction,
embedding) and deliberately shipped a minimal surface on top. This issue does
the same for *live* consumption of the event bus: the plumbing, not the UI.

**Scope split (2026-08-26).** The multi-producer socket collision that
originally travelled with this issue is now **BUG-3324**, and this issue
`depends_on` it. That defect degrades today's documented `nc -U` consumer with
no browser involved, it is fixable and testable on its own, and it carried the
bulk of this issue's risk and change surface. FEAT-3323 is now scoped to the
bridge alone: read the producer sockets, serve SSE. See BUG-3324 for the
probe-and-claim fix and the multi-producer path shape this issue consumes.

## Current Behavior

`UnixSocketTransport` (`transport.py:115`) already streams newline-delimited
JSON bus events over an `AF_UNIX` socket at `events.socket.path` (default
`.ll/events.sock`), with per-client daemon threads, bounded outbound queues,
rate-limited drop accounting, a `max_clients` cap (default 32), and
`chmod 0600` on the socket file. A connecting client is seeded with
`state_change` events for every currently running loop before it joins the
live stream (`_make_seed_callback`, `transport.py:586`). It is wired from four
call sites — `cli/loop/run.py:593`, `cli/loop/lifecycle.py:737`,
`cli/parallel.py:322`, `cli/sprint/run.py:801` — whenever `events.transports`
contains `"socket"`.

Two things block building a live view on that:

1. **A browser cannot open an `AF_UNIX` socket.** The documented consumer
   story is `nc -U .ll/events.sock | jq` (`docs/reference/CONFIGURATION.md`),
   which serves TUIs and log tailers and nothing else. This is what FEAT-3323
   fixes.
2. **Every producer binds the same path** and evicts the previous one
   (`transport.py:157`). **Tracked separately as BUG-3324**, which this issue
   depends on; after that fix a second concurrent producer binds a
   pid-suffixed sibling path in the same directory, which is what this issue's
   fan-in reads.

The wire envelope is `{"event": ..., "ts": ..., ...payload}`
(`docs/reference/EVENT-SCHEMA.md` § Wire Format) with no producer or run
identifier, so even a correctly merged multi-producer stream cannot be
demultiplexed by a consumer. Stamping that identifier stays in this issue: it
is a wire-format change serving the merged stream, not part of the binding
fix.

## Expected Behavior

A user runs one command, opens `http://127.0.0.1:<port>/…` in a browser, and
receives bus events as they are emitted, from **every** little-loops process
running in the project — with each event attributable to its producer. Two
concurrent runs both stream; neither steals the other's socket; a client that
connects mid-run is seeded with current state as it is today.

## Motivation

The producer half of a live event stream is already built and tested; what is
missing is the last hop to a consumer anyone can actually use. That is cheap
relative to what it unblocks, and it is not served by any other issue:
`ll-artifact dashboard` is frozen at export time by construction, and
FEAT-3321 polls the database rather than watching the bus.

Left alone, the socket transport stays a feature with one documented consumer
(`nc -U`), and every future live view — loop-fleet monitor, sprint progress,
a TUI — re-derives the same fan-in and bridging work.

## Proposed Solution

Relay, do not re-emit. The bridge is an **out-of-process consumer** of the
existing `UnixSocketTransport` output — not a fifth transport, not a new emit
path, and not something `EventBus` ever holds a reference to. The tested
backpressure and isolation properties on the producer side stay untouched and
there is one serialization format end to end.

That framing settles a property that was previously stated two ways in this
issue: because the bridge is a separate process, a bridge that crashes or stops
reading is indistinguishable, from the producer's side, from an ordinary slow
or disconnected socket client. It is already handled by `_record_drop` /
`_record_rejection` (`transport.py:242-278`). No `events.py` change and no
`EventBus.emit` transport-isolation test are required for this issue.

Two sub-problems, in order:

1. **Fan-in.** BUG-3324 makes each concurrent producer bind its own
   pid-suffixed path in the configured socket's directory. The bridge globs
   that directory, connects to each socket as a client, and rescans
   periodically to pick up producers that start later. Stale files (crashed
   producer, `ECONNREFUSED`) are skipped.
2. **Bridge.** A stdlib `ThreadingHTTPServer` bound to loopback, one SSE
   endpoint, each event relayed as a `data:` frame. Slow clients are dropped
   rather than buffered, mirroring the drop accounting already in
   `_record_drop`.

## Program Design

The multi-producer socket shape is settled in BUG-3324 (probe-and-claim:
lone producer keeps the configured path; a concurrent second producer binds
`events-<pid>.sock` beside it). The design below consumes that.

### Types

- `ProducerId: str` — stable per-process identifier, the producer's pid as
  recovered from its socket filename, stamped onto the relayed envelope
  alongside `event` and `ts`

### Signatures

- `serve_sse_bridge(config: EventsConfig, host: str = "127.0.0.1", port: int = 8766) -> None`
- `_fan_in_producer_sockets(socket_dir: Path, rescan_s: float = 2.0) -> Iterator[dict]`
- `_is_loopback_host(header: str | None) -> bool` — `Host` header guard

### Call Path

`ll-artifact serve` -> `serve_sse_bridge` -> `_fan_in_producer_sockets`
(one reader thread per producer socket, merging into one bounded queue) ->
per-SSE-client bounded queue -> `data:` frame written to the connected browser

### Server mechanics

These have no in-repo precedent (see § Codebase Research Findings), so they are
specified here rather than inherited:

- **`ThreadingHTTPServer`, not `HTTPServer`.** A single SSE response never
  returns; on the single-threaded base class one connected tab would block the
  whole server. Set `daemon_threads = True` so shutdown does not hang on
  attached clients.
- **Cap concurrent SSE clients**, mirroring `events.socket.max_clients`. Each
  client holds a thread for the life of the connection, so an uncapped server
  is a thread-exhaustion surface from one user opening tabs. Over the cap,
  respond `503` rather than accepting and starving.
- **Bounded per-client queue + drop-newest**, exactly mirroring
  `_SocketClient` (`transport.py:207-280`). A tab that stops reading must never
  grow an unbounded buffer in the bridge.
- **Keepalive.** Emit an SSE comment frame (`: ping\n\n`) every ~15s. On
  loopback there is no proxy to defeat, but this is how the bridge notices a
  vanished tab (write raises `EPIPE`) and reclaims its thread and queue.
- **Reconnect semantics.** Send `retry:` once at stream open. Do **not** emit
  `id:` and do not implement `Last-Event-ID` replay — there is no durable
  buffer to replay from, and pretending otherwise would silently lie about
  completeness. Instead, re-run the seed on every connect, so a reconnecting
  client resyncs to current state and resumes live traffic. Events emitted
  during the disconnect gap are lost by design; say so in the docs.

### Security

Binding loopback is necessary but **not sufficient**: any page the user visits
can resolve a hostname it controls to `127.0.0.1` and read the stream
(DNS rebinding). Two cheap controls, both required:

- **Validate the `Host` header** against `{127.0.0.1, localhost, ::1}` plus the
  bound port; return `403` otherwise. Reuse the frozen-set shape from
  `mcp_server/server.py:86` (`_LOOPBACK_HOSTS`).
- **Send no `Access-Control-Allow-Origin`.** `EventSource` is subject to CORS,
  so omitting the header blocks cross-origin reads; adding a permissive one
  would undo the `Host` guard.

### Port

Default to a fixed port (`8766`, adjacent to `ll-mcp`'s `8765`) and print the
full URL on startup, so § Use Case's "open `http://127.0.0.1:<port>/`" is
actionable. Make it config-driven. `port=0` (OS-assigned) is for tests only —
there is no `port=0` precedent in the codebase and a user cannot guess an
OS-assigned port.

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` — `UnixSocketTransport` (`:115`) stamps
  the producer identifier onto each serialized envelope. The shared-path
  collision itself is **BUG-3324**, not this issue; `_resolve_socket_path`
  (`:678`) and `wire_transports` (`:611`) are touched there, not here.
- ~~`scripts/little_loops/events.py`~~ — **not modified.** Producer attribution
  is stamped at the transport, and the bridge is out-of-process, so
  `EventBus.emit` (`:117`) needs no change. See § Proposed Solution.
- `scripts/little_loops/config/features.py` — `SocketEventsConfig` (`:1115`),
  `EventsConfig` (`:1264`); a new gating block for the bridge
- `scripts/little_loops/config-schema.json` — the `events` block is
  `additionalProperties: false`, so it must be extended before any new key is
  accepted
- A new module for the bridge, plus its CLI entry point

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml:74-129` (`[project.scripts]`) — register the new
  entry point following the `ll-<name> = "little_loops.<module>:main_<name>"`
  convention
- `scripts/pyproject.toml:140-198` (`[project.optional-dependencies]`) —
  if the bridge pulls in a dependency, add a justified pin comment next to
  it (per CLAUDE.md's minimize-dependencies rule) and a matching extras
  group, following the `otel = [...]` / `webhooks = [...]` shape
- `scripts/little_loops/cli/__init__.py` — export the bridge's `main_*`
  function so `pyproject.toml` can reference it
- `scripts/little_loops/config/__init__.py` — export any new bridge config
  dataclass and add it to `__all__`

### Dependent Files (Callers/Importers)
- The four `wire_transports` call sites (`cli/loop/run.py:593`,
  `cli/loop/lifecycle.py:737`, `cli/parallel.py:322`, `cli/sprint/run.py:801`)
  and `scripts/little_loops/__init__.py:63,117` — enumerated by **BUG-3324**.
  This issue leaves all of them unchanged: the envelope gains a key, not a
  signature.
- `_make_seed_callback` (`transport.py:586`) and
  `fsm.persistence.list_running_loops` — the mid-run seeding path the SSE
  endpoint must preserve

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py:53,69,75,80,124,127,128` — every
  events sub-config dataclass (`SocketEventsConfig`, `OTelEventsConfig`,
  `WebhookEventsConfig`) is re-exported here and listed in `__all__`; a new
  bridge config dataclass needs the same two-line addition
- `scripts/little_loops/config/core.py:328,451,937-952` — `BRConfig.to_dict()`
  hand-enumerates `events.socket.{path,max_clients}` etc.; this dict is
  load-bearing for the schema-parity guard below, not incidental
- `scripts/tests/test_config_schema.py:1283-1336`
  (`test_to_dict_values_match_schema_defaults`, `test_guard_is_non_vacuous`)
  — BUG-3192 Guard 1: walks `BRConfig().to_dict()` and diffs every leaf
  against `config-schema.json`'s declared default; fails fast if a new
  events sub-block's default isn't mirrored in `core.py`'s `to_dict()`
- `scripts/tests/test_config_schema.py:1346-1411` (`_DATACLASS_SECTION_MAP`)
  — BUG-3192 Guard 2: every `@dataclass` in `config/features.py` must map to
  its `to_dict()` section; a new bridge config dataclass must be added here
  or this test fails
- `scripts/little_loops/cli/__init__.py` — dispatch layer re-exporting each
  `main_*` function (e.g. `main_config`, `main_history`) for
  `pyproject.toml` entry points; a new bridge CLI module needs an analogous
  `main_*` export wired here
- `scripts/tests/test_cli_doctor_install_checks.py:45-51`
  (`test_real_pyproject_all_entry_points_resolve`) — iterates every
  `[project.scripts]` entry and imports its module; automatically covers a
  new bridge entry point, but will fail if the bridge module eagerly
  imports an optional dependency at module scope (see `main_mcp`'s
  lazy-import pattern, `mcp_server/__init__.py:66-93`)
- `docs/reference/HOST_COMPATIBILITY.md:99` — references
  `UnixSocketTransport` as a deferred "sidecar" mitigation for hook
  latency; check this framing still holds once the transport gains a
  bridge consumer

### Similar Patterns
- `UnixSocketTransport`'s per-client bounded queue + daemon thread + drop
  accounting (`transport.py:207-280`) is the model for handling a slow SSE
  client
- `WebhookTransport` (`transport.py:503`) is the existing precedent for a
  transport that speaks HTTP and batches

### Tests
- `scripts/tests/` — the existing transport suite covering socket behavior,
  drop accounting, and `wire_transports` registration is what a
  multi-producer change must keep green

_Wiring pass added by `/ll:wire-issue`, revised by scope split:_
- `::test_socket_registered_by_name` (`:323-335`),
  `::test_socket_uses_socket_path_from_config` (`:338-351`),
  `::test_socket_and_jsonl_both_registered` (`:354-368`),
  `::test_init_unlinks_stale_socket_file`, `::test_close_unlinks_socket_file`
  (`~:411-425`) — all socket-path-shape tests. **Owned by BUG-3324**, whose
  probe-and-claim design keeps every one of them passing unmodified. Not this
  issue's concern.
- `scripts/tests/test_transport.py` slow-client / rejection log assertions
  (`~:556-570`, `~:621`, keyed to `_record_drop`/`_record_rejection`,
  `transport.py:242-278`) — must keep passing if drop/rejection logging is
  touched
- `scripts/tests/test_config.py::TestSocketEventsConfig` (`:2379-2394`),
  `::TestWebhookEventsConfig` (`:2447-2477`) — pattern to follow
  (`test_defaults` + `test_from_dict_with_overrides`) for a new bridge
  config dataclass's test class
- `scripts/tests/test_config_schema.py::test_events_in_schema` (`:752-814`)
  — extend with a `bridge` (or equivalent) sub-block assertion following
  the existing per-block `additionalProperties: false` shape
- ~~`scripts/tests/test_events.py::TestEventBus`~~ — the
  transport-exception-isolation test previously listed here is **dropped**: the
  bridge is out-of-process and is never registered as an `EventBus` transport,
  so there is nothing for `EventBus.emit` to isolate. See § Proposed Solution.
- Two-concurrent-producers-reach-one-consumer at the *socket* layer is
  **BUG-3324's** test. This issue's version asserts the same property one hop
  later: two producer sockets in a directory, one connected *SSE* client,
  events from both arrive with distinct producer identifiers.
- New test needed, no existing precedent: binding a real
  `HTTPServer(("127.0.0.1", 0), Handler)` on a background thread and
  connecting a client via the OS-assigned port — the `flux_stub` fixture in
  `scripts/tests/test_flux_image_generator.py:248-297` (stub server +
  daemon thread + `shutdown()`/`server_close()` teardown) is the closest
  transferable model; `test_feat_3143_mcp_http_transport.py`'s
  `TestClient`-based pattern does NOT transfer (ASGI-only)
- New test needed: `serve_sse_bridge`'s loopback default, modeled on
  `test_run_http_defaults_to_loopback_not_public`
  (`test_feat_3143_mcp_http_transport.py:60-64`, `inspect.signature`
  introspection)
- New test: a request carrying a non-loopback `Host` header (e.g.
  `Host: evil.example.com`) gets `403` — the DNS-rebinding guard. Signature
  introspection is not enough here; this needs a real request against the
  bound server.
- New test: no `Access-Control-Allow-Origin` header appears on the SSE
  response.
- New test: the SSE client cap — attach `max_clients` readers, assert the next
  gets `503` and that the existing readers keep receiving. Model on
  `test_max_clients_cap_rejects_extra_connection` (`test_transport.py:506-535`).
- New test: a client that stops reading is dropped without the bridge's memory
  growing without bound, and without disturbing a second, healthy client.
- New test: a reconnecting SSE client receives the seed again before live
  traffic (the documented no-replay contract).
- New test: the bridge reports clearly when `events.transports` does not
  include `"socket"` / no producer socket exists, rather than serving an empty
  stream as success (§ Considerations).

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — § Wire Format gains the producer field
- `docs/reference/CONFIGURATION.md:1559-1589` — `events.transports`,
  `events.socket`, and the `nc -U` subscription note
- `docs/ARCHITECTURE.md:613-615` — transport fan-out and socket seeding
- `docs/reference/API.md` — `UnixSocketTransport`, `wire_transports`
- `docs/reference/CLI.md` — the new entry point

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md:99` — mentions `UnixSocketTransport`
  as a deferred hook-latency "sidecar" mitigation; verify this framing still
  holds once the transport gains a bridge consumer

### Configuration

Existing keys consumed: `events.transports` (default `[]`),
`events.socket.path` (default `.ll/events.sock`), `events.socket.max_clients`
(default `32`).

New block `events.bridge`, off by default, following the fixed three-part shape
every existing `events.*` sub-block uses (schema object with
`additionalProperties: false` + `<Name>EventsConfig` dataclass with `from_dict`
+ `field(default_factory=...)` member on `EventsConfig`):

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Gates the capability entirely |
| `host` | `"127.0.0.1"` | Loopback only; non-loopback values rejected |
| `port` | `8766` | Fixed so the printed URL is stable; `0` = OS-assigned, tests only |
| `max_clients` | `8` | Concurrent SSE connections; over the cap returns `503` |
| `keepalive_s` | `15` | SSE comment-frame interval |

Note the `_TRANSPORT_REGISTRY` caveat in § Codebase Research Findings does
**not** apply: `events.bridge` gates a server, not a transport, so there is no
registry entry and no `wire_transports` dispatch branch to add. Confirm the
schema-parity guards (`test_config_schema.py:1283-1336`, `:1346-1411`) treat it
as an ordinary section.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- No stdlib-only HTTP server precedent exists in this codebase. The one existing HTTP server is `ll-mcp`'s optional streamable-HTTP transport, built on uvicorn/starlette, not stdlib (`scripts/little_loops/mcp_server/server.py:277` `run_http`). That dependency is deliberately kept out of the base install — `scripts/pyproject.toml:182-184` notes it "pulls 16 mandatory transitive deps including a full HTTP server stack" — consistent with this issue's stdlib-only framing, but there is no prior stdlib-HTTP code in the codebase to pattern-match against; this would be new ground.
- No SSE or `text/event-stream` implementation exists anywhere in product code; `sse-starlette` is only a transitive dependency of the `mcp` extra, unused directly.
- Loopback-binding convention (from `ll-mcp`, the closest analogue): default `host="127.0.0.1"` on the server entry point, asserted by a dedicated test that inspects the function signature default (`scripts/tests/test_feat_3143_mcp_http_transport.py:60-64`), plus a frozen `_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})` gate for non-loopback binds (`server.py:86`, `:109-116`).
- No `port=0` (OS-assigned port) precedent exists anywhere in the codebase; `ll-mcp` uses a fixed default port (`8765`).
- Per-producer/per-process identifier naming is unsettled across the codebase — three existing identifiers disagree on both name and generation strategy: `run_id` is a compact ISO-timestamp string derived from `started_at` (`scripts/little_loops/fsm/persistence.py:611-613`), `session_id` is a free-form TEXT column with no fixed generation mechanism (`scripts/little_loops/session_store/schema.py`, multiple tables), and `entry_id` is a straight `str(uuid.uuid4())` (`scripts/little_loops/cli/loop/run.py:381`). No existing "producer identifier" or PID-based constant was found in `events.py` or `transport.py`.
- New `events.*` config sub-blocks follow a fixed three-part shape, evidenced by every existing sub-block (`socket`, `otel`, `webhook`, `sqlite`): (1) a schema object under `events.<name>` in `config-schema.json` with `additionalProperties: false` (e.g. `webhook` at `config-schema.json:1620-1641`); (2) a matching `<Name>EventsConfig` dataclass in `scripts/little_loops/config/features.py` with a `from_dict` classmethod supplying the same defaults as the schema (e.g. `WebhookEventsConfig` at `features.py:1232-1246`); (3) a `field(default_factory=...)` member on `EventsConfig`, threaded through its own `from_dict` (`features.py:1264-1287`). A new block is inert until its name is also added to `_TRANSPORT_REGISTRY` (`transport.py:602-608`) and a matching dispatch branch in `wire_transports` (`transport.py:632-675`) — registration in the dict alone is not sufficient.
- `ll-mcp` is the only existing `[project.scripts]` entry point that starts a long-running server process; its `main_mcp()` (`scripts/little_loops/mcp_server/__init__.py:66`) lazily imports its server dependency inside the function (not at module scope) so the module still imports on a checkout without the optional extra installed, and dispatches via `anyio.run(...)`. No naming convention has been settled yet even for the sibling FEAT-3321 server entry point this issue may share a process with — that issue records only a provisional name (`.issues/features/P3-FEAT-3321-...md:108`).
- Test precedent for the multi-producer/slow-consumer acceptance criteria already exists in `scripts/tests/test_transport.py`: `test_multi_client_each_receives_every_event` (`:458-479`) and `test_client_disconnect_does_not_affect_other_clients` (`:481-504`) are the direct models for "two producers reach one client" and "second producer does not disconnect an existing client." `test_max_clients_cap_rejects_extra_connection` (`:506-535`) and the drop-accounting/rate-limited-logging tests (`:585`, `:537`) are the models for the slow-consumer-drop acceptance criterion. All of these use a `short_tmp_path` fixture (`:52`) instead of `tmp_path`, because raw `AF_UNIX` socket paths have an OS length ceiling `tmp_path` can exceed. Separately, `scripts/tests/test_feat_3143_mcp_http_transport.py` tests its ASGI app via Starlette's in-process `TestClient` rather than a real socket bind — a pattern that would not transfer to a stdlib HTTP implementation, since `TestClient` drives the ASGI lifespan protocol this issue's server would not have.

## Implementation Steps

0. **Land BUG-3324 first.** The fan-in has nothing to read from until concurrent
   producers stop evicting each other. Do not start here.
1. Add the producer identifier to the emitted envelope (stamped in
   `UnixSocketTransport`, recovered from the pid in the socket filename) and
   document it in `docs/reference/EVENT-SCHEMA.md` § Wire Format. Pick a key
   that cannot collide with a payload field — payloads are splatted at the top
   level of the envelope; grep the event catalog before choosing.
2. Add the `events.bridge` config block (schema + dataclass + `EventsConfig`
   member + `to_dict()` mirror + `_DATACLASS_SECTION_MAP` entry), off by
   default.
3. Build `_fan_in_producer_sockets`: glob the socket directory, one reader
   thread per producer socket merging into one bounded queue, periodic rescan
   for late-starting producers, skip stale sockets on `ECONNREFUSED`.
4. Build the SSE bridge on `ThreadingHTTPServer` per § Program Design —
   loopback bind, `Host` guard, no CORS header, client cap, bounded per-client
   queue with drop-newest, keepalive comment frames, `retry:` with no `id:`.
5. Preserve seeding: a newly connected SSE client gets the running-loop
   `state_change` events before live traffic, on every connect including
   reconnects.
6. Print the full URL on startup; report clearly when no producer socket exists
   rather than serving an empty stream as success.
7. Ship the smallest possible page that renders the stream, to prove it
   end-to-end.
8. Document: `EVENT-SCHEMA.md` (envelope key), `CONFIGURATION.md`
   (`events.bridge`, the redaction decision, the no-replay reconnect contract),
   `CLI.md` (the entry point).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Register the bridge CLI entry point in `scripts/pyproject.toml`
  `[project.scripts]`, export its `main_*` function from
  `scripts/little_loops/cli/__init__.py`, and use `main_mcp`'s lazy-import
  pattern (`mcp_server/__init__.py:66-93`) if it pulls in any optional
  dependency — the entry-point-resolution test
  (`test_cli_doctor_install_checks.py::test_real_pyproject_all_entry_points_resolve`)
  fails on an eager import of a missing extra
- Export any new bridge config dataclass from
  `scripts/little_loops/config/__init__.py` and add it to `__all__`
- Add the new dataclass's `to_dict()` mirror to `BRConfig.to_dict()`
  (`config/core.py:937-952`) and to `_DATACLASS_SECTION_MAP`
  (`test_config_schema.py:1346-1411`) — both guard tests fail otherwise
- ~~Update the socket-path-shape tests~~ — moved to BUG-3324, whose design
  keeps them passing unmodified
- ~~Add a transport-exception-isolation test for `EventBus.emit`~~ — dropped;
  the bridge is out-of-process and is never an `EventBus` transport
- Write the real-`HTTPServer`-on-port-0 harness — no existing precedent to
  extend (see Tests subsection for the closest transferable model), and it is
  the prerequisite for the `Host`-guard, CORS, client-cap, and slow-client
  tests

## Impact

- **Priority**: P3 — a developer-experience capability, not a correctness or
  availability problem. (The correctness half is now BUG-3324.)
- **Effort**: Small-Medium after the split. The bridge is stdlib-only and
  self-contained; the cost is concentrated in building an HTTP/SSE test harness
  from scratch, since nothing in the repo binds a real stdlib server.
- **Risk**: Low-Medium after the split. This issue no longer changes the socket
  binding path; it adds one envelope key and a new out-of-process server that
  nothing else depends on. A bridge failure cannot reach a run — the producer
  sees only an ordinary disconnected socket client.
- **Breaking Change**: Additive envelope key only. Confirm no event payload
  already uses the chosen key name, since payloads are splatted at the top
  level of the envelope. Socket path shape is BUG-3324's concern.

## Use Case

A user kicks off `ll-sprint` and, in another terminal, `ll-loop run`. They want
one browser tab showing FSM state transitions and issue lifecycle events from
both as they happen — the thing `ll-artifact dashboard` structurally cannot do,
because its snapshot is frozen at export time.

## Scope

### In scope

- A localhost HTTP server exposing bus events as **SSE** (`text/event-stream`),
  bound to loopback only. SSE over WebSocket: it is one-way, reconnects on its
  own, and needs no client library.
- Consuming the existing `UnixSocketTransport` stream rather than adding a
  fifth transport type or a new emit path — the producer side already exists
  and is tested.
- **Fan-in over the producer socket directory**, so the consumer-visible result
  is one merged stream including producers that start after the bridge does.
  (Making concurrent producers stop evicting each other is **BUG-3324**, a
  dependency, not part of this scope.)
- **Producer attribution in the envelope** so a merged stream is
  demultiplexable — the minimum being a stable per-process/per-run identifier
  added alongside `event` and `ts`, documented in
  `docs/reference/EVENT-SCHEMA.md`.
- Preserving current-state seeding for a client that connects mid-run.
- A `Host`-header guard against DNS rebinding, and no CORS header — the
  compensating controls that make the no-redaction decision defensible.

### Out of scope

- Any UI beyond the minimum needed to prove the stream works. Charts,
  layout, and the loop-fleet view are downstream consumers.
- Live-querying `.ll/history.db` — that is FEAT-3321, which is row-shaped and
  polled. See § Relationship to FEAT-3321.
- Any write path or command execution from the browser.
- Remote or multi-user access. Loopback only.
- Replacing or deprecating `UnixSocketTransport`; TUI consumers keep working.
- **The multi-producer socket binding fix — BUG-3324.**
- Replay of events missed while an SSE client was disconnected. There is no
  durable buffer; reconnect re-seeds current state and resumes live.

## Relationship to FEAT-3321

These are adjacent and must not be merged carelessly:

- **FEAT-3321** serves *row* questions over `.ll/history.db` ("what has
  happened, aggregated") by polling a read-only query endpoint.
- **This issue** serves *event* questions off the bus ("what is happening
  right now") by pushing an event as it is emitted, with sub-second latency
  and no database round trip.

They share a localhost server process and a config gate. **Resolved
2026-08-26**: since FEAT-3321 is still `open` and unimplemented, this issue
claims `ll-artifact serve` and defines the server; FEAT-3321 mounts its
read-only query route on the same server rather than standing up a second
listener. Defining the server here rather than leaving it to whichever lands
first is what makes that reuse actually happen. Still not a blocking
dependency in either direction — if FEAT-3321 lands first it owns the server
instead, and this issue adds the `/events` route.

## API/Interface

- **`ll-artifact serve`** — claimed here (see § Relationship to FEAT-3321),
  serving the SSE stream at a dedicated route. Registered in
  `[project.scripts]`, `main_*` exported from `cli/__init__.py`, using
  `main_mcp`'s lazy-import pattern (`mcp_server/__init__.py:66-93`) if it ever
  pulls an optional dependency.
- **`events.bridge`** config block gating the capability, sibling to
  `events.socket` in `config-schema.json` (which is
  `additionalProperties: false`, so the schema must be extended before any new
  key is accepted). Keys and defaults in § Integration Map → Configuration.

## Considerations

- **`events.transports` is `[]` by default.** Nothing streams unless the
  project opts in. The bridge must say so plainly when no producer is
  configured, rather than presenting an empty stream as a quiet success.
- **Backpressure is already solved on the producer side** and the same
  discipline has to hold at the HTTP hop: a browser tab that stops reading
  must not grow an unbounded buffer in the bridge or stall the FSM thread.
  Because the bridge is out-of-process, a bridge that dies or wedges appears to
  the producer as an ordinary slow/disconnected socket client and is handled by
  the existing `_record_drop` / `_record_rejection` paths
  (`transport.py:242-278`) — no new isolation machinery, and nothing for
  `EventBus.emit` to catch.
- **POSIX only.** `wire_transports` raises `RuntimeError` for `"socket"`
  where `AF_UNIX` is unavailable (`transport.py:646-651`). The bridge inherits
  that constraint; it should fail with the same clarity rather than a
  connection error.
- **Not `ll-logs`/`ll-session`.** Those read persisted history. This is the
  live bus.

## Resolved Decisions

_Settled 2026-08-26 during pre-implementation review. Previously § Open
Questions._

- **Redaction: none on the live path.** ENH-075's column allowlist is applied
  at export time in `cli/artifact/dashboard.py`; there is no equivalent on the
  bus and this issue does not add one. Rationale: the stream is the user's own
  project data, the listener is loopback-only, the `Host` guard blocks DNS
  rebinding, no CORS header is sent, and the whole capability is doubly
  opt-in (`events.transports` is `[]` by default *and* `events.bridge.enabled`
  is `false`). **Revisit trigger**, to be recorded alongside the decision in
  `CONFIGURATION.md`: any change that makes the endpoint reachable off-host, or
  any multi-user access.
- **Multi-producer shape: probe-and-claim**, specified in BUG-3324. A lone
  producer keeps the configured path (so `nc -U .ll/events.sock` is unaffected
  and no migration doc is needed); a concurrent producer binds
  `events-<pid>.sock` beside it. Chosen over a broker (no daemon lifecycle) and
  over unconditional per-producer paths (which would break the documented
  consumer and five existing tests).
- **Producer attribution is additive, not breaking.** The envelope is
  `{"event", "ts", ...payload}` and the named external consumer (loop-viz, per
  `EVENT-SCHEMA.md`) reads by key. One caveat to check at implementation time:
  payloads are splatted at the *top level*, so the new key must not collide
  with any existing payload field — grep the event catalog before settling on
  `producer_id` (or similar).

## Open Questions

- None blocking. Remaining choices (exact envelope key name, SSE route path)
  are local to implementation.

## Acceptance Criteria

- [ ] A browser page on loopback receives bus events over SSE as they are
      emitted by a running loop, with no polling and no page reload.
- [ ] Two concurrent producers (e.g. `ll-loop run` and `ll-sprint run`) both
      stream to a single connected **SSE** client, each event carrying its own
      producer's identifier — asserted by a test over two producer sockets in
      one directory. (The socket-layer half of this property is BUG-3324's AC.)
- [ ] A producer that starts *after* the bridge is already serving is picked up
      by the directory rescan and its events reach an attached client.
- [ ] Every relayed event carries a stable producer identifier that does not
      collide with any existing payload field, and the envelope addition is
      documented in `docs/reference/EVENT-SCHEMA.md`.
- [ ] An SSE client connecting while a loop is mid-run receives the
      current-state seed events before live traffic, matching today's
      `UnixSocketTransport` behavior — on every connect, including reconnects.
- [ ] A consumer that stops reading is dropped without unbounded buffering in
      the bridge and without stalling or failing the producing run — asserted
      by a test, mirroring the existing drop-accounting discipline.
- [ ] The listener binds loopback only; a test asserts it is not reachable on a
      non-loopback interface.
- [ ] A request with a non-loopback `Host` header is rejected with `403`, and
      no `Access-Control-Allow-Origin` header is sent — both asserted by tests
      against a really-bound server.
- [ ] Concurrent SSE clients are capped; the connection over the cap gets `503`
      and existing clients are undisturbed.
- [ ] The server starts on a fixed default port and prints the full URL; with
      no producer socket present it says so plainly rather than serving an
      empty stream as success.
- [ ] The capability is gated by `events.bridge` in project config, the new
      block is added to `config-schema.json` (which is
      `additionalProperties: false`) with a `to_dict()` mirror and a
      `_DATACLASS_SECTION_MAP` entry so both BUG-3192 schema guards pass, and
      it is off by default.
- [ ] The redaction decision, its revisit trigger, and the no-replay reconnect
      contract are recorded in `docs/reference/CONFIGURATION.md`.

## Related Key Documentation

- `docs/reference/EVENT-SCHEMA.md` — wire format and event catalog
- `docs/reference/CONFIGURATION.md` — `events.transports`, `events.socket`
- `docs/ARCHITECTURE.md` — transport fan-out and socket seeding
- `docs/reference/API.md` — `UnixSocketTransport`, `wire_transports`

## Confidence Check Notes

_Re-run by `/ll:confidence-check` on 2026-08-26, after the BUG-3324 scope split._

**Readiness Score**: 93/100 -> PROCEED
**Outcome Confidence**: 69/100 -> MODERATE

(Supersedes the 2026-08-25 92/58 assessment below, which predated the split.)

### Outcome Risk Factors
- **Dominant, carried forward**: no in-repo precedent for a stdlib HTTP/SSE
  server or for a really-bound-server test harness. Both must be built from
  scratch; expect iteration there rather than in the relay logic.
- Breadth remains wide even after the split: new module + CLI entry point +
  config dataclass + `config-schema.json` block + `to_dict()` mirror +
  `_DATACLASS_SECTION_MAP` entry + `pyproject.toml` script + two `__init__.py`
  re-exports + docs. Each site is mechanical, but the BUG-3192 schema guards
  fail loudly if any config leaf is missed.
- The envelope gains a top-level key that external consumers (loop-viz, per
  `EVENT-SCHEMA.md`) read positionally by name; the collision grep against the
  event catalog is a real pre-work step, not a formality.
- `ll-artifact serve` does not exist yet (`format-check` reports it as
  `stale_cli_flag`). This is expected — the issue creates it — but it means the
  subcommand name is unclaimed and could drift if FEAT-3321 lands first.

### Notes
- Dependency `BUG-3324` is `open`. It is `depends_on`, not `blocked_by`, so no
  hard gate fires, but Implementation Step 0 correctly orders it first.
- Risk factors 1 and 3 from the 2026-08-25 assessment are retired: the
  fan-in-vs-broker decision is settled (§ Resolved Decisions) and the
  transport-path change moved to BUG-3324.

### Superseded assessment (2026-08-25)

_Added by `/ll:confidence-check` on 2026-08-25_

**Readiness Score**: 92/100 → PROCEED
**Outcome Confidence**: 58/100 → LOW

### Outcome Risk Factors
- Unresolved load-bearing design decision: per-producer-sockets-fan-in vs. broker must be settled before any HTTP code is written — deep per-site complexity in whichever shape is chosen.
- No in-repo precedent for a stdlib HTTP/SSE server or a real-`HTTPServer`-on-port-0 test harness — expect iteration building both from scratch.
- Broad enumeration across 4 call sites plus public exports and 2 schema-guard tests on a live, tested transport path — regression risk if the fan-in change alters the existing socket-path shape.

_Superseded 2026-08-26 by the scope split — the scores above predate it._
Risk factors 1 and 3 no longer apply to this issue: the design decision is
settled (§ Resolved Decisions) and the transport-path change moved to
BUG-3324. Risk factor 2 stands and is now the dominant one. Re-run
`/ll:confidence-check` on both issues before implementation to get current
scores.

## Revision History

- **2026-08-26 — pre-implementation review.** Split the multi-producer socket
  collision out to **BUG-3324** and added `depends_on`. Resolved all three open
  questions (no redaction + revisit trigger; probe-and-claim; additive envelope
  key with a collision caveat). Removed the `events.py` / `EventBus.emit`
  transport-isolation work as inapplicable to an out-of-process bridge — it
  contradicted § Proposed Solution. Specified the server mechanics that had no
  in-repo precedent to inherit: `ThreadingHTTPServer`, client cap, bounded
  per-client queues, keepalive frames, and no-replay reconnect. Added a
  `Host`-header DNS-rebinding guard and a no-CORS rule. Replaced the
  unguessable `port=0` default with a fixed `8766` plus a printed URL. Defined
  the `events.bridge` config block. Claimed `ll-artifact serve` so the
  FEAT-3321 server-sharing note is actionable.

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-26T15:05:26 - `527f3505-6fa7-4a25-937c-558cd9f06642.jsonl`
- `/ll:confidence-check` - 2026-08-26T03:42:55 - `2361c366-3751-4d40-b3d8-0d881c047601.jsonl`
- `/ll:wire-issue` - 2026-08-26T03:35:40 - `ad3eb4f0-b35e-4777-be61-e91603e9fcf0.jsonl`
- `/ll:refine-issue` - 2026-08-26T03:22:33 - `39df27ac-4529-446c-ad77-2dd45a63f9c4.jsonl`
- `/ll:format-issue` - 2026-08-26T03:13:36 - `07e3e6d6-b489-4e89-8655-3bde4b1da576.jsonl`
- `/ll:capture-issue` - 2026-08-26T03:09:09 - `eadc481c-e910-429b-9281-ccfbd253d4a9.jsonl`
