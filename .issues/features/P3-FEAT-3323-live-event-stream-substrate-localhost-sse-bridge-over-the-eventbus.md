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
- ENH-3346
- ENH-3351
- BUG-3324
- FEAT-1930
depends_on: []
learning_tests_required:
- http.server
confidence_score: 90
outcome_confidence: 58
score_complexity: 5
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
reconcile_attempted: true
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
originally travelled with this issue became **BUG-3324**, now `done`
(2026-08-28). That fix gives concurrent producers pid-suffixed sibling
sockets in one directory, which is what this issue's fan-in reads. FEAT-3323
is scoped to the bridge alone: read the producer sockets, serve SSE.

**Precedent (ENH-3351, `done`, commit `94a676582`).** `ll-loop run --serve`
added `LocalBridgeTransport` (`scripts/little_loops/transport.py:567`), a
loopback-only stdlib `ThreadingHTTPServer` SSE bridge with a per-request
`Host` guard, a per-start token prefix, bounded per-client queues, and a real
bound-server test harness (`scripts/tests/test_transport.py::TestLocalBridgeTransport`,
`:1019` onward). This issue reuses those pieces. It remains distinct from
ENH-3351: that bridge is in-process and single-producer per run; this one is
a separate process fanning in every producer socket in the project.

## Current Behavior

`UnixSocketTransport` (`transport.py:133`) streams newline-delimited JSON bus
events over an `AF_UNIX` socket at `events.socket.path` (default
`.ll/events.sock`), with per-client daemon threads, bounded outbound queues
(`_CLIENT_QUEUE_MAXSIZE = 1024`, `:56`), rate-limited drop accounting
(`_record_drop` `:314`, `_record_rejection` `:335`), a `max_clients` cap
(default 32), and `chmod 0600` on the socket file. A connecting client is
seeded with one `state_change` frame per state file in `.loops/.running/`
before it joins the live stream (`_make_seed_callback`, `:1110`). It is wired
from four call sites (`cli/loop/run.py:616-619`, `cli/loop/lifecycle.py:741`,
`cli/parallel.py:322`, `cli/sprint/run.py:801`) whenever `events.transports`
contains `"socket"`.

Since BUG-3324, a lone producer keeps the configured path and a concurrent
second producer binds `{stem}-{pid}{suffix}` beside it
(`_claim_socket_path`, `:818`; `_probe_socket_path`, `:788`).

What still blocks a live browser view:

1. **A browser cannot open an `AF_UNIX` socket.** The documented consumer
   story is `nc -U .ll/events.sock | jq` (`docs/reference/CONFIGURATION.md`),
   which serves TUIs and log tailers and nothing else.
2. **No consumer-side socket reader exists in the package.** A grep for
   `AF_UNIX` in `scripts/little_loops/` hits only `transport.py` (the
   producer) and `config-schema.json`. The reader half is new code.
3. **The envelope has no per-producer identifier.** It is a flat dict keyed
   on `event`, `ts`, `run_id`, `loop`, and payload fields
   (`docs/reference/EVENT-SCHEMA.md` § Wire Format), so a merged
   multi-producer stream cannot be demultiplexed.
4. **`ll-loop run --serve` is per-run and in-process.** `LocalBridgeTransport`
   is constructed directly in `cli/loop/run.py:585-598` from plain argparse
   flags, attached with `executor.event_bus.add_transport(bridge)` (`:628`),
   and is never in `_TRANSPORT_REGISTRY` (`transport.py:1126`) or dispatched
   by `wire_transports()` (`:1135`). It cannot see other processes.

## Expected Behavior

A user runs one command, opens the printed `http://127.0.0.1:<port>/<token>/`
URL in a browser, and receives bus events as they are emitted, from **every**
little-loops process running in the project, with each event attributable to
its producer. Two concurrent runs both stream; neither steals the other's
socket; a client that connects mid-run is seeded with current state as a
socket client is today.

## Motivation

The producer half of a live event stream is already built and tested; what is
missing is the last hop to a consumer anyone can actually use. That is cheap
relative to what it unblocks, and it is not served by any other issue:
`ll-artifact dashboard` is frozen at export time by construction,
`ll-loop run --serve` sees one run, and FEAT-3321 polls the database rather
than watching the bus.

Left alone, the socket transport stays a feature with one documented consumer
(`nc -U`), and every future live view (loop-fleet monitor, sprint progress, a
TUI) re-derives the same fan-in and bridging work.

## Proposed Solution

Relay, do not re-emit. The bridge is an **out-of-process consumer** of the
existing `UnixSocketTransport` output: not a sixth transport, not a new emit
path, and not something `EventBus` ever holds a reference to. The tested
backpressure and isolation properties on the producer side stay untouched and
there is one serialization format end to end.

Because the bridge is a separate process, a bridge that crashes or stops
reading is indistinguishable, from the producer's side, from an ordinary slow
or disconnected socket client. That is already handled by `_record_drop` /
`_record_rejection` (`transport.py:314`, `:335`). No `events.py` change and no
`EventBus.emit` transport-isolation test are required.

Three sub-problems, in order:

1. **Fan-in.** The bridge globs the configured socket's directory, connects
   to each live producer socket as a client, and rescans periodically to pick
   up producers that start later. Stale files are skipped, never unlinked.
2. **Seeding.** The bridge owns seeding for its SSE clients: on every SSE
   connect it builds `state_change` frames from `.loops/.running/` itself, and
   it **drops** the `state_change` frames producers send it at socket-connect
   time. See § Program Design → Seeding for why.
3. **Bridge.** A stdlib `ThreadingHTTPServer` bound to loopback, one SSE
   route under a per-start token prefix, each event relayed as a `data:`
   frame. Slow clients are dropped rather than buffered.

## Program Design

### Types

- `producer_pid: int` — the producer's own `os.getpid()`, stamped by
  `UnixSocketTransport.send()` onto a copy of every envelope it serializes,
  alongside `event` and `ts`. It is **never** recovered from the socket
  filename: a lone producer keeps the unsuffixed configured path
  (`_claim_socket_path`, `transport.py:818`), so the common single-producer
  case has no pid in the filename to recover. On live frames it is always
  present. On bridge-built seed frames it is `LoopState.pid`, which is
  `int | None` (`fsm/persistence.py:361`) and which `to_dict()` already
  omits when unset (`:406-407`): the bridge does the same, **omitting the
  key** rather than writing `null`, so `_BASE_PROPS` can type it as a plain
  `integer` and EVENT-SCHEMA can say "optional; absent on a seed frame whose
  state file recorded no pid". Note that `to_dict()` already emits `pid`
  when set, so a bridge seed frame carries **both** `pid` and `producer_pid`
  with the same value; the redundancy is deliberate (one demux key on every
  frame) and EVENT-SCHEMA must say so.
- `_ProducerReader` — one per connected producer socket: the socket, a
  daemon thread, a partial-line buffer, and the path it was opened from.
- `SseBridge` — the server object, mirroring `LocalBridgeTransport`'s shape
  so tests get a handle: `__init__` binds the `ThreadingHTTPServer`, starts
  the serve thread, the fan-in thread, and the relay thread; `.url` returns
  the full tokenized URL from the bound port; `.close()` sets the shared
  stop `Event`, closes every producer client socket, shuts the server down,
  and joins its threads within a bounded budget. It is **not** a `Transport`
  and is never added to an `EventBus`.

### Signatures

- `class SseBridge(config: EventsConfig, port: int | None = None, *, base: Path | None = None, loops_dir: Path | None = None, routes: dict[str, Callable[[http.server.BaseHTTPRequestHandler], None]] | None = None)`
  — `port=None` means `config.bridge.port`; `port=0` is the test path.
  `base` is the socket-directory root passed to `_resolve_socket_path`
  (`None` = `Path(".ll")`), mirroring `wire_transports(log_dir=...)`;
  `loops_dir` is the seed source passed to `list_running_loops` (`None` =
  `Path(".loops")`). Both exist so every seed test and the
  "`.loops/.running/` untouched" test run against a tmp dir rather than the
  real repo state; `cmd_serve` passes neither.
  `routes` is the FEAT-3321 mount point: extra `GET` routes under
  `/{token}/`, keyed by path suffix, dispatched by the shared handler after
  the Host and token checks. This issue registers `""` (page) and `"events"`
  (SSE) through the same table rather than hardcoding them the way
  `_make_local_bridge_handler` does (`transport.py:474-479`).
