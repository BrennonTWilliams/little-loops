---
id: ENH-3351
title: 'Add `ll-artifact dashboard --serve`: a Level-3 localhost SSE bridge for live
  FSM dashboards'
type: ENH
priority: P2
status: open
discovered_date: '2026-08-28'
relates_to:
- ENH-3307
- ENH-3306
labels:
- artifact
- fsm
- htmx
---

## Summary

Add an opt-in `ll-artifact dashboard --serve` mode that binds a loopback-only stdlib
HTTP server, streams `EventBus` events to the rendered page over SSE, and accepts
`artifact_interaction` POSTs back into the running `FSMExecutor`. This is the first
implementation of **Level 3 (host-owned)** in
[`docs/reference/ARTIFACT_CONTROL_LEVELS.md`](../../docs/reference/ARTIFACT_CONTROL_LEVELS.md),
whose render-target table currently has no Level-3 row at all. The client half uses
htmx 4.0 (`hx-sse` + native morph swaps + `<hx-partial>`), vendored as package data
and inlined into the page the same way `sql.js` already is.

The default `file://` output path is unchanged and stays htmx-free.

## Current Behavior

`ll-artifact` is offline and single-file by construction:

- `cmd_dashboard` (`scripts/little_loops/cli/artifact/dashboard.py`) builds a filtered,
  ENH-075-redacted snapshot of `.ll/history.db`, gzip+base64-embeds it beside an
  inlined `sql.js`, and writes one HTML file that "runs arbitrary read-only SQL over
  `file://` with no network access". Its flags are `--tables`, `--since`, `--local`,
  `--db`, `-o/--output`. There is no server mode.
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
There is no `docs/explorations/` directory. htmx appears nowhere in the codebase; it is
referenced only in that goals line and in ENH-3306/ENH-3307 prose.

## Expected Behavior

`ll-artifact dashboard --serve [--port N]` binds `127.0.0.1` (loopback only, never
`0.0.0.0`), prints a URL, and serves the same dashboard page with a live region wired to
an SSE endpoint. While a loop runs, the page updates in place: state badge, iteration
counter, and log tail refresh from streamed events **without losing scroll position,
open `<details>`, or in-progress query-box text**.

The page declares Level 3 and may POST an `artifact_interaction` event to the bridge;
the bridge hands it to the executor's inbound channel unchanged (Prohibition 2 in
`ARTIFACT_CONTROL_LEVELS.md`) and never consumes it itself.

`ARTIFACT_CONTROL_LEVELS.md` gains its first Level-3 render-target row. Omitting
`--serve` produces the byte-for-byte `file://` artifact it produces today, with no htmx
in it.

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
enqueues `artifact_interaction` onto a `queue.Queue` the executor can drain.

Use `http.server.ThreadingHTTPServer` from the stdlib. Do **not** add a web framework:
the only HTTP machinery in the package today is `uvicorn`, imported lazily inside
`mcp_server/server.py:298` and optional; `.claude/CLAUDE.md` requires preferring stdlib
over a new pin.

htmx ships as **vendored package data** (`templates/vendor/htmax.js`), not a Python
dependency — registered in `package_data.py` and covered by `ll-verify-package-data`.

### 2. Executor inbound channel

`FSMExecutor` gains an optional `inbound: queue.Queue[dict] | None = None` constructor
parameter, drained non-blockingly at the top of each `run()` iteration. `None` (the
default) preserves today's behavior exactly — this is additive and every existing caller
is unaffected.

### 3. Page

The dashboard template grows a `--serve`-only block (Jinja-conditional, absent from the
`file://` render) carrying the inlined `htmax.js`, an `hx-sse` connection to
`/events`, and morph-swap targets for the live regions.

### Alternative considered — reuse `UnixSocketTransport` + a `socat`-style shim

Rejected: a browser cannot open a unix socket, so a translating HTTP process is required
regardless, and that process is the thing being built here. Building it directly is
strictly less machinery.

## API/Interface

```python
# scripts/little_loops/transport.py
class LocalBridgeTransport:
    """Loopback-only SSE bridge (ARTIFACT_CONTROL_LEVELS Level 3)."""

    def __init__(self, port: int = 0, inbound: queue.Queue[dict] | None = None) -> None: ...
    def emit(self, event: dict[str, Any]) -> None: ...   # Transport protocol
    def close(self) -> None: ...
    @property
    def url(self) -> str: ...                            # http://127.0.0.1:<bound-port>

# scripts/little_loops/fsm/executor.py
class FSMExecutor:
    def __init__(self, ..., inbound: queue.Queue[dict] | None = None) -> None: ...
```

```
ll-artifact dashboard --serve [--port N]
  --serve   Bind a loopback HTTP + SSE bridge instead of writing a static file.
            Declares Level 3 (host-owned). Implies a live page; the default
            file:// output is unaffected and contains no htmx.
  --port    TCP port on 127.0.0.1 (default: 0 = ephemeral, printed on start).
```

## Program Design

### Types

- `LocalBridgeTransport.inbound: queue.Queue[dict[str, Any]] | None`
- `FSMExecutor.inbound: queue.Queue[dict[str, Any]] | None`

### Signatures

- `LocalBridgeTransport.__init__(port: int = 0, inbound: queue.Queue | None = None) -> None`
- `LocalBridgeTransport.emit(event: dict[str, Any]) -> None`
- `LocalBridgeTransport.url() -> str`
- `FSMExecutor._drain_inbound() -> list[dict[str, Any]]`
- `cmd_dashboard(args: argparse.Namespace, logger: Logger) -> int` — extended, not replaced

### Call Path

