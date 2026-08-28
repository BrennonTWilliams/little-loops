---
id: ENH-3351
title: 'Add `ll-loop run --serve`: a Level-3 loopback SSE bridge for live FSM dashboards'
type: ENH
priority: P2
status: done
completed_at: '2026-08-28T20:35:20Z'
discovered_date: '2026-08-28'
relates_to:
- ENH-3307
- ENH-3306
labels:
- artifact
- fsm
- htmx
unproven_mechanism: false
learning_tests_required:
- htmx
- http.server
confidence_score: 90
outcome_confidence: 77
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
spike_needed: true
---

## Summary

Add an opt-in `ll-loop run --serve` mode that binds a loopback-only stdlib HTTP server
**inside the loop-running process**, streams that run's `EventBus` events to a served
dashboard page over SSE, and accepts `artifact_interaction` POSTs back into the running
`FSMExecutor` via an inbound queue. This is the first implementation of **Level 3
(host-owned)** in
[`docs/reference/ARTIFACT_CONTROL_LEVELS.md`](../../docs/reference/ARTIFACT_CONTROL_LEVELS.md),
whose render-target table currently has no Level-3 row at all. The client half uses
htmx 4.0 (`hx-sse` + native morph swaps + `<hx-partial>`), vendored as package data
and inlined into the page the same way `sql.js` already is.

**Architecture decision (resolves the process-ownership contradiction found in
review):** the bridge lives in the loop process, wired at the `PersistentExecutor`
construction site in `cli/loop/run.py`. It does **not** live in `ll-artifact
dashboard` — `cmd_dashboard` runs as a separate CLI process with no live `EventBus`
or `FSMExecutor` in it, and no cross-process channel exists (see Codebase Research
Findings). A standalone-process bridge would require designing *two* new
cross-process mechanisms (event tailing outbound, interaction delivery inbound) and
is explicitly out of scope.

The `ll-artifact dashboard` CLI surface is **unchanged** by this issue. The default
`file://` output path is unchanged and stays htmx-free.

## Current Behavior

`ll-artifact` is offline and single-file by construction:

- `cmd_dashboard` (`scripts/little_loops/cli/artifact/dashboard.py`) builds a filtered,
  ENH-075-redacted snapshot of `.ll/history.db`, gzip+base64-embeds it beside an
  inlined `sql.js`, and writes one HTML file that "runs arbitrary read-only SQL over
  `file://` with no network access". Its flags are `--tables`, `--since`, `--local`,
  `--db`, `-o/--output`. There is no server mode anywhere in the package.
- `cmd_render` (`cli/artifact/render.py`) is a deterministic `template + data.json ->
  artifact` Jinja stamp with no runtime at all.
- `cmd_policy_builder` (`cli/artifact/policy_builder.py`) ships a self-contained page
  whose logic is vanilla JS (`templates/policy_builder_core.mjs`), gated by
  `scripts/tests/test_policy_builder_node_gate.py`.

Every shipped render target is **Level 1 (notify)**. The `ARTIFACT_CONTROL_LEVELS.md`
render-target table lists exactly two rows (`html-anything.yaml` dashboards, ENH-3306's
`ui://` resources), both Level 1; Level 3 is described as "reserved for a future SSE
bridge / queue path" with no implementation.

The event plumbing is send-only in both directions that matter:

- `EventBus.emit()` (`scripts/little_loops/events.py:117`) fans out to `Transport` sinks
  (`scripts/little_loops/transport.py`). Every sink — `JsonlTransport`,
  `UnixSocketTransport`, `OTelTransport`, `WebhookTransport` — is outbound only;
  `UnixSocketTransport._client_loop()` drains an outbound queue and never reads bytes
  back from `client.conn`.
- `FSMExecutor.run()` (`scripts/little_loops/fsm/executor.py`) consumes only
  self-produced input (action results, evaluator verdicts, `SignalDetector` in-band
  signals). There is no inbound channel through which an external actor injects an event.

Consequence: a live loop run's state is only visible by re-running the exporter and
reloading the file, which destroys scroll position, open `<details>`, and any SQL the
user had typed into the query box.

**Also broken today (in scope as a cleanup step):** `.ll/ll-goals.md:19` cites two
exploration docs that do not exist on disk —
`docs/explorations/htmx-artifacts-exploration.md` and
`docs/explorations/2026-07-12-htmx-fsm-dashboard-event-bus-capability-assessment.md`.
There is no `docs/explorations/` directory and never was; the htmx research now lives
in this issue. **Resolution: drop the two citations** (do not attempt to restore docs
that never existed).

## Expected Behavior

`ll-loop run <loop> --serve [--port N]` binds `127.0.0.1` (loopback only, never
`0.0.0.0`), prints a tokenized URL, and serves a dashboard page with a live region
wired to an SSE endpoint. While the loop runs, the page updates in place: state badge,
iteration counter, and log tail refresh from streamed events **without losing scroll
position, open `<details>`, or in-progress query-box text**.

The page declares Level 3 and may POST an `artifact_interaction` event to the bridge;
the bridge hands it to the executor's inbound channel unchanged (Prohibition 2 in
`ARTIFACT_CONTROL_LEVELS.md`) and never consumes it itself. The executor's handling of
drained events is specified below (Proposed Solution §2) — in this issue it records
and re-emits them; FSM routing semantics are a future issue.

**Lifecycle:** the server lives exactly as long as the run. When the loop reaches a
terminal state (or the user hits Ctrl-C), the bridge emits a final `run_complete` SSE
frame, `close()` shuts the HTTP server down, and `cmd_run` returns its normal exit
code. The already-rendered page DOM persists in the browser for post-run inspection;
its SSE connection simply ends.

**Hardening:** all endpoints sit under an unguessable per-run URL token, and the
server validates the `Host` header — see Proposed Solution §1. Loopback binding alone
does not stop a malicious webpage in the user's own browser from firing drive-by
`POST http://127.0.0.1:<port>/...` requests, nor DNS-rebinding tricks.

`ARTIFACT_CONTROL_LEVELS.md` gains its first Level-3 render-target row. `ll-loop run`
without `--serve`, and all of `ll-artifact`, behave byte-for-byte as today.

## Motivation

Three things line up:

1. **`.ll/ll-goals.md:19`** names making automation state legible as an active goal —
   "artifact templates, dashboards, and next-action recommendations that make automation
   state legible."
2. **ENH-3307 deliberately left the mechanism unbuilt.** It wrote the contract first
   precisely so the first transport would not define it by accident. The contract exists;
   nothing has claimed the Level-3 row. Building it now is the intended sequel, and doing
   it *without* the contract in hand was the failure mode ENH-3307 was written to prevent.
