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
---

# FEAT-3323: Live event stream substrate: localhost SSE bridge over the EventBus

## Summary

Land the foundation tier for live consumption of `EventBus` events: a
localhost HTTP/SSE endpoint that relays bus events to a browser in real time,
plus the multi-producer fix that makes such a stream trustworthy when more
than one little-loops process is running.

This is the event-stream analogue of FEAT-3304. FEAT-3304 built the
substrate for *snapshot* consumption of `.ll/history.db` (export, redaction,
embedding) and deliberately shipped a minimal surface on top. This issue does
the same for *live* consumption of the event bus: the plumbing, not the UI.

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
   which serves TUIs and log tailers and nothing else.
2. **Every producer binds the same path.** All four call sites resolve
   `events.socket.path` through `_resolve_socket_path` to one socket, and the
   constructor unlinks any stale file before binding
   (`transport.py:157`). A second concurrent run therefore takes the socket
   away from the first, whose already-connected clients are left attached to
   an unlinked inode receiving only that dead producer's events.

The wire envelope is `{"event": ..., "ts": ..., ...payload}`
(`docs/reference/EVENT-SCHEMA.md` § Wire Format) with no producer or run
identifier, so even a correctly merged multi-producer stream cannot be
demultiplexed by a consumer.

## Expected Behavior

A user runs one command, opens `http://127.0.0.1:<port>/…` in a browser, and
receives bus events as they are emitted, from **every** little-loops process
running in the project — with each event attributable to its producer. Two
concurrent runs both stream; neither steals the other's socket; a client that
connects mid-run is seeded with current state as it is today.

## Motivation

The producer half of a live event stream is already built and tested; what is
missing is the last hop to a consumer anyone can actually use, plus a
correctness bug that makes the stream untrustworthy the moment two runs
overlap. Both are cheap relative to what they unblock, and neither is served
by any other issue: `ll-artifact dashboard` is frozen at export time by
construction, and FEAT-3321 polls the database rather than watching the bus.

Left alone, the socket transport stays a feature with one documented consumer
(`nc -U`), and every future live view — loop-fleet monitor, sprint progress,
a TUI — re-derives the same fan-in and bridging work.

## Proposed Solution

Relay, do not re-emit. The bridge is a consumer of the existing
`UnixSocketTransport` output, not a fifth transport and not a new emit path,
so the tested backpressure and isolation properties on the producer side stay
untouched and there is one serialization format end to end.

Two sub-problems, in order:

1. **Fan-in.** Producers must stop competing for one socket path. Either give
   each producer its own path under a directory the bridge watches, or stand up
   a broker the producers connect to. The first has no daemon lifecycle to
   manage and degrades to today's behavior with a single producer; the second
   gives one stable endpoint and survives producer restarts. This is the
   load-bearing decision and should be settled before any HTTP code exists.
2. **Bridge.** A stdlib HTTP server bound to loopback, one SSE endpoint, each
   event relayed as a `data:` frame. Slow clients are dropped rather than
   buffered, mirroring the drop accounting already in `_record_drop`.

## Program Design

The multi-producer shape (per-producer sockets + fan-in, vs. a broker) is an
open design decision (see § Open Questions); the signatures below assume the
fan-in variant since it requires no new daemon lifecycle, and should be
revised in place once that decision is settled.

### Types

- `ProducerId: str` — stable per-process/per-run identifier stamped onto the
  relayed envelope alongside `event` and `ts`

### Signatures

- `serve_sse_bridge(config: EventsConfig, host: str = "127.0.0.1", port: int = 0) -> None`
- `_fan_in_producer_sockets(socket_dir: Path) -> Iterator[dict]`

### Call Path