Outbound: `FSMExecutor._emit` -> `EventBus.emit` -> `LocalBridgeTransport.emit` -> SSE
frame -> `hx-sse` morph swap.

Inbound: page POST `/interaction` -> `LocalBridgeTransport` handler -> `queue.Queue` ->
`FSMExecutor._drain_inbound` -> `FSMExecutor.run`.

Wiring: `wire_transports` (`transport.py:758`) registers the sink; `cmd_dashboard`
constructs it under `--serve`.

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` — add `LocalBridgeTransport`; register in `wire_transports`
- `scripts/little_loops/fsm/executor.py` — optional `inbound` queue + `_drain_inbound`
- `scripts/little_loops/cli/artifact/dashboard.py` — `--serve` / `--port` in `add_dashboard_parser`, branch in `cmd_dashboard`
- `scripts/little_loops/templates/dashboard.llat/template.html.j2` — `--serve`-only htmx block
- `scripts/little_loops/package_data.py` — register `templates/vendor/htmax.js`
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — first Level-3 render-target row
- `docs/reference/CLI.md` — `--serve` / `--port`
- `.ll/ll-goals.md` — fix the two dangling `docs/explorations/` references (restore or drop)

### Files to Create
- `scripts/little_loops/templates/vendor/htmax.js` — vendored htmx 4.0 bundle, version pinned in a header comment

### Dependent Files (Callers/Importers)
- `scripts/little_loops/events.py` — `EventBus.add_transport` / `Transport` protocol conformance
- Every current `FSMExecutor(...)` construction site — unaffected (`inbound` defaults to `None`), but grep to confirm no positional-arg breakage

### Similar Patterns
- `UnixSocketTransport` (`transport.py:119`) — client fan-out and `_claim_socket_path` lifecycle; closest precedent
- `mcp_server/server.py:298` — precedent for lazily-imported, optional HTTP machinery

### Tests
- `scripts/tests/test_transport.py` — bind/emit/close, loopback-only bind assertion, port-in-use handling
- `scripts/tests/test_fsm_executor.py` — `inbound=None` is byte-identical to today; queued event is drained
- `scripts/tests/test_feat3304_artifact_dashboard.py` — `--serve` absent => output has no htmx (regression guard on the `file://` path)

### Documentation
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md`, `docs/reference/CLI.md`, `docs/ARCHITECTURE.md` (`## Artifact Control Layer`)

### Configuration
- N/A — `--serve` is flag-only; no `ll-config.json` key in this issue

## Implementation Steps

1. Fix the dangling `docs/explorations/` references in `.ll/ll-goals.md` (restore the two
   docs or drop the citations). Cheap, independent, unblocks reading the prior art.
2. Vendor htmx 4.0 as package data; register it and extend `ll-verify-package-data`.
3. Add `LocalBridgeTransport` (outbound SSE only) + tests. Assert the loopback-only bind.
4. Add the executor `inbound` queue and `_drain_inbound`; prove `inbound=None` is a no-op.
5. Add `--serve` / `--port` to `cmd_dashboard` and the template's conditional htmx block.
6. Update `ARTIFACT_CONTROL_LEVELS.md` (Level-3 row), `CLI.md`, `ARCHITECTURE.md`.
7. Verify: `python -m pytest scripts/tests/` exits 0, and a live loop run visibly updates
   the page while preserving scroll and query-box text.

## Success Metrics

- `ARTIFACT_CONTROL_LEVELS.md`'s render-target table has a Level-3 row backed by shipping code.
- A page open during a live loop run updates on each iteration with scroll position, open
  `<details>`, and query-box contents intact — the state today's regenerate-and-reload destroys.
- Default `ll-artifact dashboard` output contains zero occurrences of `htmx`/`hx-` and is
  byte-identical to the pre-change render (regression-tested).
- No new entry in `scripts/pyproject.toml` `dependencies`.

## Scope Boundaries

Explicitly **out of scope**:

- Retrofitting htmx into `policy-builder`. It is pure client-side state with no server on
  the other end; htmx replaces nothing there and would disturb its Node conformance gate.
- Retrofitting htmx into `render` / `extract` / `refresh` / `.llat` templates.
- Any non-loopback bind, authentication, or TLS. `--serve` is a local-development
  affordance; if it ever needs to leave `127.0.0.1`, that is a separate issue with its own
  threat model.
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
  shape and the executor change is one optional parameter, but it spans four modules plus
  a vendored asset and three docs.
- **Risk**: Medium. Three named risks:
  1. **htmx 4.0 is one day old** (released 2026-08-28). Any 2.x snippet is wrong — the
     `:inherited` inheritance model and the `htmx:before:request` event renames both
     changed. Pin the vendored version explicitly and do not copy 2.x examples.
  2. **New network surface.** A loopback HTTP server is new for this package. Loopback-only
     binding must be asserted in a test, not just intended.
  3. **Executor inbound channel** touches the FSM's single routing authority. Mitigated by
     `inbound=None` being the default and provably inert.
- **Breaking Change**: No. `--serve` is additive; the default output path is
  regression-tested as unchanged.

## Related Key Documentation

- [`docs/reference/ARTIFACT_CONTROL_LEVELS.md`](../../docs/reference/ARTIFACT_CONTROL_LEVELS.md) — the contract this implements
- [`docs/reference/EVENT-SCHEMA.md`](../../docs/reference/EVENT-SCHEMA.md) — `## Reserved Event Names`, where `artifact_interaction` is reserved
- [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) — `## Artifact Control Layer`
- [htmx 4.0 release announcement](https://four.htmx.org/announcements/2026-08-28-htmx-4.0.0-is-released)

## Status

**Open** | Created: 2026-08-28 | Priority: P2