3. **htmx 4.0 (released 2026-08-28) supplies the missing client half.** Specifically:
   - **`hx-sse`** replaces a hand-rolled `EventSource` + DOM-patch layer.
   - **Native morphing swaps** are the actual win — they preserve focus, scroll, and
     input state across per-iteration updates, which is exactly what regenerate-and-reload
     destroys today.
   - **`<hx-partial>`** lets one bridge payload update several regions as explicit OOB
     targets instead of a bespoke multi-region patcher.
   - **`htmax.js`** (htmx + extensions, one file) matches the inline-everything
     constraint — same treatment as the already-inlined `sql.js`.
   - 4.0's **explicit `:inherited`** suits *generated* HTML: `templatize` emits
     per-element attributes with no accidental inheritance leaking into children.

Note honestly what 4.0 does **not** fix: swapping XHR for `fetch()` does not relax the
`file://` constraint — `fetch` from a `file://` origin is blocked just as hard. htmx pays
off only *behind* the local server, which is why `--serve` is the unit of work.

## Proposed Solution

### 1. Transport: `LocalBridgeTransport`

Add a `Transport` sink in `scripts/little_loops/transport.py` alongside
`UnixSocketTransport`, following its `_SocketClient` fan-out shape. It differs in being
**bidirectional**: outbound events serialize as SSE frames; an inbound POST handler
enqueues `artifact_interaction` onto a `queue.Queue` the executor drains.

It implements the `Transport` protocol exactly: **`send(event)` and `close()`** —
`EventBus.emit()` calls `transport.send(event)`; there is no `emit()` method on sinks.

Endpoints, all under a per-run token prefix generated with `secrets.token_urlsafe(16)`:

- `GET /{token}/` — the dashboard page (serve-mode render, see §3)
- `GET /{token}/events` — `text/event-stream`; per-client outbound queue, drop-on-full,
  same back-pressure shape as `UnixSocketTransport`
- `POST /{token}/interaction` — enqueue the JSON body onto `inbound` unchanged

Requests with a missing/wrong token get `404`. Requests whose `Host` header is not
`127.0.0.1:<port>` or `localhost:<port>` get `403` (DNS-rebinding guard). Both are
asserted in tests, not just intended.

`send()` converts an event dict to an SSE frame via a constructor-injected
`render_fragment: Callable[[dict[str, Any]], str | None] | None`. The callable returns
an HTML fragment (`<hx-partial>` OOB regions for the state badge / iteration counter /
log tail) or `None` to skip the event; when the callable itself is `None` (default),
events are forwarded as raw JSON `data:` frames — the form the transport unit tests
exercise. The htmx-fragment renderer is *supplied by the wiring site*, keeping Jinja
out of `transport.py` (see §3).

**Shutdown mechanics (specified, not left to implementation):**
`ThreadingHTTPServer` sets `daemon_threads = True`, and stdlib `server_close()`
skips joining daemon threads — so teardown never hangs, but nothing flushes SSE
clients either: a naive `close()` would drop the promised final frame and leak
handler threads blocked on `queue.get()` in tests. Therefore `close()` pushes a
final `run_complete` sentinel frame into every per-client queue **before**
calling `shutdown()`/`server_close()`; each SSE handler loop reads its queue
with `get(timeout=...)` and exits when it sees the sentinel. Handlers catch
`BrokenPipeError`/`ConnectionResetError` on write and deregister the dead
client's queue. This one mechanism delivers the final `run_complete` frame,
prevents handler-thread leaks, and prunes dead clients; the serve-lifecycle
test asserts handler threads are gone after `close()`.

Use `http.server.ThreadingHTTPServer` from the stdlib. Do **not** add a web framework:
the only HTTP machinery in the package today is `uvicorn`, imported lazily inside
`mcp_server/server.py:298` and optional; `.claude/CLAUDE.md` requires preferring stdlib
over a new pin.

htmx ships as **vendored package data** (`assets/vendor/htmx/htmax.js`), not a Python
dependency — registered in `package_data.py` with a `PROVENANCE.md` sibling, following
the `sql.js` convention (`assets/vendor/<pkg>/`, see Codebase Research Findings).

No `wire_transports`/`_TRANSPORT_REGISTRY` change and no `ll-config.json` key:
`--serve` is flag-only, and `cli/loop/run.py` constructs the transport directly and
registers it with `executor.event_bus.add_transport(...)` after the existing
`wire_transports` call. (Config-driven wiring can be a follow-up if wanted.)

### 2. Executor inbound channel

`FSMExecutor` gains an optional keyword-only `inbound: queue.Queue[dict[str, Any]] |
None = None` constructor parameter, drained non-blockingly at the top of each `run()`
iteration (right after the `_shutdown_requested` check). `None` (the default) preserves
today's behavior exactly — additive; every existing caller is unaffected.
`PersistentExecutor` already forwards `**executor_kwargs`, so
`PersistentExecutor(..., inbound=q)` needs zero changes there.

**What the executor does with a drained event (v1 contract — record and re-emit, no
FSM routing):** for each drained dict, `_drain_inbound()`

1. re-emits it through `self._emit("artifact_interaction", event)` — so it reaches
   `event_callback` → `PersistentExecutor._handle_event` → `EventBus` → persistence
   (`history.db`) and echoes back out over SSE as a delivery ack. **This makes the
   executor the first real `artifact_interaction` emitter**, which resolves
   EVENT-SCHEMA.md's "no emitter until a mechanism ships" reservation (see
   Documentation).
2. appends it to a bounded `self.inbound_events: collections.deque[dict[str, Any]]`
   (`maxlen=100`) so future issues can build routing/guard semantics on top without
   another executor change.

Routing an interaction to FSM transitions/guards is explicitly **not** in this issue.

`_execute_sub_loop`'s child-executor construction (`fsm/executor.py:1026`) **must
forward `inbound=self.inbound`** so interactions still arrive while the FSM is inside
a `loop:` sub-state — one keyword argument, decided (not optional) per review.

### 3. Page and fragment renderer

The dashboard template grows a serve-only block (Jinja-conditional, absent from the
`file://` render) carrying the inlined `htmax.js`, an `hx-sse` connection to
`/{token}/events`, and morph-swap targets for the live regions.

`cli/artifact/dashboard.py` is refactored (behavior-preserving) to expose a reusable
`build_dashboard_html(..., serve_context: ServeContext | None = None)` helper so the
loop process can render the same page with the serve block enabled; `cmd_dashboard`
keeps calling it with `serve_context=None`. It also gains
`render_live_fragment(event: dict) -> str | None` — the `render_fragment` callable
passed to `LocalBridgeTransport` — backed by a new
`templates/dashboard.llat/partials.html.j2` holding the `<hx-partial>` region
templates. This renderer is real code with its own tests; it is not folded into the
transport.