- `SseBridge.url -> str`, `SseBridge.close() -> None`
- `serve_sse_bridge(config: EventsConfig, port: int | None = None) -> int`
  — the blocking CLI wrapper: construct `SseBridge`, print `.url`, block on
  the serve thread until `KeyboardInterrupt`, then `.close()`. Returns the
  process exit code (see § Server mechanics → Startup and shutdown).
- `_fan_in_producer_sockets(socket_path: Path, out: Queue[bytes], stop: threading.Event, rescan_s: float = 2.0) -> None`
  — runs the rescan loop until `stop` is set; owns the `_ProducerReader` set
  and detects reader death via `reader.thread.is_alive()` on each rescan
- `_read_producer_socket(sock: socket.socket, out: Queue[bytes], stop: threading.Event) -> None`
  — one reader thread body
- `_sse_bridge_seed_frames(loops_dir: Path) -> list[bytes]` — the
  bridge-owned seed, one encoded `state_change` frame per state file

### Call Path

`ll-artifact serve` -> `serve_sse_bridge` -> `SseBridge` ->
`_fan_in_producer_sockets` (one `_ProducerReader` thread per live producer
socket, merging into one bounded queue) -> relay thread -> per-SSE-client
bounded queue -> `data:` frame written to the browser at
`GET /{token}/events`.

### Fan-in and the socket reader

No consumer-side `AF_UNIX` reader exists in the package, so this is
specified rather than inherited:

- **Glob shape.** Match the configured path and its BUG-3324 siblings:
  `{stem}{suffix}` ∪ `{stem}-*{suffix}` in the configured path's directory,
  where the configured path comes from
  `_resolve_socket_path(config.socket.path, Path(".ll"))` (`transport.py:1202`).
- **Connect is the probe.** For each matched path the bridge is not already
  connected to, attempt a real client connect. `ECONNREFUSED` / `ENOTSOCK`
  means a stale file: skip it and log once at debug, tracked by a per-path
  seen-set so a stale file re-tried every `rescan_s` does not re-log (the
  set entry is cleared when the path later connects or disappears, so a
  producer that re-binds the same path after the pid is recycled logs
  fresh). Do **not** call
  `_probe_socket_path` (`:788`) on paths the bridge already holds a
  connection to: that helper opens a real connection, which would consume one
  of the producer's `max_clients` slots, re-trigger that producer's `_seed()`
  into a throwaway connection, and log `_record_rejection` warnings on a
  producer at cap, every `rescan_s`.
- **Never unlink.** Reclaiming a dead socket file is the producer's job
  (`_claim_socket_path`). The bridge is a consumer and must not delete
  anything in the socket directory.
- **Reader loop.** `recv()` with a timeout (so shutdown and rescan can
  interrupt), append to a per-reader buffer, split on `\n`, forward each
  complete line unchanged (it is already the serialized envelope) to the
  shared bounded queue, and keep the trailing partial line. A line that is
  not valid JSON is skipped with a rate-limited warning. EOF or any socket
  error marks the reader dead: close it, remove it from the connected set, and
  let the next rescan decide whether the path is live again (a restarted
  producer under a recycled pid) or gone.