new bridge entry point -> `serve_sse_bridge` -> `_fan_in_producer_sockets` ->
`UnixSocketTransport` (per-producer socket read, `transport.py:115`) -> SSE
`data:` frame written to the connected browser client

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` — `UnixSocketTransport`
  (`:115`), `_resolve_socket_path` (`:678`), and `wire_transports` (`:611`)
  are where the shared-path collision is fixed and producer identity is
  attached
- `scripts/little_loops/events.py` — `EventBus.emit` (`:117`) if producer
  attribution is stamped at emit time rather than at the transport
- `scripts/little_loops/config/features.py` — `SocketEventsConfig` (`:1115`),
  `EventsConfig` (`:1264`); a new gating block for the bridge
- `scripts/little_loops/config-schema.json` — the `events` block is
  `additionalProperties: false`, so it must be extended before any new key is
  accepted
- A new module for the bridge, plus its CLI entry point

### Dependent Files (Callers/Importers)
- The four `wire_transports` call sites: `cli/loop/run.py:593`,
  `cli/loop/lifecycle.py:737`, `cli/parallel.py:322`, `cli/sprint/run.py:801`
- `scripts/little_loops/__init__.py:63,117` — `wire_transports` is a public
  export
- `_make_seed_callback` (`transport.py:586`) and
  `fsm.persistence.list_running_loops` — the mid-run seeding path the SSE
  endpoint must preserve

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

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — § Wire Format gains the producer field
- `docs/reference/CONFIGURATION.md:1559-1589` — `events.transports`,
  `events.socket`, and the `nc -U` subscription note
- `docs/ARCHITECTURE.md:613-615` — transport fan-out and socket seeding
- `docs/reference/API.md` — `UnixSocketTransport`, `wire_transports`
- `docs/reference/CLI.md` — the new entry point

### Configuration
- `events.transports` (default `[]`), `events.socket.path`
  (default `.ll/events.sock`), `events.socket.max_clients` (default `32`)

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

1. Decide and implement the multi-producer shape (per-producer socket paths +
   fan-in, or a broker). This is the load-bearing design decision and should be
   settled before any HTTP code is written.
2. Add the producer identifier to the emitted envelope and document it in
   `docs/reference/EVENT-SCHEMA.md` § Wire Format.
3. Build the SSE bridge: subscribe to the merged stream, relay each event as an
   SSE `data:` frame, bind loopback only, drop slow clients rather than
   buffering without bound (mirroring `_record_drop`'s existing discipline at
   `transport.py:237`).
4. Preserve seeding: a newly connected SSE client gets the running-loop
   `state_change` events before live traffic.
5. Ship the smallest possible page that renders the stream, to prove it
   end-to-end.
6. Add the config gate and document it.

## Impact

- **Priority**: P3 — a developer-experience capability, not a correctness or
  availability problem. The multi-producer collision inside it is a real
  defect, but it only bites projects that have opted into
  `events.transports: ["socket"]`, which is empty by default.
- **Effort**: Medium — the bridge itself is small and stdlib-only; the
  multi-producer fan-in touches a tested transport used from four call sites
  and carries the bulk of the work and the risk.
- **Risk**: Medium — changes a live path that runs inside every FSM loop.
  Mitigated by `EventBus.emit` already isolating transport exceptions
  (`events.py:134-138`), so a defect degrades the stream rather than failing a
  run. That property must be preserved and asserted.
- **Breaking Change**: Possibly, for external socket consumers. An additive
  envelope key should be safe, but changing the socket path shape would not be
  — hence the acceptance criterion requiring existing `nc -U` consumers to keep
  working or the migration to be documented.

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
- **Multi-producer safety**: concurrent producers must not evict each other.
  Whatever shape this takes (per-producer socket paths under a directory that
  the bridge watches and fans in, or a single long-lived broker the producers
  connect to), the consumer-visible result is one merged stream.
- **Producer attribution in the envelope** so a merged stream is
  demultiplexable — the minimum being a stable per-process/per-run identifier
  added alongside `event` and `ts`, documented in
  `docs/reference/EVENT-SCHEMA.md`.
- Preserving current-state seeding for a client that connects mid-run.
- A redaction decision for the live path, stated explicitly (see Open
  Questions).

### Out of scope

- Any UI beyond the minimum needed to prove the stream works. Charts,
  layout, and the loop-fleet view are downstream consumers.
- Live-querying `.ll/history.db` — that is FEAT-3321, which is row-shaped and
  polled. See § Relationship to FEAT-3321.
- Any write path or command execution from the browser.
- Remote or multi-user access. Loopback only.
- Replacing or deprecating `UnixSocketTransport`; TUI consumers keep working.

## Relationship to FEAT-3321

These are adjacent and must not be merged carelessly:

- **FEAT-3321** serves *row* questions over `.ll/history.db` ("what has
  happened, aggregated") by polling a read-only query endpoint.
- **This issue** serves *event* questions off the bus ("what is happening
  right now") by pushing an event as it is emitted, with sub-second latency
  and no database round trip.

They plausibly share a localhost server process and a config gate. Whoever
implements the second one should reuse the first one's server rather than
standing up a second listener. That reuse is a sequencing note, not a
dependency: neither blocks the other.

## API/Interface

- A new entry point or subcommand (working name unresolved — `ll-artifact
  serve` is FEAT-3321's provisional name and a shared server would make it the
  natural home). Naming is a decision for whoever picks this up.
- A config block gating the capability, sibling to `events.socket` in
  `config-schema.json` (which is `additionalProperties: false`, so the schema
  must be extended before any new key is accepted).

## Considerations

- **`events.transports` is `[]` by default.** Nothing streams unless the
  project opts in. The bridge must say so plainly when no producer is
  configured, rather than presenting an empty stream as a quiet success.
- **Backpressure is already solved on the producer side** and the same
  discipline has to hold at the HTTP hop: a browser tab that stops reading
  must not grow an unbounded buffer in the bridge or stall the FSM thread.
  `EventBus.emit` isolates transport exceptions (`events.py:134-138`), so a
  failing bridge cannot abort a run — that property must survive.
- **POSIX only.** `wire_transports` raises `RuntimeError` for `"socket"`
  where `AF_UNIX` is unavailable (`transport.py:646-651`). The bridge inherits
  that constraint; it should fail with the same clarity rather than a
  connection error.
- **Not `ll-logs`/`ll-session`.** Those read persisted history. This is the
  live bus.

## Open Questions

- **Redaction.** ENH-075's column allowlist is applied at export time in
  `cli/artifact/dashboard.py`, and there is no equivalent on the bus. A
  loopback-only stream of a user's own project is arguably fine unredacted —
  but that needs to be a stated decision with a rationale, not an omission,
  and it should be revisited the moment anything makes the endpoint reachable
  off-host.
- **Multi-producer shape.** Per-producer sockets + fan-in is simpler and has
  no daemon lifecycle; a broker gives one stable endpoint and survives
  producer restarts. Pick one with the reasoning recorded.
- **Whether producer attribution is a breaking envelope change** for existing
  consumers (`docs/reference/EVENT-SCHEMA.md` names loop-viz as an external
  consumer). Additive keys should be safe; confirm before landing.

## Acceptance Criteria

- [ ] A browser page on loopback receives bus events over SSE as they are
      emitted by a running loop, with no polling and no page reload.
- [ ] Two concurrent producers (e.g. `ll-loop run` and `ll-sprint run`) both
      stream to a single connected consumer; a test starts two producers and
      asserts events from both reach one client, and that the second producer
      starting does not disconnect a client already attached to the first.
- [ ] Every relayed event carries a stable producer identifier, and the
      envelope addition is documented in `docs/reference/EVENT-SCHEMA.md`.
- [ ] An SSE client connecting while a loop is mid-run receives the
      current-state seed events before live traffic, matching today's
      `UnixSocketTransport` behavior.
- [ ] A consumer that stops reading is dropped without unbounded buffering in
      the bridge and without stalling or failing the producing run — asserted
      by a test, mirroring the existing drop-accounting discipline.
- [ ] The listener binds loopback only; a test asserts it is not reachable on a
      non-loopback interface.
- [ ] The capability is gated by project config, the new block is added to
      `config-schema.json` (which is `additionalProperties: false`), and it is
      off by default.
- [ ] Existing `AF_UNIX` consumers (`nc -U .ll/events.sock`) still work, or the
      migration is documented if the multi-producer fix changes the path.
- [ ] The redaction decision for the live path is recorded in the issue and in
      `docs/reference/CONFIGURATION.md`.

## Related Key Documentation

- `docs/reference/EVENT-SCHEMA.md` — wire format and event catalog
- `docs/reference/CONFIGURATION.md` — `events.transports`, `events.socket`
- `docs/ARCHITECTURE.md` — transport fan-out and socket seeding
- `docs/reference/API.md` — `UnixSocketTransport`, `wire_transports`

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-26T03:22:33 - `39df27ac-4529-446c-ad77-2dd45a63f9c4.jsonl`
- `/ll:format-issue` - 2026-08-26T03:13:36 - `07e3e6d6-b489-4e89-8655-3bde4b1da576.jsonl`
- `/ll:capture-issue` - 2026-08-26T03:09:09 - `eadc481c-e910-429b-9281-ccfbd253d4a9.jsonl`