**Snapshot vs live data (stated so nobody files it as a bug):** the served page still
embeds the gzip'd `history.db` snapshot built at server start; the sql.js query box
queries that startup snapshot, while the badge/counter/log-tail regions update live
from SSE. Live-refreshing the embedded snapshot is out of scope.

**Missing/empty `history.db` (first-ever run):** `cmd_dashboard` returns 1 when
`.ll/history.db` does not exist (`dashboard.py:150`). `--serve` must **not**
inherit that failure: when the db is missing at server start,
`build_dashboard_html` renders the page with an empty snapshot — the live SSE
regions are the point of serve mode; the query box is a bonus — rather than
failing the run or silently dropping the flag. The `cmd_dashboard` CLI path
keeps its existing missing-db error behavior unchanged.

**Render determinism (gzip mtime):** `cmd_dashboard` embeds the snapshot via
`gzip.compress()` (`dashboard.py:193`), which stamps wall-clock mtime into the
gzip header — two renders of identical input already differ byte-wise today. As
part of the refactor, pass `mtime=0` so output becomes reproducible (a one-time
byte change to the shipped render; the embedded db content is unchanged).
Consequence for testing: "byte-identical pre/post refactor" is a **dev-time
verification** (render fixed input with old vs new code, mtime pinned), not a
persistent CI test — the enduring regression tests instead assert (a) zero
`htmx`/`hx-` occurrences in default output and (b) `cmd_dashboard` delegates to
`build_dashboard_html(serve_context=None)`.

### 4. CLI wiring

`--serve` / `--port` are added to the `run` subparser
(`cli/loop/__init__.py:135`). In `cmd_run` (`cli/loop/run.py`), under `--serve`:
construct the inbound `queue.Queue`, `LocalBridgeTransport(port=args.port or 0,
inbound=q, render_fragment=render_live_fragment)` (lazy import of the dashboard
helpers), pass `inbound=q` into the `PersistentExecutor(...)` construction at
`run.py:579`, register the transport on `executor.event_bus` next to the existing
`wire_transports(...)` call at `run.py:599`, print `bridge.url`, and `close()` in the
run's existing cleanup/`finally` path so `cmd_run` still returns its normal `int`.

### Alternatives considered

- **`ll-artifact dashboard --serve` (the original shape of this issue) — rejected.**
  `cmd_dashboard` is a separate process from any loop run; it has no live `EventBus`
  or executor, and no cross-process channel exists (Codebase Research Findings).
  A standalone bridge would need cross-process event tailing *and* a cross-process
  inbound path — two new mechanisms instead of zero.
- **Reuse `UnixSocketTransport` + a `socat`-style shim — rejected.** A browser cannot
  open a unix socket, so a translating HTTP process is required regardless, and that
  process is the thing being built here. Building it directly is strictly less
  machinery.

## API/Interface

```python
# scripts/little_loops/transport.py
class LocalBridgeTransport:
    """Loopback-only SSE bridge (ARTIFACT_CONTROL_LEVELS Level 3)."""

    def __init__(
        self,
        port: int = 0,
        inbound: queue.Queue[dict[str, Any]] | None = None,
        render_fragment: Callable[[dict[str, Any]], str | None] | None = None,
        page_html: str | None = None,
    ) -> None: ...
    def send(self, event: dict[str, Any]) -> None: ...   # Transport protocol
    def close(self) -> None: ...
    @property
    def url(self) -> str: ...   # http://127.0.0.1:<bound-port>/<token>/

# scripts/little_loops/fsm/executor.py
class FSMExecutor:
    def __init__(self, ..., inbound: queue.Queue[dict[str, Any]] | None = None) -> None: ...
```

```
ll-loop run <loop> --serve [--port N]
  --serve   Bind a loopback HTTP + SSE bridge for this run and serve a live
            dashboard page. Declares Level 3 (host-owned). Server lifetime ==
            run lifetime. Without --serve, behavior is byte-identical to today.
  --port    TCP port on 127.0.0.1 (default: 0 = ephemeral, printed on start).
```

## Program Design

### Types

- `LocalBridgeTransport.inbound: queue.Queue[dict[str, Any]] | None`
- `FSMExecutor.inbound: queue.Queue[dict[str, Any]] | None`
- `FSMExecutor.inbound_events: collections.deque[dict[str, Any]]` (maxlen=100)

### Signatures

- `LocalBridgeTransport.__init__(port: int = 0, inbound: queue.Queue | None = None, render_fragment: Callable[[dict], str | None] | None = None, page_html: str | None = None) -> None`
- `LocalBridgeTransport.send(event: dict[str, Any]) -> None`
- `LocalBridgeTransport.close() -> None`
- `LocalBridgeTransport.url -> str`
- `FSMExecutor._drain_inbound() -> None` — drains, re-emits, records; returns nothing
- `render_live_fragment(event: dict[str, Any]) -> str | None` — in `cli/artifact/dashboard.py`
- `build_dashboard_html(...)` — extracted from `cmd_dashboard`, behavior-preserving

### Call Path

Outbound: `FSMExecutor._emit` -> `event_callback` -> `PersistentExecutor._handle_event`
-> `EventBus.emit` -> `LocalBridgeTransport.send` -> `render_fragment` -> SSE frame ->
`hx-sse` morph swap.

Inbound: page POST `/{token}/interaction` -> `LocalBridgeTransport` handler ->
`queue.Queue` -> `FSMExecutor._drain_inbound` (top of each `run()` iteration) ->
re-emit as `artifact_interaction` (persisted + SSE-echoed) + append to
`inbound_events`.