- **Backoff on connect-then-immediate-EOF.** A producer already at
  `max_clients` *accepts* the bridge's connect and closes it at once
  (`_accept_loop`, `transport.py:241-247`), logging `_record_rejection`. The
  bridge cannot tell this from a producer that exited just after accepting,
  and a plain `rescan_s` retry would re-trip the producer's rejection log
  every 2 s for as long as it stays at cap. So: a reader that dies within
  one `rescan_s` of connecting without forwarding a single line marks its
  path as *flapping*; the fan-in loop doubles that path's retry interval on
  each consecutive flap (`rescan_s`, `2×`, `4×`, ... capped at 60 s), logs
  once per path at warning ("producer at %s closed the connection
  immediately; at max_clients?"), and resets the interval on the first
  successfully forwarded line. A test drives a producer with
  `max_clients=1`, a `nc`-style holder on the one slot, and asserts the
  producer's rejection count grows sub-linearly across several rescan
  intervals.
- **Filter `state_change`.** Every socket connect triggers the producer's
  `_seed()` (`:1114-1116`), which sends one `state_change` frame per state
  file in `.loops/.running/` (all processes' loops, terminal statuses
  included, per `list_running_loops`'s documented contract at
  `fsm/persistence.py:1396`). With N producers the bridge would receive N
  copies of the same seed set, unstamped, at fan-in time. `state_change` is
  emitted **only** by the seed and never on the EventBus
  (`docs/reference/EVENT-SCHEMA.md:1965`), so the bridge drops every
  `state_change` line from the socket side and seeds its own clients instead.
- **Shared queue.** The merged queue is bounded (`_CLIENT_QUEUE_MAXSIZE`);
  when full, drop-newest with the same four-field rate-limited accounting the
  transports use. The relay thread pops from it and fans out to each SSE
  client's own bounded queue.

### Seeding

Producers seed a client once, at socket-connect time. The bridge is a
long-lived socket client, so an SSE tab that reconnects would get nothing
unless the bridge seeds it. Reconnecting to every producer per SSE client is
wrong (it burns `max_clients` slots and re-triggers producer seeds per tab).

Decision: on each SSE connect, including reconnects, the bridge calls
`list_running_loops(Path(".loops"))` (`fsm/persistence.py:1396`; the running
directory is `.loops/.running/`, `RUNNING_DIR` at `:51`) and writes one
`{"event": "state_change", **state.to_dict()}` frame per state, with
`producer_pid` set to `state.pid` when that is not `None` and **omitted**
otherwise (§ Types). For seed frames `producer_pid` is the loop's owning
process (`LoopState.pid`, `:361`), which is the honest attribution: the
bridge, not a producer, emitted the frame.

**Order on connect (no gap between seed and live).** The client's queue is
registered in the fan-out set **first**, then the `list_running_loops`
snapshot is taken and the seed frames are written directly to the wire, and
only then does the handler start draining the queue. Any live event emitted
while the seed is being built and written is therefore already waiting in
the queue rather than lost. The reverse order (seed, then register) has a
window in which events are dropped on the floor; it is the wrong order and
the test for this criterion emits an event between snapshot and drain to
prove the queue caught it.

The cost of this order is a possible **duplicate, never a loss**: a
`state_enter` queued while the snapshot is being taken may describe a
transition the seed frame already reflects, so the client sees the seed at
state B and then a live `state_enter` for B. Consumers must treat seed frames
as idempotent snapshots. Record this in `CONFIGURATION.md` alongside the
no-replay contract so it is not filed as a bug.

Consequences to state in docs and tests:

- The seed covers **FSM loops only**. `ll-sprint run` and `ll-parallel`
  producers write no state files, so a mid-run SSE connect gets no seed for
  them. This matches today's socket seed.
- `list_running_loops` returns terminal states too (`completed`, `failed`,
  `timed_out`; BUG-3232) and runs `_reconcile_stale_running` (`:279`) on the
  read path, which can rewrite a stale `running` state file to `interrupted`.
  The bridge process therefore writes into `.loops/.running/` on every SSE
  connect. This is the same side effect every producer's `_seed()` has today;
  keep parity rather than filtering to `ACTIVE_RUN_STATUSES`.
- `Path(".loops")` and `Path(".ll")` are CWD-relative, as they are for every
  producer. `ll-artifact serve` runs from the project root, like the rest of
  `ll-artifact`.
- `_make_seed_callback` is **not modified**. The withdrawn idea of stamping
  `producer_pid` inside `_seed()` is unnecessary once the bridge filters
  socket-side `state_change` frames.

### Server mechanics

Reuse `LocalBridgeTransport`'s pieces where they exist and add what they
lack. `_SSEClient` (`transport.py:418`) and `_sse_encode` (`:430`) are
importable as-is. `_make_local_bridge_handler` (`:441`) is a closure over a
`LocalBridgeTransport` instance and is not callable for this bridge, so
extract shared module-level helpers used by both handlers: the Host check
(`_expected_hosts`, `:452-454`), the SSE write loop with dead-client pruning
(`_serve_events`, `:502-536`), and the four-field drop accounting
(`_record_drop`, `:734`). This is a small refactor of tested code guarded by
`TestLocalBridgeTransport`.

`LocalBridgeTransport` does **not** have the following; the shared write-loop
helper gains them as parameters (defaults preserving ENH-3351 behavior), or
they stay bridge-only:

- **Client cap.** Mirror `events.socket.max_clients` at the HTTP hop. Each
  SSE client holds a thread for the life of the connection, so an uncapped
  server is a thread-exhaustion surface from one user opening tabs. Over the
  cap, respond `503` before writing the stream headers.
- **Keepalive.** Emit an SSE comment frame (`: ping\n\n`) every
  `keepalive_s`. The precedent notices a vanished tab only on the next failed
  event write; on a quiet bus that could be minutes. Keepalive bounds the
  detection latency so the thread and queue are reclaimed promptly.
- **Reconnect semantics.** Send `retry: 2000` once at stream open (2 s; the
  browser default is typically 3 s, and the value only matters after a
  bridge restart, when the token has changed and the page must be reloaded
  anyway). Do **not** emit `id:` and do not implement `Last-Event-ID`
  replay: there is no durable buffer to replay from, and pretending
  otherwise would silently lie about completeness. Reconnect re-seeds
  (§ Seeding) and resumes live. Events emitted during the gap are lost by
  design; say so in the docs.

Inherited unchanged: `ThreadingHTTPServer` with `daemon_threads = True`
(`:640-641`), bounded per-client queue with drop-newest, `close_connection =
True` on stream exit so the handler thread does not leak (`:525-536`), the
`_SHUTDOWN` sentinel on close.

#### Startup and shutdown

`LocalBridgeTransport` has neither concern because `ll-loop run` owns its
process lifetime. `ll-artifact serve` is the process, so both are specified:

- **Port in use.** With a fixed default port, a second `ll-artifact serve`
  (or a stale one from another terminal) hits `OSError` `EADDRINUSE` from
  `ThreadingHTTPServer.__init__`. `cmd_serve` catches it and prints one line
  naming the port and the `--port` override, e.g.
  `ll-artifact serve: port 8766 is already in use (another ll-artifact serve?); pass --port N`,
  then returns exit code `1`. No traceback. Any other `OSError` at bind is
  re-raised. A test binds a throwaway socket to a `port=0` port **and calls
  `listen()` on it** (a bound-but-not-listening socket is ambiguous across
  Linux and macOS once `HTTPServer.allow_reuse_address` sets `SO_REUSEADDR`
  on the server side), then constructs `SseBridge` on that port and asserts
  the message and code.
- **Ctrl-C.** `serve_sse_bridge` blocks on the serve thread; on
  `KeyboardInterrupt` it calls `SseBridge.close()`, which sets the stop
  `Event` (fan-in loop and reader threads exit on their next `recv`/rescan
  timeout), closes every producer client socket (each producer's
  `_client_loop` then retires the slot via `_peer_closed`, `transport.py:274`),
  pushes `_SHUTDOWN` to every SSE client queue, shuts the HTTP server down,
  and joins its threads within `_LOCAL_BRIDGE_CLOSE_TIMEOUT`. Exit code `0`.
  Nothing in the socket directory or `.loops/.running/` is touched on the
  way out. A test calls `close()` on a bridge with one producer and one SSE
  client attached and asserts the producer's client count returns to 0, the
  SSE stream ends, and no non-daemon thread is left alive.
- **Exit codes** (`cli/artifact/__init__.py` epilog): `0` clean shutdown on
  Ctrl-C; `1` port in use or `AF_UNIX` unavailable; `2` argparse usage
  error (inherited).

### Security

Binding loopback is necessary but **not sufficient**. Three cheap controls,
all required, matching ENH-3351's docstring framing (`:570-578`):

- **Validate the `Host` header** per request against exactly
  `{f"127.0.0.1:{port}", f"localhost:{port}"}` computed from the bound port,
  returning `403` otherwise. This is `_expected_hosts()` (`:452-454`), the
  only per-request Host check in the codebase; `mcp_server/server.py`'s
  `_LOOPBACK_HOSTS` is a construction-time input to the MCP SDK, not a
  request check. `::1` is deliberately absent: the server binds IPv4 loopback
  only, so a `Host: [::1]:<port>` request cannot legitimately arrive.
- **Per-start token prefix.** Every route sits under `/{token}/` with
  `secrets.token_urlsafe(16)` (`:625`; `_route()` at `:456`). CORS blocks a
  cross-origin page from *reading* the stream but not from *sending* the
  request: `fetch(url, {mode: "no-cors"})` carries a legitimate `Host`
  header, passes the Host guard, and pins one of the `max_clients` SSE slots
  for as long as the page lives. The unguessable prefix closes that.
- **Send no `Access-Control-Allow-Origin`.** `EventSource` is subject to
  CORS, so omitting the header blocks cross-origin reads; a permissive value
  would undo the Host guard. No code in the repo sets `Access-Control-*`
  today and no test asserts its absence, so this issue's test is the first.

### Port and URL

Default to a fixed port (`8766`, adjacent to `ll-mcp`'s `8765`) and print the
full tokenized URL on startup. `LocalBridgeTransport` defaults to `port=0`
because `ll-loop run --serve` is a per-run server whose URL is printed once by
the process the user just started. `ll-artifact serve` is a long-lived,
explicitly started process the user returns to, so a stable port is the
right default; the token changes per start either way, and the printed URL is
the UX in both cases. `port=0` is the test path. The in-use failure mode is
specified in § Server mechanics → Startup and shutdown.

### Page

The Level 1 page at `GET /{token}/` is new code; `_LOCAL_BRIDGE_DEFAULT_PAGE_HTML`
(`transport.py:74`) is a placeholder, not a page. It opens an `EventSource`
on the events route and appends one line per frame.

**Trailing slash.** `_route()` (`transport.py:456-464`) serves the page for
both `/{token}` and `/{token}/`, but a relative `./events` resolves to
`/events` from the slash-less form and `404`s. The shared handler therefore
answers `GET /{token}` with a `301` to `/{token}/` (the printed URL already
has the slash), and the page builds its SSE URL as
`location.pathname.replace(/\/?$/, "/") + "events"` so it is correct even
if a future route serves it elsewhere. A bound-server test asserts the
`301` and its `Location` header.

**Escaping is mandatory.** Every relayed event can carry captured tool
output and untrusted text (`action_output`, evaluate payloads; BUG-3334's
concern applied to the browser hop). The precedent page is safe only
because `render_live_fragment` (`cli/artifact/dashboard.py:274`) renders
through a jinja `Environment(autoescape=True)`. This page renders raw JSON
client-side, so it must build every node with `document.createTextNode` /
`textContent` and must never assign `innerHTML`, `outerHTML`, or
`insertAdjacentHTML` from event data. The page is a single string constant
in `cli/artifact/serve.py`; a test asserts the string contains `textContent`
and none of the three sink names, and a bound-server test serves an event
whose payload contains `<script>` and asserts the SSE frame delivers it as
JSON-escaped data (the page-side assertion is static because there is no
browser in the suite). No htmx, no `sql.js`, no vendored assets: Level 1
(notify) only.

### Codebase Research Findings

_Added by `/ll:refine-issue` (2026-09-03) and re-verified 2026-09-03 against
the live tree. Only findings still true and still load-bearing are kept._

- **Reuse boundary for `LocalBridgeTransport`'s pieces**: `_sse_encode` (`transport.py:430`) is a pure function; `_SSEClient` (`:418`) is a plain per-client container with no token/Host logic. Both are directly importable. `_make_local_bridge_handler` (`:441`) references `transport._token`, `transport._inbound`, `transport._page_html` through its closure, and `LocalBridgeTransport.send()` is the `Transport.send()` Protocol method invoked by `EventBus.emit()`; using either directly would make the new bridge an `EventBus` transport, contradicting § Proposed Solution. Hence the extract-shared-helpers plan in § Server mechanics.
- **Drop/rejection accounting are per-instance methods, not standalone functions.** `UnixSocketTransport._record_drop`/`_record_rejection` (`:314`, `:335`) and `LocalBridgeTransport._record_drop` (`:734`) share an identical four-field shape (`*_total`, `*_since_log`, `last_*_log_ts`, `first_*_logged`) rate-limited via `_DROP_LOG_INTERVAL_SEC`/`_REJECT_LOG_INTERVAL_SEC` (5.0s each). No shared helper exists yet; this issue extracts one.
- **A real-bound HTTP/SSE test harness exists**: `TestLocalBridgeTransport` (`scripts/tests/test_transport.py:1019` onward, 15 methods) binds a real `LocalBridgeTransport(port=0)` per test and drives it over the network via `_lb_http_request` (`:940`), `_sse_connect` (`:969`), `_read_sse_headers` (`:986`), and `_read_sse_frame` (`:999`). `test_bad_host_header_returns_403` and `test_wrong_token_returns_404` are the direct models for this issue's Host-guard and token tests. The harness has no client-cap, keepalive, or `retry:` test because the precedent has none of those features.
- **Socket-layer test precedent**: `test_multi_client_each_receives_every_event` (`:464`) and `test_client_disconnect_does_not_affect_other_clients` model "two producers reach one client" and "a second producer does not disturb an existing client"; `test_max_clients_cap_rejects_extra_connection` (`:512`) and the drop-accounting tests model the slow-consumer criterion. All use the `short_tmp_path` fixture (`:58`) because raw `AF_UNIX` paths have an OS length ceiling `tmp_path` can exceed. `test_feat_3143_mcp_http_transport.py`'s Starlette `TestClient` pattern does not transfer (ASGI-only).
- **`state_change` provenance**: a grep for `"state_change"` in `scripts/little_loops/` hits only `transport.py:1116` (the seed). `EVENT-SCHEMA.md:1647` documents it as the "connection seed event" and `:1965` lists its source as "Socket seed (not on the EventBus)". This is what makes the § Fan-in filter safe.
- **`pid` is already a top-level envelope key with two other meanings**: `handoff_spawned` carries the spawned child's pid (`EVENT-SCHEMA.md:646,651`), and every `state_change` seed frame carries `LoopState.pid` via `to_dict()` (`fsm/persistence.py:361`). Hence `producer_pid`, not `pid`. `run_id` is stamped by `FSMExecutor._emit()` and every `parallel.*` emitter (ENH-3345/ENH-3346, both done) and is already in `generate_schemas.py`'s `_BASE_PROPS` (`:28-36`). No `producer_pid`/`producer_id` exists anywhere.
- **`events.*` config sub-block shape**: schema object under `events.<name>` with `additionalProperties: false` + `<Name>EventsConfig` dataclass with `from_dict` in `config/features.py` (`SqliteEventsConfig` at `:1286` is the freshest example) + `field(default_factory=...)` member on `EventsConfig` (`:1300-1323`) + a `to_dict()` mirror in `BRConfig.to_dict()` (`config/core.py:938-953`, which hand-inlines `socket`/`otel`/`webhook` and currently omits `sqlite`, a pre-existing gap) + a `_DATACLASS_SECTION_MAP` entry (`scripts/tests/test_config_schema.py:1382-1389`, where every events dataclass maps to the string `"events"`). `events.bridge` is unclaimed ground today: no schema key, dataclass, or member uses the name.
- **`mcp.http` is the precedent for a server config block** (`config-schema.json:611` onward): `host`/`port` defaults in config, with the console script's `--host`/`--port` flags taking precedence, and no `enabled` key; the user opts in by starting the server.
- **`ll-mcp` lazy-import pattern**: `main_mcp()` (`mcp_server/__init__.py:66-93`) imports its optional server dependency inside the function so the module still imports without the extra. This bridge is stdlib-only, so the pattern is not needed, but `test_real_pyproject_all_entry_points_resolve` (`test_cli_doctor_install_checks.py:45-51`) would fail on any eager optional import.
- **`docs/reference/ARTIFACT_CONTROL_LEVELS.md:49-58`** is a canonical table of render targets; a new target landing without a row is a stated contract violation. `ll-loop run --serve`'s page is declared Level 3 there.
- **Learning-test gate is satisfied.** `http.server` slugifies to `httpserver` and `.ll/learning-tests/httpserver.md` exists (landed with ENH-3351). Separately, `http` is in `learning_tests/extractor.py:73`'s `_STDLIB_EXCLUDED`, so the extractor drops the target anyway. Nothing to do.
- Adjacent, not integration points: `cli/loop/__init__.py:296,306` (`--serve`/`--port` argparse), `templates/dashboard.llat/`, `assets/vendor/htmx/`, `observability/schema.py:379`, `docs/ARCHITECTURE.md:902-918` ("Artifact Control Layer"). `docs/reference/API.md` already documents `LocalBridgeTransport` (module table row + `### LocalBridgeTransport`, ~`:10649`); this issue's API.md entry follows that shape.

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py`:
  - `UnixSocketTransport.send()` (`:304`) stamps `producer_pid = os.getpid()`
    onto a **copy** of `event` before `json.dumps` (copy, not mutate; see
    § Dependent Files).
  - Extract shared helpers from `_make_local_bridge_handler` (`:441`): the
    Host check, the SSE write loop (gaining optional cap / keepalive /
    `retry:` parameters), and the drop accounting. `LocalBridgeTransport`
    keeps its behavior and its tests.
  - New: `_ProducerReader`, `_read_producer_socket`,
    `_fan_in_producer_sockets`, `_sse_bridge_seed_frames`, `SseBridge`,
    `serve_sse_bridge` per § Program Design. Reuses `_resolve_socket_path`
    (`:1202`) for the directory, `_SSEClient`/`_sse_encode` for clients, and
    `list_running_loops` for the seed. The shared handler builder takes a
    route table (`SseBridge(routes=...)`) so FEAT-3321 mounts without
    touching the handler.
  - `_make_seed_callback` (`:1110`) is **not modified**.
- ~~`scripts/little_loops/events.py`~~ — **not modified.** The bridge is
  out-of-process, so `EventBus.emit` needs no change.
- `scripts/little_loops/config/features.py` — new `BridgeEventsConfig`
  dataclass beside `SocketEventsConfig` (`:1151`), member on `EventsConfig`
  (`:1300-1323`).
- `scripts/little_loops/config-schema.json` — `events` (`:1628`) is
  `additionalProperties: false`; add the `bridge` sub-object.
- `scripts/little_loops/config/core.py:938-953` — `BRConfig.to_dict()` gains
  the `events.bridge` mirror (do not copy the `sqlite` omission).
- `scripts/little_loops/config/__init__.py` — re-export `BridgeEventsConfig`
  and add it to `__all__` (the existing events dataclasses are at
  `:53,69,75,80,124,127,128`). Enforce it with a
  `test_reexported_from_config_package` method on `TestBridgeEventsConfig`,
  the repo convention (`TestCompressionConfig`, `scripts/tests/test_config.py:3402`).
- `scripts/little_loops/cli/artifact/serve.py` (new) — `add_serve_parser` /
  `cmd_serve`, one module per subcommand per `cli/artifact/__init__.py:22-27`,
  modeled on `dashboard.py`. `--port` overrides `events.bridge.port`. Owns
  the Level 1 page string (§ Page) and the `EADDRINUSE` / Ctrl-C handling
  (§ Startup and shutdown).
- `scripts/little_loops/cli/artifact/__init__.py` — import alongside `:36-47`,
  `add_serve_parser(subparsers)` alongside `:174`, dispatch branch alongside
  `:195-196`, docstring bullet (`:1-28`), `Examples:`/`Exit codes:` epilog
  entries. `ll-artifact` is already a `[project.scripts]` entry; **no new
  entry point, no `pyproject.toml` change, no new `main_*` export.**
- `scripts/little_loops/generate_schemas.py:25` — add `producer_pid` to
  `_BASE_PROPS` alongside `run_id`, `"type": "integer"`, optional (not in
  `_BASE_REQUIRED`), with a description naming `UnixSocketTransport.send()`
  as the stamping site, noting it is absent on a seed frame whose state
  recorded no pid (never `null`; § Types), and that on a seed frame it
  equals the frame's `pid`.

### Dependent Files (Callers/Importers)
- The four `wire_transports` call sites and `scripts/little_loops/__init__.py:63,117`
  are unchanged: the envelope gains a key, not a signature.
- `scripts/little_loops/events.py` — `EventBus.emit()` passes the same mutable
  `event` dict to every registered transport's `.send()`. A stamp implemented
  by in-place mutation would leak `producer_pid` into `JsonlTransport`,
  `SQLiteTransport`, `OTelTransport`, and `WebhookTransport` whenever
  `"socket"` is listed alongside them. Copy, then stamp.
- `fsm.persistence.list_running_loops` (`:1396`) — called by the bridge on
  every SSE connect. Its read-path reconciliation writes state files; see
  § Seeding.
- `scripts/tests/test_config_schema.py:1283-1336`
  (`test_to_dict_values_match_schema_defaults`, `test_guard_is_non_vacuous`)
  — BUG-3192 Guard 1: every `to_dict()` leaf must match the schema default.
- `scripts/tests/test_config_schema.py:1346-1411` (`_DATACLASS_SECTION_MAP`)
  — BUG-3192 Guard 2: add `"BridgeEventsConfig": "events"`.
- `scripts/tests/test_config.py:2621-2667`
  (`test_events_transport_sub_config_round_trips_through_to_dict`,
  parametrized `["socket", "otel", "webhook"]`) — `events.bridge` gates a
  server, not a transport, so it does not join this list; add a separate
  round-trip assertion for the `bridge` leaves instead.
- `scripts/tests/test_wiring_cli_registry.py:226-236`
  (`test_cli_entry_point_coverage`) — fires only for new `[project.scripts]`
  entries; not triggered. CLI.md needs a subcommand-level entry instead.
- `docs/reference/HOST_COMPATIBILITY.md:107` — cites `UnixSocketTransport` as
  a deferred hook-latency "sidecar" mitigation; confirm the framing still
  reads correctly once the transport has a bridge consumer.

### Similar Patterns
- `LocalBridgeTransport` (`transport.py:567`) — the server precedent. See
  § Server mechanics for what is reused and what is added.
- `UnixSocketTransport`'s per-client bounded queue + daemon thread + drop
  accounting (`:207-280`) — the model for a slow SSE client and for the
  bridge's merged queue.
- `_claim_socket_path` / `_probe_socket_path` (`:818`, `:788`) — the
  producer-side classification of stale sockets. The bridge's connect-is-the-
  probe rule mirrors the errno handling without calling the helper on
  already-connected paths.

### Tests
- Existing suite that must stay green: `TestUnixSocketTransport` (every
  assertion checks `["event"]` only, so the new key is safe),
  `TestLocalBridgeTransport` (guards the helper extraction; the two
  full-dict-equality assertions there are against `LocalBridgeTransport.send()`,
  which does not stamp), the BUG-3324 socket-path-shape tests, and the
  slow-client / rejection log assertions.
- `scripts/tests/test_config.py::TestSocketEventsConfig` (`:2485`) — pattern
  (`test_defaults` + `test_from_dict_with_overrides`) for
  `TestBridgeEventsConfig`.
- `scripts/tests/test_config_schema.py::test_events_in_schema` (`:752-814`)
  — extend with a `bridge` sub-block assertion.
- `scripts/tests/test_generate_schemas.py` — `producer_pid` appears in every
  generated schema's properties and not in `required`.

New tests, each against a really-bound `SseBridge(port=0, base=<short_tmp_path>,
loops_dir=<tmp_path>)` (constructed in a fixture, `.close()`d in teardown,
`.url` giving the token and port), reusing the `_sse_connect` /
`_read_sse_frame` helpers. `base` must be the `short_tmp_path` fixture
(`test_transport.py:58`) because the producer sockets live under it.
**Seed fixtures must not trip reconciliation**: `list_running_loops` runs
`_reconcile_stale_running` (`fsm/persistence.py:279`), which rewrites a
`running` state whose pid is dead or unresolvable-and-stale to
`interrupted`. State files written by tests use a terminal status
(`completed`) or a fresh `updated_at` with `pid = os.getpid()`, so the
"directory unchanged" assertions are deterministic.

- `UnixSocketTransport.send()` stamps `producer_pid == os.getpid()` and does
  not mutate the caller's dict (a second transport on the same bus sees no
  `producer_pid`).
- Two producer sockets in one directory, one SSE client: events from both
  arrive with distinct `producer_pid` values. Model on
  `test_multi_client_each_receives_every_event`.
- A producer socket created after the bridge is serving is picked up by the
  rescan and its events reach the attached client.
- A rescan does not open a new connection to a producer the bridge is already
  connected to (assert the producer's client count stays at 1 across two
  rescan intervals).
- A stale socket file (bound then closed) is skipped and **not unlinked**.
- Producer EOF: the reader exits, the path is dropped from the connected set,
  and a fresh producer at the same path is reconnected on the next rescan.
- Producer at cap (`max_clients=1`, slot held by a throwaway client): the
  bridge's retry interval for that path backs off, the producer's
  `get_stats()["client_rejections"]` grows sub-linearly across several
  `rescan_s` intervals, and the path recovers once the slot is released
  (§ Fan-in → Backoff).
- `GET /{token}` (no trailing slash) returns `301` with
  `Location: /{token}/`; the page string builds its SSE URL from
  `location.pathname`, not a bare `./events` (§ Page → Trailing slash).
- Socket-side `state_change` lines are not relayed to SSE clients.
- An SSE client connecting with a state file in `.loops/.running/` receives
  that `state_change` frame with `producer_pid == state.pid` before live
  traffic, and receives it again on reconnect. A second state file with no
  `pid` yields a seed frame with **no** `producer_pid` key (not `null`).
- Seed-to-live gap: an event emitted after the client's queue is registered
  but before the seed is written arrives after the seed frames, not lost
  (§ Seeding → Order on connect). Drive it by patching
  `list_running_loops` to emit on the producer mid-call.
- `SseBridge(routes={"extra": handler})` serves `GET /{token}/extra` through
  `handler` after the Host and token checks, and `GET /{token}/other` still
  `404`s (the FEAT-3321 mount point).
- `SseBridge` on a port already bound by a throwaway socket: `cmd_serve`
  prints the port-in-use message naming `--port` and returns `1`, with no
  traceback.
- `SseBridge.close()` with one producer and one SSE client attached: the
  producer's `_clients` drains to 0, the SSE stream ends, the socket
  directory and `.loops/.running/` are unchanged, and no bridge thread is
  alive after the join budget.
- The page constant contains `textContent` and none of `innerHTML`,
  `outerHTML`, `insertAdjacentHTML`; an event whose payload contains
  `<script>` reaches the SSE client as JSON-escaped data (§ Page).
- `Host: evil.example.com` gets `403`. Model on
  `test_bad_host_header_returns_403`.
- Wrong or missing token prefix gets `404`. Model on
  `test_wrong_token_returns_404`.
- No `Access-Control-Allow-Origin` header on the SSE response.
- Client cap: `max_clients` readers attached, the next gets `503`, the
  existing readers keep receiving. Model on
  `test_max_clients_cap_rejects_extra_connection`.
- A client that stops reading is dropped (drop counter increments, queue stays
  bounded) without disturbing a second healthy client.
- A keepalive comment frame arrives within `keepalive_s` on a quiet bus, and
  `retry:` appears once at stream open with no `id:` lines.
- `serve_sse_bridge` binds `127.0.0.1` only (signature default, modeled on
  `test_run_http_defaults_to_loopback_not_public`).
- With `"socket"` absent from `events.transports` or no producer socket
  present, the CLI prints a clear message rather than serving an empty stream
  as success.

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — § Wire Format gains `producer_pid`
  (integer, optional; always present on socket-relayed live frames, absent
  on a seed frame whose state recorded no pid); the `state_change` entry
  (`:1647`) notes the bridge-owned seed and that a seed frame carries both
  `pid` and `producer_pid` with the same value.
- `docs/reference/CONFIGURATION.md:1559-1589` — `events.bridge` keys, the
  redaction decision and its revisit trigger, the no-replay reconnect
  contract, the seed-then-live duplicate-not-loss contract (§ Seeding), and
  the seed scope (FSM loops only).
- `docs/ARCHITECTURE.md:613-615` — transport fan-out, socket seeding, and the
  bridge as an out-of-process consumer.
- `docs/reference/API.md` — `UnixSocketTransport` (the stamp),
  `serve_sse_bridge` and the fan-in helpers, following the existing
  `LocalBridgeTransport` entry's shape.
- `docs/reference/CLI.md` — `ll-artifact` subcommand table row plus a
  `#### ll-artifact serve` section beside `#### ll-artifact dashboard`
  (`:4777`), linking to `ARTIFACT_CONTROL_LEVELS.md`.
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md:49-58` — a **Level 1 (notify)**
  row for the minimal page. Mandatory: the doc calls a missing row a
  contract violation.
- `docs/reference/HOST_COMPATIBILITY.md:107` — re-read the sidecar framing.

### Configuration

Existing keys consumed: `events.transports` (default `[]`),
`events.socket.path` (default `.ll/events.sock`), `events.socket.max_clients`
(default `32`).

New block `events.bridge`, following the three-part shape every `events.*`
sub-block uses. There is **no `enabled` key and no `host` key** (see
§ Resolved Decisions):

| Key | Default | Meaning |
|---|---|---|
| `port` | `8766` | Fixed so the printed URL is stable; `0` = OS-assigned, tests only; `--port` overrides |
| `max_clients` | `8` | Concurrent SSE connections; over the cap returns `503` |
| `keepalive_s` | `15` | SSE comment-frame interval; schema `type: number` (the signature takes a float) |
| `rescan_s` | `2` | Producer-socket directory rescan interval; schema `type: number`; also the base of the per-path backoff (§ Fan-in) |

`events.bridge` gates a server, not a transport: no `_TRANSPORT_REGISTRY`
entry and no `wire_transports` branch. FEAT-3321 adds its own sub-key
(`history: bool`) to this block rather than a separate one.

## Implementation Steps

1. **Envelope.** `UnixSocketTransport.send()` copies `event`, stamps
   `producer_pid = os.getpid()`, serializes. Add `producer_pid` to
   `generate_schemas.py`'s `_BASE_PROPS`, regenerate `docs/reference/schemas/`,
   and document it in `EVENT-SCHEMA.md` § Wire Format. The collision grep
   (§ Resolved Decisions) is done: no payload uses `producer_pid`. FEAT-1930's
   `human_approval_requested`/`human_response` are unimplemented, so there is
   nothing to grep there yet; the bridge relays them unfiltered when they land.
2. **Config.** `BridgeEventsConfig` + schema + `EventsConfig` member +
   `to_dict()` mirror + `_DATACLASS_SECTION_MAP` entry + `config/__init__.py`
   re-export.
3. **Refactor.** Extract the Host check, SSE write loop, and drop accounting
   from `_make_local_bridge_handler` into module-level helpers, with cap /
   keepalive / `retry:` as optional parameters defaulting to ENH-3351's
   behavior. `TestLocalBridgeTransport` stays green unmodified.
4. **Fan-in.** `_ProducerReader`, `_read_producer_socket`,
   `_fan_in_producer_sockets` per § Fan-in: glob, connect-is-the-probe, never
   unlink, partial-line buffering, EOF handling, per-path backoff on
   immediate EOF, `state_change` filter, bounded merged queue.
5. **Bridge.** `SseBridge` on `ThreadingHTTPServer` per § Server mechanics
   and § Security: loopback bind, token prefix, Host guard, no CORS header,
   client cap, bounded per-client queues, keepalive, `retry: 2000` with no
   `id:`, route table for `""`/`"events"` (and FEAT-3321 later), `301` from
   `/{token}` to `/{token}/`, `base`/`loops_dir` kwargs, `.url`, `.close()`
   with the shared stop `Event`.
6. **Seeding.** `_sse_bridge_seed_frames` from `list_running_loops`, written
   to each SSE client on every connect in the register → seed → drain order
   (§ Seeding), omitting `producer_pid` when `LoopState.pid` is `None`.
7. **CLI.** `cli/artifact/serve.py` + registration in `main_artifact()`.
   `serve_sse_bridge` prints the full tokenized URL on startup, blocks, and
   handles Ctrl-C and `EADDRINUSE` per § Startup and shutdown (exit codes in
   the epilog). If `"socket"` is not in `events.transports` or no producer
   socket exists, say so plainly and keep serving (a producer may start
   later). Without `AF_UNIX`, fail with the same message `wire_transports`
   uses, exit `1`.
8. **Page.** The smallest page that renders the stream, to prove it
   end-to-end. Level 1 (notify). `textContent` only; SSE URL built from
   `location.pathname`, per § Page.
9. **Docs.** Per § Documentation, including the `ARTIFACT_CONTROL_LEVELS.md`
   row and the CLI.md subcommand section.

## Impact

- **Priority**: P3, a developer-experience capability. The correctness half
  was BUG-3324, now done.
- **Effort**: Small-Medium. The HTTP/SSE side reuses ENH-3351's tested server
  and harness. The genuinely new code is the consumer-side socket reader and
  the rescan loop, which have no precedent in the package.
- **Risk**: Low-Medium. No change to the socket binding path; one additive
  envelope key; a new out-of-process server nothing else depends on. A bridge
  failure cannot reach a run. The refactor in Step 3 touches
  `LocalBridgeTransport`, but its tests pin the behavior.
- **Breaking Change**: Additive envelope key only. The collision grep is done
  (`producer_pid` is unused; `pid` and `run_id` are taken and avoided).

## Use Case

A user kicks off `ll-sprint` and, in another terminal, `ll-loop run`. They want
one browser tab showing FSM state transitions and issue lifecycle events from
both as they happen, which `ll-artifact dashboard` structurally cannot do
(frozen at export) and `ll-loop run --serve` cannot do (one run).

## Scope

### In scope

- A localhost HTTP server exposing bus events as **SSE** (`text/event-stream`),
  bound to loopback only. SSE over WebSocket: one-way, reconnects on its own,
  no client library.
- Consuming the existing `UnixSocketTransport` stream rather than adding a
  transport type or an emit path.
- **Fan-in over the producer socket directory**, including producers that
  start after the bridge does.
- **Producer attribution in the envelope** (`producer_pid`), documented in
  `EVENT-SCHEMA.md`.
- Bridge-owned current-state seeding on every SSE connect.
- The three security controls: Host guard, token prefix, no CORS header.

### Out of scope

- Any UI beyond the minimum needed to prove the stream works.
- Live-querying `.ll/history.db` (FEAT-3321; mounts on this server).
- Any write path or command execution from the browser.
- Remote or multi-user access. Loopback only.
- Replacing or deprecating `UnixSocketTransport`; `nc -U` keeps working.
- Seeding for non-FSM producers (`ll-sprint`, `ll-parallel`), which write no
  state files. Parity with today's socket seed.
- Replay of events missed while an SSE client was disconnected.

## Relationship to FEAT-3321

These are adjacent and must not be merged carelessly:

- **FEAT-3321** serves *row* questions over `.ll/history.db` ("what has
  happened, aggregated") by polling a read-only query endpoint.
- **This issue** serves *event* questions off the bus ("what is happening
  right now") by pushing an event as it is emitted.

They share one server process and one config block. **Resolved 2026-08-26,
reconfirmed 2026-09-03**: this issue claims `ll-artifact serve` and defines
the server; FEAT-3321 mounts its query route on it via `SseBridge(routes=...)`
(§ Signatures) and adds a `history` sub-key to `events.bridge`. FEAT-3321's page is `dashboard.llat` via
`build_dashboard_html(serve_context=...)`, which needs `ServeContext`
(`cli/artifact/dashboard.py:133`) to accept `interaction_url=None` or the
server to `404` the POST route, since this server has no executor behind it.
That change belongs to FEAT-3321. Not a blocking dependency in either
direction.

## Relationship to FEAT-1930

This bridge is a read-only relay: it would surface `human_approval_requested`
and `human_response` events (once FEAT-1930's EventBus adapter emits them)
like any other bus event, with no special-casing. A browser-side verdict
adapter would be a separate, future FEAT layered on both issues.

## API/Interface

- **`ll-artifact serve [--port N]`** — a subcommand of the existing
  `ll-artifact` entry point (no new `[project.scripts]` entry). Serves
  `GET /{token}/` (minimal page) and `GET /{token}/events` (SSE). Prints the
  full URL on startup. `--port` overrides `events.bridge.port`.
- **`events.bridge`** config block, sibling to `events.socket`. Keys and
  defaults in § Integration Map → Configuration.

## Considerations

- **`events.transports` is `[]` by default.** Nothing streams unless the
  project opts in. The bridge must say so plainly at startup rather than
  presenting an empty stream as quiet success, and keep serving in case a
  producer starts later.
- **Backpressure holds at both hops.** A browser tab that stops reading must
  not grow an unbounded buffer in the bridge; the bridge stopping must not
  stall a producer. The first is the per-client bounded queue; the second is
  the producer's existing `_record_drop` path (`transport.py:314`).
- **Probe etiquette.** The bridge holds one of each producer's `max_clients`
  (32) slots for as long as it runs, and must not spend more by re-probing
  connected sockets (§ Fan-in).
- **POSIX only.** `wire_transports` raises `RuntimeError` for `"socket"`
  where `AF_UNIX` is unavailable. The bridge fails with the same clarity.
- **Not `ll-logs`/`ll-session`.** Those read persisted history. This is the
  live bus.

## Resolved Decisions

_Settled 2026-08-26 during pre-implementation review, extended 2026-09-03._

- **Redaction: none on the live path.** ENH-075's column allowlist is applied
  at export time in `cli/artifact/dashboard.py`; there is no equivalent on the
  bus and this issue does not add one. Rationale: the stream is the user's own
  project data, the listener is loopback-only, the Host guard blocks DNS
  rebinding, the token prefix blocks blind requests, no CORS header is sent,
  and the capability is opt-in twice: `events.transports` is `[]` by default
  and the user must explicitly start `ll-artifact serve`. **Revisit
  trigger**, to be recorded in `CONFIGURATION.md`: any change that makes the
  endpoint reachable off-host, or any multi-user access.
- **Multi-producer shape: probe-and-claim**, specified and landed in
  BUG-3324. A lone producer keeps the configured path; a concurrent producer
  binds `events-<pid>.sock` beside it.
- **Envelope key: `producer_pid`, stamped from `os.getpid()` in
  `UnixSocketTransport.send()`.** Not `pid` (taken twice with other meanings),
  not `run_id` (ENH-3346), never recovered from the filename. Additive;
  external consumers read by key.
- **Bridge-owned seeding; socket-side `state_change` dropped (2026-09-03).**
  Producer seeds only fire at socket connect, `list_running_loops` returns
  every process's loops, and `state_change` exists only as the seed. So the
  bridge filters it on the way in and rebuilds it per SSE client, attributing
  each frame to `LoopState.pid`. `_make_seed_callback` is untouched.
- **Token prefix adopted (2026-09-03).** Third control alongside Host guard
  and no-CORS; closes the `no-cors` slot-pinning gap. Precedent ENH-3351.
- **Fixed default port `8766` (2026-09-03, re-justified).** Long-lived
  explicitly started server, so a stable port; `port=0` remains the test path.
  ENH-3351's `port=0` default is right for its per-run case.
- **No `enabled` and no `host` key (2026-09-03).** The user opts in by running
  the command; a config flag that refuses an explicit command is bad UX and
  has no precedent (`ll-loop run --serve` and `ll-mcp` have none). The server
  binds `127.0.0.1` unconditionally, matching `LocalBridgeTransport`, which is
  stricter than a validated `host` key.
- **Connect-is-the-probe; never re-probe connected sockets; never unlink
  (2026-09-03).** See § Fan-in.
- **Factor shared helpers out of `_make_local_bridge_handler` rather than
  copy-adapting it (2026-09-03).** Both bridges live in `transport.py`;
  `TestLocalBridgeTransport` guards the refactor.
- **`SseBridge` object plus a blocking wrapper, not a bare blocking function
  (2026-09-03, review).** Every test in § Tests needs the bound port, the
  token, and a `close()`; a `-> None` function that blocks forever gives
  none of them. Mirrors `LocalBridgeTransport`'s constructor-binds shape.
- **Register-then-seed-then-drain on SSE connect (2026-09-03, review).**
  The earlier "seed before joining the live stream" wording had a lossy
  window. See § Seeding → Order on connect.
- **`producer_pid` is omitted, never `null`, on a seed frame with no pid
  (2026-09-03, review).** `LoopState.pid` is `int | None`; matching
  `to_dict()`'s omission keeps the schema type a plain `integer`.
- **Route table on the shared handler (2026-09-03, review).** Costs nothing
  now and spares FEAT-3321 a handler refactor.
- **`EADDRINUSE` and Ctrl-C are specified, with exit codes (2026-09-03,
  review).** A fixed default port makes the in-use case routine, and
  `ll-artifact serve` owns its process lifetime, unlike `--serve`.
- **Page renders via `textContent` only (2026-09-03, review).** Event
  payloads carry untrusted captured output (BUG-3334); the precedent's
  safety comes from jinja autoescape, which this page does not use. Seed
  frames are in scope for this too: `to_dict()` includes `captured`,
  `prev_result`, and `last_result`.
- **Per-path backoff on connect-then-immediate-EOF (2026-09-03, third
  review).** A producer at `max_clients` accepts then closes; without
  backoff the bridge would re-trip its rejection log every `rescan_s`.
- **`base` / `loops_dir` kwargs on `SseBridge` (2026-09-03, third review).**
  The seed and "directory untouched" tests cannot run against the repo's
  own `.ll/` and `.loops/`; mirrors `wire_transports(log_dir=...)`.
- **`301` from `/{token}` to `/{token}/`; page derives its SSE URL from
  `location.pathname` (2026-09-03, third review).** A relative `./events`
  breaks from the slash-less URL the precedent also accepts.
- **Seed-then-live may duplicate, never lose (2026-09-03, third review).**
  Documented as a consumer contract rather than engineered away.
- **Merged queue + relay thread kept as specified (2026-09-03, third
  review).** Readers fanning out directly to per-client queues would drop
  one hop and one drop-accounting site; deferred as an optional
  simplification the implementer may take if it falls out naturally.

## Open Questions

- None blocking.

## Acceptance Criteria

- [ ] A browser page on loopback receives bus events over SSE as they are
      emitted by a running loop, with no polling and no page reload.
- [ ] Two concurrent producers (e.g. `ll-loop run` and `ll-sprint run`) both
      stream to a single connected SSE client, each event carrying its own
      producer's `producer_pid`, asserted by a test over two producer sockets
      in one directory.
- [ ] A producer that starts *after* the bridge is already serving is picked up
      by the directory rescan and its events reach an attached client; the
      rescan opens no extra connections to producers already connected, and
      never unlinks a socket file.
- [ ] Producer EOF is handled: the reader exits, and a new producer at the same
      path is reconnected on a later rescan. A producer that closes the
      connection immediately (at `max_clients`) is retried with per-path
      backoff so its rejection count grows sub-linearly, asserted by a test.
- [ ] Every relayed live event carries `producer_pid == os.getpid()` of its
      producer, stamped on a copy (other transports on the same bus see no
      `producer_pid`), documented in `EVENT-SCHEMA.md` and present in
      `generate_schemas.py`'s `_BASE_PROPS`.
- [ ] Socket-side `state_change` frames are not relayed; instead an SSE client
      connecting while a loop is mid-run receives bridge-built `state_change`
      frames (with `producer_pid == LoopState.pid`, or no `producer_pid` key
      when the state recorded no pid) before live traffic, on every connect
      including reconnects; a live event emitted during the seed write is
      delivered after the seed, not lost.
- [ ] `SseBridge` exposes `.url` and `.close()`; `close()` releases every
      producer slot, ends every SSE stream, leaves the socket directory and
      `.loops/.running/` untouched, and leaves no bridge thread alive after
      its join budget. `SseBridge(routes=...)` dispatches an extra `GET`
      route under `/{token}/` after the Host and token checks;
      `SseBridge(base=..., loops_dir=...)` redirects the socket directory and
      seed source so tests never touch the repo's own state dirs.
- [ ] `GET /{token}` without a trailing slash returns `301` to `/{token}/`,
      and the page constant derives its SSE URL from `location.pathname`
      rather than a bare relative `./events`.
- [ ] `ll-artifact serve` on an in-use port prints one line naming the port
      and `--port` and exits `1` with no traceback; Ctrl-C exits `0`; the
      exit codes are in the `ll-artifact` epilog.
- [ ] The Level 1 page renders event data through `textContent` only (no
      `innerHTML` / `outerHTML` / `insertAdjacentHTML`), asserted by a test.
- [ ] A consumer that stops reading is dropped without unbounded buffering in
      the bridge and without stalling or failing the producing run.
- [ ] The listener binds loopback only; a test asserts the signature default.
- [ ] A request with a non-loopback `Host` header gets `403`; a request with a
      wrong or missing token prefix gets `404`; no
      `Access-Control-Allow-Origin` header is sent. All three asserted against
      a really-bound server.
- [ ] Concurrent SSE clients are capped at `events.bridge.max_clients`; the
      connection over the cap gets `503` and existing clients are undisturbed.
- [ ] A keepalive comment frame arrives within `keepalive_s` on a quiet bus;
      `retry: 2000` is sent once at stream open; no `id:` is ever sent.
- [ ] The server starts on `events.bridge.port` (default `8766`, `--port`
      overrides) and prints the full tokenized URL; with `"socket"` absent from
      `events.transports` or no producer socket present it says so plainly and
      keeps serving.
- [ ] `events.bridge` (`port`, `max_clients`, `keepalive_s`, `rescan_s`) is in
      `config-schema.json` (`keepalive_s`/`rescan_s` typed `number`),
      `BridgeEventsConfig`, `EventsConfig`, `BRConfig.to_dict()`,
      `_DATACLASS_SECTION_MAP`, and `config/__init__.py` (the re-export
      asserted by `test_reexported_from_config_package`), and both BUG-3192
      schema guards pass.
- [ ] `TestLocalBridgeTransport` passes unmodified after the helper
      extraction.
- [ ] `docs/reference/ARTIFACT_CONTROL_LEVELS.md` has a Level 1 row for the
      minimal page, and `CLI.md` has an `ll-artifact serve` section linking
      to it.
- [ ] The redaction decision, its revisit trigger, the no-replay reconnect
      contract, the seed-then-live duplicate-not-loss contract, and the
      FSM-loops-only seed scope are recorded in
      `docs/reference/CONFIGURATION.md`; `EVENT-SCHEMA.md` states that a seed
      frame carries both `pid` and `producer_pid` with the same value.

## Related Key Documentation

- `docs/reference/EVENT-SCHEMA.md` — wire format, event catalog, `state_change`
- `docs/reference/CONFIGURATION.md` — `events.transports`, `events.socket`
- `docs/ARCHITECTURE.md` — transport fan-out and socket seeding
- `docs/reference/API.md` — `UnixSocketTransport`, `LocalBridgeTransport`,
  `wire_transports`
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — render-target level table

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-03. Re-run confirms the
2026-09-03 reconcile addressed the prior contradictions. Re-verified again
2026-09-03 (no issue-content changes since the prior run): every cited
precedent (`LocalBridgeTransport`, `_SSEClient`/`_sse_encode`,
`_expected_hosts`, `SqliteEventsConfig`/`SocketEventsConfig` shape,
`BRConfig.to_dict()`'s `sqlite` omission, `list_running_loops`,
`generate_schemas.py._BASE_PROPS`) checked out unchanged against the live
tree, and no `SseBridge`/`serve_sse_bridge`/`events.bridge` code exists yet.
Scores unchanged._

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 58/100 → LOW

### Gaps to Address (advisory, non-blocking)
- `stale_cli_flag`: `ll-artifact serve (no such subcommand)`. Expected; this
  issue creates it. Caps Criterion 4 (Issue Well-Specified) at 10/20 per the
  Parity/Claim/Structure cap regardless of otherwise-complete specification.

### Outcome Risk Factors
- Breadth is wide (16+ change sites): `transport.py` (stamp, helper
  extraction, reader, fan-in, server), the `events.bridge` block across five
  files, the CLI subcommand and its registration, `generate_schemas.py`, and
  six documentation files.
- Depth is Moderate: one reader thread per producer socket merging into a
  shared bounded queue that feeds per-SSE-client bounded queues. Cross-thread
  shared state, not a contained single-function change.
- The wholly new consumer-side socket reader and fan-in loop have no in-repo
  test precedent yet — the test plan is fully enumerated but not yet written,
  which is why Test Coverage scores 18/25 rather than 25/25.
- The change touches guarded contracts (two BUG-3192 schema-parity tests,
  `TestLocalBridgeTransport` across the refactor). Each is mechanical but a
  missed leaf fails loudly.

## Revision History

- **2026-08-26 — pre-implementation review.** Split the multi-producer socket
  collision out to BUG-3324. Resolved the open questions (no redaction +
  revisit trigger; probe-and-claim; additive envelope key). Specified server
  mechanics, Host guard, no-CORS rule, fixed port, `events.bridge`, and
  claimed `ll-artifact serve`. Confidence 93/69 at the time.
- **2026-08-28.** BUG-3324 and ENH-3351 landed; a STALE NOTICE recorded that
  the "no stdlib HTTP / SSE / `port=0` precedent" research and the
  "harness from scratch" risk were void.
- **2026-09-03 — refine, wire, review, reconcile.** Verified against the
  live tree and folded into the directive sections, deleting the STALE NOTICE
  and Pre-implementation Review Findings layers: `producer_pid` stamped from
  `os.getpid()` (never recovered from the filename); token prefix adopted;
  `_expected_hosts` precedent (no `::1`); port re-justified; bridge-owned
  seeding with the socket-side `state_change` filter (the earlier plan to map
  `LoopState.pid` onto relayed seed frames was wrong, since `list_running_loops`
  returns every process's loops); a consumer-side socket reader spec (no
  in-repo precedent); connect-is-the-probe and never-re-probe / never-unlink
  rules; `LocalBridgeTransport`'s missing cap / keepalive / `retry:` named
  explicitly; `enabled` and `host` keys dropped from `events.bridge`;
  `rescan_s` added; learning-test gate confirmed satisfied; superseded
  2026-08-25 and 2026-08-26 confidence assessments removed.
- **2026-09-03 — pre-implementation review, second pass.** Six spec gaps
  closed (see § Resolved Decisions, entries marked "review"): `SseBridge`
  object with `.url`/`.close()` so the enumerated tests have a handle;
  register → seed → drain order on SSE connect; `producer_pid` omitted, not
  `null`, on pid-less seed frames; route table as FEAT-3321's mount point;
  `EADDRINUSE` and Ctrl-C handling with exit codes; `textContent`-only page.
  Also: `retry: 2000` fixed, stale-socket debug log made once-per-path via
  a seen-set, `HOST_COMPATIBILITY.md` sidecar ref corrected from `:99` to
  `:107`. Tests and acceptance criteria extended to match.
- **2026-09-03 — pre-implementation review, third pass.** Verified every
  cited line against the live tree (all hold). Closed: per-path backoff on
  connect-then-immediate-EOF (producer at `max_clients`); `base`/`loops_dir`
  kwargs on `SseBridge` so seed tests avoid the repo's own state dirs; seed
  fixtures must dodge `_reconcile_stale_running`; `301` from `/{token}` to
  `/{token}/` and a `location.pathname`-derived SSE URL; seed frames carry
  both `pid` and `producer_pid`; seed-then-live duplicate-not-loss contract;
  `test_reexported_from_config_package` for `BridgeEventsConfig` (the issue
  wrongly said no test convention exists); `keepalive_s`/`rescan_s` schema
  type `number`; `EADDRINUSE` test throwaway must `listen()`. Merged-queue
  relay kept, noted as an optional simplification.

## Status

**Open** | Created: 2026-08-26 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-09-03T22:33:38 - `c4598621-fc70-4771-8b85-912ca5add2cd.jsonl`
- `/ll:confidence-check` - 2026-09-03T22:07:57 - `a295750d-9358-46ca-aab5-a1817177b579.jsonl`
- `/ll:confidence-check` - 2026-09-03T21:26:10 - `242e594e-c4d8-419b-854d-4291b014ff22.jsonl`
- `/ll:reconcile-issue` - 2026-09-03T21:21:08 - `a65ff5c9-09a4-4101-a67e-cc592584f289.jsonl`
- `/ll:wire-issue` - 2026-09-03T05:12:02 - `ca5d5b5d-2640-4a8f-b9c1-7d66de090028.jsonl`
- `/ll:refine-issue` - 2026-09-03T04:53:23 - `ee893e9d-d66e-40e3-ac8c-32f272137cf4.jsonl`
- `/ll:confidence-check` - 2026-08-26T15:05:26 - `527f3505-6fa7-4a25-937c-558cd9f06642.jsonl`
- `/ll:confidence-check` - 2026-08-26T03:42:55 - `2361c366-3751-4d40-b3d8-0d881c047601.jsonl`
- `/ll:wire-issue` - 2026-08-26T03:35:40 - `ad3eb4f0-b35e-4777-be61-e91603e9fcf0.jsonl`
- `/ll:refine-issue` - 2026-08-26T03:22:33 - `39df27ac-4529-446c-ad77-2dd45a63f9c4.jsonl`
- `/ll:format-issue` - 2026-08-26T03:13:36 - `07e3e6d6-b489-4e89-8655-3bde4b1da576.jsonl`
- `/ll:capture-issue` - 2026-08-26T03:09:09 - `eadc481c-e910-429b-9281-ccfbd253d4a9.jsonl`