Wiring: `cli/loop/run.py` under `--serve` — construct queue + transport, pass
`inbound=` into `PersistentExecutor(...)` (run.py:579), `executor.event_bus
.add_transport(bridge)` beside `wire_transports` (run.py:599), `close()` in cleanup.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Transport protocol conformance**: `Transport` (`scripts/little_loops/transport.py:67-83`, `@runtime_checkable`) requires `send(self, event: dict[str, Any]) -> None` and `close(self) -> None`, not `emit()`. `EventBus.emit()` (`scripts/little_loops/events.py:117-138`) dispatches by calling `transport.send(event)` on every registered sink, never `transport.emit(...)`. _(Resolved in this revision: the API/Interface and Signatures sections now specify `send()`/`close()`.)_
- **`FSMExecutor._emit` anchor**: `scripts/little_loops/fsm/executor.py:3340` — builds `{"event": ..., "ts": ..., "run_id": ..., "loop": ..., **data}` and calls `self.event_callback(...)`; it never touches `EventBus` directly. For persisted runs, `event_callback=self._handle_event` (`fsm/persistence.py:955`), and `PersistentExecutor._handle_event()` (`fsm/persistence.py:998`) is what eventually calls `self.event_bus.emit(event)` (line 1084, and the resume-path variant at line 1323) — `EventBus` lives on `PersistentExecutor`, not on the inner `FSMExecutor`.
- **`FSMExecutor.__init__` signature** (`fsm/executor.py:194-208`): every parameter after `fsm` is keyword-with-default; no `**kwargs`. A new `inbound: queue.Queue[dict[str, Any]] | None = None` keyword-only param is safe to add — confirmed against all three production construction sites (see Integration Map → Dependent Files), none of which pass positional args past `fsm`/`child_fsm`.
- **`run()` loop top**: `while True:` at `fsm/executor.py:500`, immediately followed by the `self._shutdown_requested` check (line 502-503). No `queue.Queue` import or usage exists anywhere in `fsm/executor.py` today (confirmed by unfiltered search) — a `_drain_inbound()` call would be net-new, not a refactor of an existing poll, and would slot in right after the shutdown check.
- **Non-blocking full-drain precedent**: `WebhookTransport._flush()` (`transport.py:701-709`) is the codebase's existing "drain everything queued right now, non-blocking, no background consumer thread" shape (`while True: try: events.append(q.get_nowait()) except Empty: break`) — lives in the same module `LocalBridgeTransport` would be added to, and is the closest model for `FSMExecutor._drain_inbound()`.
- **`cmd_dashboard` has no live-process hook to any `EventBus`/`FSMExecutor`**: `cmd_dashboard()` (`cli/artifact/dashboard.py:127-275`) has no call anywhere to `EventBus`, `FSMExecutor`, `PersistentExecutor`, or `wire_transports()` — it is a batch reader of `.ll/history.db` via `build_snapshot_db()`. All four production `wire_transports()` call sites (`cli/loop/run.py:599`, `cli/loop/lifecycle.py:741`, `cli/parallel.py:322`, `cli/sprint/run.py:801`) construct/obtain their own `EventBus` and wire it before running — none passes that `EventBus` or executor to `cmd_dashboard`, and `cmd_dashboard` is invoked as a separate CLI process from any of them. `EventBus.emit()` runs synchronously in the emitting process's own thread — no existing mechanism threads a live in-process `EventBus` across process boundaries into a separately-invoked CLI. _(Resolved in this revision: the bridge now lives in the loop-run process via `ll-loop run --serve`; no cross-process EventBus wiring is attempted. The `unproven_mechanism` flag remains for htmx 4.0 itself.)_

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` — add `LocalBridgeTransport` (`send`/`close`, token + Host validation, `render_fragment` injection). No `wire_transports`/`_TRANSPORT_REGISTRY` change — flag-constructed.
- `scripts/little_loops/fsm/executor.py` — optional `inbound` queue, `_drain_inbound` (re-emit + record contract), `inbound_events` deque, and forward `inbound=self.inbound` in `_execute_sub_loop`'s child construction (line 1026).
- `scripts/little_loops/cli/loop/__init__.py` — `--serve` / `--port` on the `run` subparser (line 135).
- `scripts/little_loops/cli/loop/run.py` — construct queue + bridge under `--serve`; `inbound=` into `PersistentExecutor(...)` (:579); `add_transport` beside `wire_transports` (:599); print URL; `close()` in cleanup.
- `scripts/little_loops/cli/artifact/dashboard.py` — behavior-preserving refactor: extract `build_dashboard_html(...)` with a `serve_context` hook; add `render_live_fragment()`. **No CLI flag changes here.**
- `scripts/little_loops/templates/dashboard.llat/template.html.j2` — serve-only htmx block
- `scripts/little_loops/templates/dashboard.llat/partials.html.j2` — new `<hx-partial>` region templates (create)
- `scripts/little_loops/package_data.py` — register `assets/vendor/htmx/htmax.js` (+ `PROVENANCE.md`)
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — first Level-3 render-target row
- `docs/reference/CLI.md` — `--serve` / `--port` under `ll-loop run` (not under `ll-artifact dashboard`)
- `.ll/ll-goals.md` — drop the two dangling `docs/explorations/` citations

### Files to Create
- `scripts/little_loops/assets/vendor/htmx/htmax.js` — vendored htmx 4.0 bundle, version pinned in a header comment
- `scripts/little_loops/assets/vendor/htmx/PROVENANCE.md` — version, source URL, license, per-file SHA-256, update procedure (per the `sql.js` convention)
- `scripts/little_loops/templates/dashboard.llat/partials.html.j2` — live-region fragments

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — add `LocalBridgeTransport` to the `little_loops.transport` import block (lines 57-64) and the `# transport` section of `__all__` (lines 109-117). Every other transport class (`JsonlTransport`, `OTelTransport`, `UnixSocketTransport`, `WebhookTransport`) is re-exported here; `LocalBridgeTransport` is currently the only one that would be missing from this list if not added.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/events.py` — `EventBus.add_transport` / `Transport` protocol conformance
- Every current `FSMExecutor(...)` construction site — unaffected (`inbound` defaults to `None`), but grep to confirm no positional-arg breakage
- Confirmed exact sites (all keyword-only past `fsm`/`child_fsm`, none at risk of positional collision): `fsm/executor.py:1026` (child sub-loop executor, `event_callback=_sub_event_callback`), `fsm/persistence.py:953` (inside `PersistentExecutor.__init__`, `event_callback=self._handle_event`, forwards `**executor_kwargs`), `cli/loop/testing.py:260` (simulation mode, `event_callback=simulation_callback`)

_Wiring pass added by `/ll:wire-issue`:_
- **Full-repo census (523 `FSMExecutor(` occurrences across 45 files, not just the 3 production sites)**: no call site anywhere passes a second positional argument — every argument after `fsm`/`child_fsm`/`parent_fsm` is keyword. No positional-collision risk anywhere in the tree, extending the issue's own 3-site check.
- `scripts/little_loops/fsm/persistence.py:953-960` (`PersistentExecutor.__init__`) already accepts `**executor_kwargs: Any` and forwards it verbatim into its `FSMExecutor(...)` call — `PersistentExecutor(..., inbound=queue)` works with **zero code changes** at this site beyond what already exists today; scope-reducing, not scope-adding.
- `scripts/little_loops/fsm/executor.py:1026` (`_execute_sub_loop`'s child `FSMExecutor` construction) — **decided: forward `inbound=self.inbound`** so `artifact_interaction` delivery keeps working while the FSM is inside a `loop:` sub-state. One keyword argument; no longer left open.
- `scripts/little_loops/cli/loop/run.py` (`cmd_run`) returns an `int` and already has a cleanup path for the executor; the bridge's `close()` joins that path so `--serve` never changes the return-code contract. _(The previous revision's note about `cmd_dashboard`'s dispatcher is obsolete — `ll-artifact dashboard` is no longer touched.)_

### Similar Patterns
- `UnixSocketTransport` (`transport.py:119`) — client fan-out and per-client outbound queue lifecycle; closest precedent
- `mcp_server/server.py:298` — precedent for lazily-imported, optional HTTP machinery

### Tests
- `scripts/tests/test_transport.py` — bind/send/close; loopback-only bind assertion; port-in-use handling; **wrong/missing token → 404; bad `Host` header → 403**; raw-JSON SSE frames when `render_fragment is None`; inbound POST lands on the queue unchanged; **`close()` delivers the final `run_complete` sentinel frame to a connected SSE client and its handler thread exits (no thread leak — assert via thread count/join, not sleep)**; disconnected client's queue is deregistered after a write failure
- `scripts/tests/test_fsm_executor.py` — `inbound=None` is byte-identical to today; queued event is re-emitted as `artifact_interaction` and appended to `inbound_events`; sub-loop child receives the parent's `inbound`
- `scripts/tests/test_feat3304_artifact_dashboard.py` — default `ll-artifact dashboard` output has no `htmx`/`hx-`, and `cmd_dashboard` delegates to `build_dashboard_html(serve_context=None)` (regression guard on the `file://` path and on the extraction). Byte-identity across the refactor is verified **at dev time** with fixed input and gzip mtime pinned — not as a persistent test, since `gzip.compress()`'s mtime header makes repeated renders non-identical by construction (fixed in this issue via `mtime=0`, see Proposed Solution §3)
- New: `--serve` with missing `history.db` — page renders with an empty snapshot and the run proceeds; `cmd_dashboard`'s missing-db `return 1` is unchanged
- New: `render_live_fragment` unit tests — event dict in, `<hx-partial>` fragment (or `None`) out
- New: serve-lifecycle test — bridge `close()` fires when the run reaches a terminal state, SSE handler threads are gone afterwards, and `cmd_run` still returns its normal exit code

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_reference_docs.py` — `DOC_STRINGS_PRESENT` is a pytest-enforced substring gate, not free prose: any rewrite of `docs/reference/ARTIFACT_CONTROL_LEVELS.md`'s Level-3 row must retain the literal substrings `"notify"`, `"ask-to-run-prompt"`, `"host-owned"`, `"artifact_interaction"`, `"_meta.ui.visibility"` (lines 204-208), and any rewrite of `docs/ARCHITECTURE.md`'s `## Artifact Control Layer` section must retain that literal heading text (line 212). No test-file edit needed — this is a constraint on the wording of the doc edits already planned, not new test code.
- `scripts/tests/test_feat3304_artifact_dashboard.py::TestVendoredSqlJs` (line 621, `test_provenance_records_version_hashes_license_and_procedure`) is the precedent for vendored-asset testing: it is a **feature-owned, hard-coded** test class asserting `PROVENANCE.md` content (version string, source URL, license, per-file SHA-256 digest) — there is no repo-wide `ll-verify-package-data`/`test_package_data_manifest.py` check that does this generically. `assets/vendor/htmx/htmax.js` needs an equivalent bespoke `TestVendoredHtmax`-style class (in this file or a new `test_enh3351_*` file) asserting its own `PROVENANCE.md`'s version/source/license/hash content — `test_package_data_manifest.py`'s generic `PACKAGE_DATA_ASSETS` parametrization auto-covers *accessibility* of the new tuple with zero edits, but not provenance-content correctness.
- Closest stdlib HTTP-bind test precedent: `scripts/tests/test_flux_image_generator.py:248-297` (`_StubFluxHandler` + `flux_stub` fixture) — `http.server.HTTPServer(("127.0.0.1", 0), Handler)` bound in a `daemon=True` background thread via `serve_forever`, torn down with `server.shutdown()` + `server.server_close()` in a fixture `finally`. Closer fit than the ASGI `TestClient` pattern in `test_enh_3173_mcp_http_bind.py`/`test_feat_3143_mcp_http_transport.py`, since those never open a real socket and `LocalBridgeTransport` needs a real bound loopback port (mirrors the issue's own `test_transport.py::TestUnixSocketTransport` model).
- No SSE (`text/event-stream`) response-parsing precedent exists anywhere in this codebase (confirmed by repo-wide search — the only hits are `Accept:` header strings in MCP HTTP tests, never an actual streamed body). The `--serve` SSE test needs new test infrastructure — a raw `urllib.request`/`http.client` streaming read against the bound server — not an extension of an existing helper.

### Documentation
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md`, `docs/reference/CLI.md` (`ll-loop run`), `docs/ARCHITECTURE.md` (`## Artifact Control Layer`)

_Wiring pass added by `/ll:wire-issue` (updated in this revision):_
- `docs/reference/API.md` — three anchors describing the exact symbols being changed, none currently mentioning them: the `little_loops.transport` module-table row (line 99, lists only `JsonlTransport`/`UnixSocketTransport`/`OTelTransport`, omitting both `WebhookTransport` and the new `LocalBridgeTransport`); the `## little_loops.transport` per-class code-example section (line 10271, where every other transport class gets a runnable snippet); and `little_loops.fsm.executor`'s module-table row (line 5474) and `### little_loops.fsm.executor` section (line 6058), neither mentioning the new `inbound`/`_drain_inbound`.
- `docs/reference/EVENT-SCHEMA.md` — **resolved**: `_drain_inbound`'s re-emission makes `FSMExecutor` a real `artifact_interaction` emitter, so (a) update `## Reserved Event Names` (lines 1367-1377) — the "no schema file and no emitter until a mechanism ships" language becomes false — and (b) add the `artifact_interaction` row to the `## Quick Reference` Event table, satisfying ENH-3307's "until an executor actually emits" deferral condition.
- `docs/ARCHITECTURE.md:902-905` — the specific stale sentence: "`FSMExecutor.run()`... is the sole routing authority today... no artifact type can currently route an interaction back into it." This factual claim becomes false once `--serve` ships and needs updating, not just the section's general presence.
- `docs/reference/CLI.md` — document `--serve`/`--port` under **`ll-loop run`**. The `ll-artifact dashboard` section (including its Exit codes note at :4588) is **unchanged** — that command gains no flags in this revision.

### Configuration
- N/A — `--serve` is flag-only on `ll-loop run`; no `ll-config.json` key and no `wire_transports` registry entry in this issue (config-driven wiring is a possible follow-up)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Vendored-asset registration convention**: a vendored asset is (1) placed under `assets/vendor/<pkg>/`, (2) given a `PROVENANCE.md` sibling (version, source, hashes, license, update procedure — see `assets/vendor/sql.js/PROVENANCE.md`), (3) registered as one tuple per file in `PACKAGE_DATA_ASSETS` (`package_data.py:76-86`) — no directory-glob form, per that file's own comment — and (4) read at runtime via a small `_packaged_path()`/`importlib.resources` helper local to the consuming CLI module (`dashboard.py:46-54`), not a shared generic loader. A new entry in `PACKAGE_DATA_ASSETS` is auto-covered by `scripts/tests/test_package_data_manifest.py`'s parametrized `test_individual_asset_accessible` — no test edit needed beyond the manifest tuple itself.
- **`ll-artifact` subcommand module convention**: each subcommand exports `add_<name>_parser(subparsers)` + `cmd_<name>(args, logger)` in its own module (`cli/artifact/__init__.py:22-27` states this explicitly, citing FEAT-3036). _(This revision no longer adds flags to `ll-artifact dashboard`; the convention still constrains the `dashboard.py` refactor — keep `add_dashboard_parser`/`cmd_dashboard` exports intact.)_
- **Only existing `--port` flag in the CLI**: `mcp_server/__init__.py:106-107` — `type=int, default=None`, letting the caller distinguish "not given" from an explicit value in a flag > config > code-default precedence chain (exercised by `test_enh_3173_mcp_http_bind.py::test_main_mcp_host_flag_wins_over_config`). No existing `--host`/`--port` flag pair enforces a no-override loopback-only bind — see Tests note below.
- **Jinja conditional-block precedent is content-presence-gated, not render-mode-gated**: the only existing `[[% if %]]` block under `templates/dashboard.llat/template.html.j2` (line 86-88) gates on whether `schema_version_warning` is truthy, not on a boolean "which render mode" flag. A serve-only htmx block would be the first render-mode-gated conditional in this template — no direct precedent for that specific shape, though the delimiter/environment machinery (`artifact_templates.py:259-279`, frozen per FEAT-3308) is unaffected either way.
- **Tests — loopback-only bind precedent disagreement**: two existing shapes disagree on what "loopback-only" means. `test_feat_3143_mcp_http_transport.py::test_run_http_defaults_to_loopback_not_public` only asserts the function's *default* host value is `127.0.0.1` via `inspect.signature`, never opening a real socket. `mcp_server/server.py`'s actual runtime behavior (Shape B, exercised by `test_enh_3173_mcp_http_bind.py`) explicitly *permits* an explicit non-loopback `--host` override with a compensating allow-list widening. Neither existing test enforces "this server can only ever bind loopback, with no override path at all," which is the stricter invariant this issue's own text describes (no host-override flag in its own API/Interface section) — a new test for `LocalBridgeTransport` would be the first of this stricter shape in the codebase.
- **`UnixSocketTransport` test shape** (`test_transport.py`, class `TestUnixSocketTransport`, lines 393-925): every test follows `bind -> exercise -> assert -> close()` in a `try/finally`; uses a `_wait_until(pred, timeout, interval)` polling helper (lines 91-103) instead of fixed `time.sleep()` for anything depending on the background accept thread. Coverage is one narrowly-named test method per behavior (protocol conformance, bind, stale-file reclaim, permissions, fan-out, disconnect isolation, max-clients rejection, queue-full drop, `on_connect` seeding, close timing) rather than one large integration test — the shape `LocalBridgeTransport`'s tests in the same file should follow, minus the `AF_UNIX`-specific bits (`short_tmp_path`, stale-path reclaim, `0o600` permissions) that don't transfer to a TCP bind.

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Confirmed, no line drift**: `PersistentExecutor(...)` construction spans `cli/loop/run.py:579-590`; `wire_extensions(...)` is at `run.py:598` immediately followed by `wire_transports(executor.event_bus, _config.events)` at `run.py:599`; the `run` subparser is still at `cli/loop/__init__.py:135`.
- **`wire_transports` cannot register a pre-built transport instance**: `transport.py:758-830+` dispatches purely by transport *name* string (from `config.events.transports`) against a fixed `_TRANSPORT_REGISTRY`/if-elif chain; it has no parameter for injecting an already-constructed instance. This confirms the issue's own plan (direct `executor.event_bus.add_transport(bridge)` call beside, not through, `wire_transports`) is the only route — no `wire_transports` change is needed or possible for this.
- **`bridge.close()` is likely already covered by existing cleanup with zero new code**: `cmd_run`'s `finally:` block (`run.py:615-619`) unconditionally calls `executor.close_transports()` whenever `executor is not None`. `PersistentExecutor.close_transports()` (`fsm/persistence.py:978-980`) delegates to `EventBus.close_transports()` (`events.py:109-115`), which loops every transport in `self._transports` and calls `.close()` on each, isolating exceptions (`except Exception: logger.warning(...)`). Once `LocalBridgeTransport` is registered via `add_transport(bridge)`, its `close()` fires automatically through this existing path — on the normal `return run_foreground(...)` success path (`run.py:600-614`, which still runs `finally` before returning) and on a first Ctrl-C (which routes through `FSMExecutor.request_shutdown()` → normal return, confirmed via `register_loop_signal_handlers`, `_helpers.py:222-246`). A **second** Ctrl-C forces `sys.exit(1)` from the signal handler, raising `SystemExit`, which still unwinds through the same `finally` block. Net effect: Implementation Step 6's "close() in cleanup" is satisfied by registration alone — no explicit new `bridge.close()` call site in `cmd_run` is needed beyond `add_transport(bridge)`, contingent on confirming this in the actual signal-handler code path during implementation (the exact second-Ctrl-C force-exit body in `_helpers.py` was not fully traced).
- **`FSMExecutor.__init__` has no `*,` keyword-only separator today** (`executor.py:194-208`): all 12 existing params (`fsm, event_callback, action_runner, signal_detector, handoff_handler, loops_dir, circuit, run_model, run_effort, working_dir, compression_config, orchestration_config`) are positional-or-keyword by convention, not syntactically enforced keyword-only. Every current call site (`persistence.py:953`, `executor.py:1026`) already passes everything by keyword, so adding `inbound` the same way is safe either with or without introducing a `*,` separator — that separator is a style choice, not a correctness requirement, for this issue.

## Implementation Steps

1. Drop the two dangling `docs/explorations/` citations from `.ll/ll-goals.md`. Cheap,
   independent.
2. Vendor htmx 4.0 as package data with `PROVENANCE.md`; register in
   `PACKAGE_DATA_ASSETS`; write the `TestVendoredHtmax` provenance test. Write the
   learning tests (`learning_tests_required`) so they exercise **`hx-sse` + morph
   swaps against the actual vendored `htmax.js`** — not merely that the file loads —
   plus the `http.server` SSE-streaming shape.
3. Add `LocalBridgeTransport` (`send`/`close`, token prefix, Host validation,
   `render_fragment` injection, per-client SSE queues, sentinel-based shutdown per
   §1's shutdown mechanics) + tests. Assert loopback-only bind, 404-on-bad-token,
   403-on-bad-Host, final-frame delivery, and no handler-thread leak after `close()`.
4. Add the executor `inbound` queue, `_drain_inbound` (re-emit + `inbound_events`
   record), and `inbound=self.inbound` forwarding in `_execute_sub_loop`; prove
   `inbound=None` is a no-op.
5. Refactor `dashboard.py` into `build_dashboard_html(...)`: pin `gzip.compress`
   `mtime=0`, verify byte-identity vs the old code at dev time with fixed input,
   handle missing `history.db` in serve mode (empty snapshot), and add
   `render_live_fragment` + `partials.html.j2` + the template's serve-only htmx
   block. Persistent tests per the Tests section (no-htmx guard + delegation +
   missing-db serve behavior).
6. Wire `--serve` / `--port` into `cli/loop/__init__.py` + `cli/loop/run.py`
   (construct, register, print URL, close in cleanup).
7. Update `ARTIFACT_CONTROL_LEVELS.md` (Level-3 row), `CLI.md` (`ll-loop run`),
   `ARCHITECTURE.md` (:902-905), `EVENT-SCHEMA.md` (Reserved Event Names + Quick
   Reference row), `API.md` anchors.
8. Verify: `python -m pytest scripts/tests/` exits 0, and a live `ll-loop run --serve`
   visibly updates the page while preserving scroll and query-box text; killing the
   run shuts the server down and the page DOM survives.

### Wiring Phase (added by `/ll:wire-issue`, updated in this revision)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/__init__.py` — add `LocalBridgeTransport` to the `little_loops.transport` import block and to `__all__`'s `# transport` section, matching every other transport class.
- Forward `inbound=self.inbound` in `scripts/little_loops/fsm/executor.py:1026` (`_execute_sub_loop`'s child `FSMExecutor` construction) — decided, not optional.
- Ensure the bridge's `close()` runs in `cmd_run`'s existing cleanup path so `--serve` preserves the normal `int` return-code contract of `ll-loop run`.
- Update `docs/reference/API.md` — add `LocalBridgeTransport` to the `little_loops.transport` module-table row and give it a code example in `## little_loops.transport`; add `inbound`/`_drain_inbound` to `little_loops.fsm.executor`'s module-table row and section.
- Update `docs/reference/EVENT-SCHEMA.md` per the resolved emitter decision: fix the `## Reserved Event Names` "no emitter" language **and** add the `artifact_interaction` `## Quick Reference` row (the executor now emits it via `_drain_inbound` re-emission).
- Update `docs/ARCHITECTURE.md:902-905`'s "no artifact type can currently route an interaction back into it" sentence.
- Document `--serve`/`--port` in `docs/reference/CLI.md` under `ll-loop run`; leave the `ll-artifact dashboard` section (exit-codes note at :4588 included) untouched.
- Write a `TestVendoredHtmax`-style test class (provenance version/source/license/hash) for `assets/vendor/htmx/htmax.js`, modeled on `test_feat3304_artifact_dashboard.py::TestVendoredSqlJs` — the generic `PACKAGE_DATA_ASSETS` manifest check does not cover provenance-content correctness.
- Preserve the literal substrings `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT` asserts on (`"notify"`, `"ask-to-run-prompt"`, `"host-owned"`, `"artifact_interaction"`, `"_meta.ui.visibility"` in `ARTIFACT_CONTROL_LEVELS.md`; the `## Artifact Control Layer` heading in `ARCHITECTURE.md`) when rewriting those docs.

## Success Metrics

- `ARTIFACT_CONTROL_LEVELS.md`'s render-target table has a Level-3 row backed by shipping code.
- A page open during a live `ll-loop run --serve` updates on each iteration with scroll
  position, open `<details>`, and query-box contents intact — the state today's
  regenerate-and-reload destroys.
- A POST to the interaction endpoint with a wrong token or non-loopback `Host` header is
  rejected (404/403) — asserted in tests.
- When the run ends, the server shuts down and `ll-loop run` returns its normal exit code.
- Default `ll-artifact dashboard` output contains zero occurrences of `htmx`/`hx-`
  (persistent regression test), and the `build_dashboard_html` extraction is verified
  byte-identical at dev time with gzip mtime pinned (`mtime=0` ships, making future
  renders reproducible).
- Bridge `close()` delivers a final `run_complete` frame to connected SSE clients and
  leaves no handler threads behind — asserted in tests.
- `ll-loop run --serve` on a project with no `history.db` still serves the live page
  (empty snapshot) instead of failing the run.
- No new entry in `scripts/pyproject.toml` `dependencies`.

## Scope Boundaries

Explicitly **out of scope**:

- **Any `--serve` flag on `ll-artifact dashboard`.** The bridge requires a live
  in-process `EventBus`/executor; a standalone-process bridge (cross-process event
  tailing + cross-process inbound delivery) is a separate issue if ever wanted.
- FSM routing semantics for inbound interactions (guards/transitions reacting to
  `artifact_interaction`). This issue records and re-emits only; `inbound_events` is
  the forward slot.
- Live-refreshing the embedded sql.js snapshot; the query box queries the
  server-start snapshot.
- A config key / `wire_transports` registry entry for the bridge (flag-only for now).
- Retrofitting htmx into `policy-builder`. It is pure client-side state with no server on
  the other end; htmx replaces nothing there and would disturb its Node conformance gate.
- Retrofitting htmx into `render` / `extract` / `refresh` / `.llat` templates.
- Any non-loopback bind, authentication beyond the URL token + Host check, or TLS.
  `--serve` is a local-development affordance; if it ever needs to leave `127.0.0.1`,
  that is a separate issue with its own threat model.
- Adding an `ArtifactControlLevel` machine-readable field. `ARTIFACT_CONTROL_LEVELS.md`
  names that as a deliberate forward slot; this issue satisfies the *binding* requirement
  (declare the level in prose, in the target's own doc) only.
- ENH-3306's `ui://` MCP Apps surface. Separate render target, still Level 1.
- Changing `EventBus` / `Transport` semantics for existing sinks.
- Level-2 (ask-to-run-prompt) behavior. This issue implements Level 3 only.

## Impact

- **Priority**: P2 — active goal area (`.ll/ll-goals.md:19`) and the only unclaimed row in
  a contract that already shipped (ENH-3307). Not P1: nothing is broken, and the entire
  benefit is opt-in behind a flag.
- **Effort**: Medium — the transport reuses `UnixSocketTransport`'s established fan-out
  shape and the executor change is one optional parameter, but it spans five modules plus
  a vendored asset and four docs.
- **Risk**: Medium. Four named risks:
  1. **htmx 4.0 is one day old** (released 2026-08-28). Any 2.x snippet is wrong — the
     `:inherited` inheritance model and the `htmx:before:request` event renames both
     changed. Pin the vendored version explicitly, do not copy 2.x examples, and gate on
     the learning tests exercising the real vendored bundle.
  2. **New network surface.** A loopback HTTP server is new for this package. Loopback-only
     binding, the URL token, and the Host-header check must each be asserted in tests, not
     just intended — loopback alone does not stop browser drive-by POSTs or DNS rebinding.
  3. **Executor inbound channel** touches the FSM's single routing authority. Mitigated by
     `inbound=None` being the default and provably inert, and by v1 deliberately having no
     routing semantics (record + re-emit only).
  4. **Dashboard refactor regression.** Extracting `build_dashboard_html` touches the
     shipped `file://` path; mitigated by the byte-identical-output regression test.
- **Breaking Change**: No. `--serve` is additive; `ll-loop run` without it and all of
  `ll-artifact` are regression-tested as unchanged.

## Related Key Documentation

- [`docs/reference/ARTIFACT_CONTROL_LEVELS.md`](../../docs/reference/ARTIFACT_CONTROL_LEVELS.md) — the contract this implements
- [`docs/reference/EVENT-SCHEMA.md`](../../docs/reference/EVENT-SCHEMA.md) — `## Reserved Event Names`, where `artifact_interaction` is reserved
- [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) — `## Artifact Control Layer`
- [htmx 4.0 release announcement](https://four.htmx.org/announcements/2026-08-28-htmx-4.0.0-is-released)

## Status

**Open** | Created: 2026-08-28 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-28_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 77/100 (uncapped) → MODERATE

`unproven_mechanism` was cleared by `/ll:decide-issue` (2026-08-28T19:38:47) on the
strength of the now-`proven` learning-test evidence for both `htmx` and `http.server`
(see Session Log). The prior run's outcome-confidence cap (`min(raw, 64)`) no longer
applies — this run scores the raw Criteria A-D sum (9 + 25 + 25 + 18 = 77) directly.

### Outcome Risk Factors
- Broad enumeration across 17 change sites (transport.py, fsm/executor.py, cli/loop/__init__.py, cli/loop/run.py, cli/artifact/dashboard.py, two template files, package_data.py, little_loops/__init__.py, plus 5 docs and 2 new vendored assets) is the dominant risk axis — Breadth scored 0/12 on Criterion A even though each individual site's depth is Local (contained logic change).

## Session Log
- `/ll:manage-issue` - 2026-08-28T20:35:03 - `40ac07c5-f2b6-4094-810d-3a0283a566be.jsonl`
- `/ll:confidence-check` - 2026-08-28T19:49:35 - `ea33ecd6-8c2e-4da2-984b-1c4e3288aafb.jsonl`
- pre-implementation review revision 2 - 2026-08-28 - specified SSE shutdown mechanics (sentinel + daemon-thread rationale), respec'd the byte-identical test as dev-time verification with `mtime=0` pinned (gzip mtime makes renders non-deterministic today), decided missing-`history.db` serve behavior (empty snapshot, run proceeds)
- `/ll:decide-issue` - 2026-08-28T19:38:47 - `e999097a-2e38-45bb-b367-623703246cd4.jsonl`
- `/ll:refine-issue` - 2026-08-28T19:37:43 - `0d616ba3-5ba9-4111-950a-8e9bccdf61b1.jsonl`
- `/ll:confidence-check` - 2026-08-28T19:30:30 - `d3964614-0e7e-4d89-bc34-5bd7bd83f914.jsonl`
- pre-implementation review revision - 2026-08-28 - moved bridge into the loop process (`ll-loop run --serve`), fixed `send()`/`close()` naming, specified the inbound drain contract + fragment renderer + lifecycle + POST hardening, decided sub-loop forwarding and the ll-goals citation drop
- `/ll:wire-issue` - 2026-08-28T19:01:15 - `d3964614-0e7e-4d89-bc34-5bd7bd83f914.jsonl`
- `/ll:refine-issue` - 2026-08-28T18:49:26 - `d3964614-0e7e-4d89-bc34-5bd7bd83f914.jsonl`

## Tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Reusable FSMExecutor/PersistentExecutor test fixtures already exist**: `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor` (from `:802`) has `simple_fsm` (`:805-823`, a minimal 3-state in-memory `FSMLoop`) and `tmp_loops_dir` (`:825-828`, `tmp_path / ".loops"`) fixtures, and the shared `MockActionRunner` dataclass (defined once in `test_fsm_executor.py:38-53`, imported elsewhere) drives `FSMExecutor`/`PersistentExecutor` without real subprocess execution. `test_archive_run_only_saves_state_and_archives` (`test_fsm_persistence.py:874-891+`, ENH-2516) is the closest existing signal-handler-safe-shutdown precedent for the new serve-lifecycle test (bridge `close()` firing on terminal state / Ctrl-C).
- **No existing test binds a real stdlib HTTP server for a `Transport` class**: `TestUnixSocketTransport` (`test_transport.py:394+`) is the closest precedent for binding a real listening socket in-process and asserting on delivered bytes/close-and-thread-join timing, but it is `AF_UNIX`, not TCP/HTTP. `TestWebhookTransport` (`test_transport.py:1158+`) mocks `httpx.post` directly and never opens a real socket. Confirmed by a repo-wide `HTTPServer|ThreadingHTTPServer|http.server` search: only 2 unrelated hits (`test_hooks_integration.py`, `test_flux_image_generator.py`) — `LocalBridgeTransport`'s tests need new real-socket test infrastructure, not an extension of an existing `Transport` test fixture.
