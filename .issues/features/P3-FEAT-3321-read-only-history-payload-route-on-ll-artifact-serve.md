---
id: FEAT-3321
type: FEAT
title: Read-only history payload route on `ll-artifact serve`
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T01:39:46Z'
completed_at: '2026-09-04T03:02:40Z'
relates_to:
- FEAT-3323
- ENH-3351
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-3321: Read-only history payload route on `ll-artifact serve`

## Summary

Mount a single read-only `GET /{token}/history` route on FEAT-3323's
`SseBridge` (`ll-artifact serve`) that returns the same gzipped
`history.db` snapshot `build_dashboard_html` embeds at export time, and
serve the existing `dashboard.llat` page from that server with a timer that
re-fetches the payload and reloads it into the already-embedded sql.js.

This is **not** a new web UI. The page, the SSE plumbing, the htmx kit, and
the server all exist in-tree already (ENH-3351, FEAT-3323). This issue is
one route, one config key, one `ServeContext` relaxation, and one
page-side timer. Everything with a JS build step, a framework, or app
structure stays out of this repo (precedent: `little-loops-policy-builder`).

## Scope Boundary (re-scoped 2026-09-03)

The original framing of this issue ("Local realtime web UI for
live-querying history.db", with an arbitrary-SQL query route and its own
`artifacts` config block) is withdrawn. Reasons, verified against the tree:

- **The page already exists and is already served live.** `ll-loop run
  --serve` renders `templates/dashboard.llat` with
  `serve_context=ServeContext(events_url, interaction_url)`
  (`cli/loop/run.py:625-647`), which adds an SSE sentinel and htmx partial
  swaps (`template.html.j2:319-329`, `render_live_fragment` at
  `cli/artifact/dashboard.py:274`). The sql.js query box in that page is the
  "live query" surface. Do not build a second page.
- **The mount point already exists.** `SseBridge.__init__` accepts
  `routes: dict[str, Callable[[BaseHTTPRequestHandler], None]]`
  (`transport.py:1248-1277`) and its handler dispatches `GET /{token}/<route>`
  through `bridge._routes` after the Host and token checks
  (`transport.py:1191-1230`). The docstring names this "the FEAT-3321
  mount point".
- **Arbitrary SQL from the browser is dropped.** `PRAGMA query_only` stops
  writes only; it does not constrain `ATTACH`, SQL functions, or resource
  use. SQL stays client-side inside sql.js, exactly as the dashboard works
  today. The route returns data, not query results.
- **No new redaction or config surface.** The route obeys
  `artifacts.export.mode` via `resolve_tables(None, local_mode=...)`
  (`dashboard.py:75-105`), the same switch `ll-loop run --serve` already
  applies. The single new config key is a sub-key of FEAT-3323's existing
  `events.bridge` block, not a new block.
- **Out-of-tree is not viable for this piece.** The extension protocol
  (`extension.py:38-111`) has `on_event`, interceptors, action/evaluator
  providers, and hook intents, but no HTTP route provider. An external
  package would have to run its own listener and re-implement the
  read-only opener, ENH-075 projection, and mode gating. If out-of-tree
  UIs are wanted later, the missing seam is a `provided_routes` extension
  protocol on the bridge; that is a separate issue.

## Current Behavior

- `ll-artifact dashboard` exports a frozen snapshot into a single HTML file.
- `ll-loop run --serve` serves that same page live, but only for the
  lifetime of one loop process, and its embedded snapshot is taken once at
  startup; new `loop_run`/`usage_event` rows do not reach the sql.js query
  box without restarting the loop.
- `ll-artifact serve` (FEAT-3323) serves a static placeholder page
  (`_SSE_BRIDGE_PAGE_HTML`, `transport.py:1319-1325`) plus the SSE stream.
  It has no history data at all.

## Expected Behavior

- `events.bridge.history` (default `false`) gates the **whole feature**, page
  included. With it `false`, `ll-artifact serve` behaves exactly as FEAT-3323
  shipped it: `GET /{token}/` is the static `_SSE_BRIDGE_PAGE_HTML`
  placeholder and `GET /{token}/history` is 404. Serving the dashboard page
  without the route would hand every default user a multi-MB page whose
  snapshot is frozen at server start and never refreshes — strictly worse and
  more misleading than the placeholder, so the page swap and the route are
  one switch, not two.
- With `events.bridge.history: true`, `ll-artifact serve` serves the
  `dashboard.llat` page at `GET /{token}/` rendered with
  `ServeContext(events_url=..., interaction_url=None, history_url=...)`, so
  the page has the SSE sentinel and the refresh timer but no Level 3
  interaction POST.
- `GET /{token}/history` returns a JSON payload
  `{"snapshot_gzip_b64", "exported_at", "source_schema_version",
  "export_mode", "filter_tables"}` produced by the same
  `build_snapshot_db` path the export uses, filtered by
  `artifacts.export.mode`.
- The page re-fetches `./history` every 5 seconds, reassigns the module-level
  `snapshotBytes` and re-runs the template's existing `instantiate()`
  (`template.html.j2:168-170`), so new rows appear in the query box without a
  reload, the `PRAGMA query_only` guardrail is re-applied, and the "Reset
  snapshot" button resets to the *latest* snapshot rather than the startup one.
- The route's connection is opened `mode=ro` and never runs migrations; a
  missing `history.db` yields an empty payload and does not create the file.
- A page-render failure never prevents the bridge from serving. If
  `build_dashboard_html` raises (oversized snapshot, manifest/data error), the
  server logs a warning and falls back to the placeholder page; the SSE stream
  and the bridge's exit codes are unchanged from FEAT-3323.
- Repeated polls do not rebuild the snapshot per request: the route caches the
  built payload keyed on the source db's `(st_mtime_ns, st_size)` behind a
  lock, so N open tabs cost one build per change, and serves `304` to a
  matching `If-None-Match`.

`ll-artifact serve` gains no `--local` flag; the route follows
`artifacts.export.mode`, whose default is `shareable` (ENH-075 column
allowlist). A project that has set `mode: local` serves unredacted history
rows on the loopback port, gated only by FEAT-3323's Host check and URL token
— the same exposure `ll-loop run --serve` already has.

## Motivation

Watching an in-progress `ll-sprint`/`ll-parallel`/`ll-loop` run's history
data today means polling `ll-session recent` by hand or re-exporting a
dashboard. `ll-artifact serve` already outlives any single loop process and
already has the page; adding the data route closes the gap with the
smallest possible surface and no live-connection dependency in the
portable `.llat` render pipeline.

## Use Case

A user starts a long `ll-sprint` run, then runs `ll-artifact serve` in a
second terminal and opens the printed URL. The page shows the live SSE
state badges from every producer socket in the project, and the sql.js
query box below refreshes on a timer, so a query like
`SELECT loop, final_state, ended_at FROM loop_runs ORDER BY started_at DESC LIMIT 20`
re-run a minute later shows the runs that finished in between, with no
re-export and no reload. (Note the table name: `loop_run`/`usage_event` are
`_EXPORT_TABLE_MAP` *type* names taken by `--tables` and `resolve_tables`;
the snapshot's actual SQLite tables are `loop_runs` / `usage_events`
(`session_store/queries.py:102`), which is what the page's predefined queries
already use.) Closing and re-opening the tab, or restarting an
individual loop, does not affect the server. The user never edits config
beyond setting `events.bridge.history: true` once.

## Program Design

### Deviations

- 2026-09-03 (implementation): `serve_history_enabled` is stamped
  **unconditionally in `build_dashboard_html`'s base `data` dict**, not only
  inside the `if serve_context is not None:` block that stamps
  `serve_interaction_enabled`/`serve_interaction_url_js`/
  `serve_history_url_js`/`serve_history_poll_s`. Reason: the Call Path's
  history-refresh timer must reassign the base query-box script's
  closure-local `db`/`snapshotBytes` and call its `instantiate()`/
  `buildViews()` directly (not via `window.*`, which those `var`s are never
  attached to) — so the timer's Jinja conditional necessarily lives inside
  the *base* `<script>` IIFE (the one that always renders, sql.js query box),
  not inside the `[[% if serve_enabled %]]`-gated region. `StrictUndefined`
  then requires `serve_history_enabled` present on every render, including
  the `file://` `dashboard` path where `serve_context is None` — mirroring
  how `serve_enabled` itself is already stamped unconditionally. The other
  four `serve_history_*`/`serve_interaction_*` keys stay inside the
  `serve_context is not None` block exactly as designed, since they're only
  referenced from inside `[[% if serve_enabled %]]`.

New and changed Python surface; all names live in existing modules.

```python
# scripts/little_loops/cli/artifact/dashboard.py

@dataclass(frozen=True)
class HistoryPayload:
    """Exactly five fields. `to_dict()` is the route's JSON body and performs
    the one key rename: `source_version` -> `"source_schema_version"`, matching
    the template data key `build_dashboard_html` already stamps."""

    snapshot_gzip_b64: str
    source_version: str | None
    exported_at: str
    export_mode: str
    filter_tables: list[str]

    def to_dict(self) -> dict[str, Any]: ...

def build_history_payload(
    *, db_path: Path, config: BRConfig, tables: list[str],
    since_iso: str | None, mode: str, allow_missing: bool = False,
) -> HistoryPayload:
    ...

@dataclass(frozen=True)
class ServeContext:
    events_url: str
    interaction_url: str | None = None
    history_url: str | None = None
    history_poll_s: int = 5
```

- `HistoryPayload` — the snapshot-plus-metadata value both the route and
  the page render consume. The dataclass field is `source_version` (matching
  `build_snapshot_db`'s return); the JSON key and the template data key are
  both `source_schema_version`. Do not introduce a third spelling.
- `build_history_payload(...)` — extracted from the snapshot block of
  `build_dashboard_html`; calls `build_snapshot_db` (read-only opener),
  applies the `max_artifact_bytes` pre-check, raises `ValueError` on
  overflow. `allow_missing=True` returns an empty gzip payload when the db
  file is absent instead of raising, matching the serve-context branch;
  `build_dashboard_html` passes `allow_missing=serve_context is not None` so
  the `file://` path keeps raising.
- `ServeContext` — `interaction_url` becomes optional so a server with no
  FSM executor renders no Level 3 wiring; `history_url` and
  `history_poll_s` drive the page-side timer and are `None`/unused when the
  gate is off.

```python
# scripts/little_loops/cli/artifact/serve.py

def make_history_route(config: BRConfig) -> Callable[[BaseHTTPRequestHandler], None]:
    ...
```

- `make_history_route(config)` — returns the handler mounted at
  `"history"`; resolves tables via `resolve_tables(None, local_mode=...)`,
  calls `build_history_payload(allow_missing=True)`, writes JSON with
  `Cache-Control: no-store` and an `ETag`; maps `ValueError` to 413.
- **Caching and concurrency.** The closure holds
  `(cache_key, payload_json, etag)` plus a `threading.Lock`. `cache_key` is
  `(st_mtime_ns, st_size)` of `db_path`, or `None` when absent. On each
  request: stat, and if the key is unchanged reuse the cached body; otherwise
  rebuild under the lock (double-checked, so N concurrent pollers cost one
  build). If `If-None-Match` matches the current ETag, return `304` with no
  body. Without this, each `GET /history` runs a full ATTACH +
  `CREATE TABLE … AS SELECT` + gzip + base64 over the whole db, and
  `ThreadingHTTPServer` will happily run one per open tab every 5s with no
  bound — `max_clients` covers the SSE stream only, not `_routes`.

```python
# scripts/little_loops/transport.py

class SseBridge:
    def set_page_html(self, page_html: str) -> None: ...

def serve_sse_bridge(
    config: EventsConfig,
    port: int | None = None,
    *,
    routes: dict[str, Callable[[BaseHTTPRequestHandler], None]] | None = None,
    page_html_factory: Callable[[SseBridge], str] | None = None,
) -> int:
    ...
```

- `SseBridge.set_page_html(page_html)` — replaces the static placeholder
  served at `GET /{token}/`, mirroring the existing
  `LocalBridgeTransport.set_page_html`; needed because the page embeds
  `bridge.url`, which exists only after the bind.
- `serve_sse_bridge` is **extended, not moved**. Its existing signature and
  print-and-block body stay put: it owns the
  `"socket" not in transports` / no-producer-socket stderr notices
  (`transport.py:1457-1470`). (`test_feat3323_sse_bridge.py:799` does **not**
  currently call `serve_sse_bridge` — see § Verification Notes; the
  extend-not-move decision stands on the stderr-notice ownership and the
  print-and-block body alone.) The two new keyword-only
  parameters are passed through to `SseBridge(...)` and to a
  `set_page_html` call made after the bind. `page_html_factory` takes the
  bound bridge so the page can embed `bridge.url`, and **any exception it
  raises is caught, logged as a warning, and swallowed** — the placeholder
  page stays, the bridge keeps serving (see § Expected Behavior).

```python
# scripts/little_loops/config/features.py

@dataclass
class BridgeEventsConfig:
    port: int = 8766
    max_clients: int = 8
    keepalive_s: float = 15.0
    rescan_s: float = 2.0
    history: bool = False
```

- `BridgeEventsConfig.history` — the single gate; mirrored in
  `config-schema.json` with `default: false`.

### Call Path

Server startup (only when `config.events.bridge.history` is `true`; otherwise
`cmd_serve` calls `serve_sse_bridge(config.events, port=port)` exactly as it
does today and nothing below runs):
`cmd_serve()` (`cli/artifact/serve.py:36-64`) → `BRConfig` → `make_history_route(config)` (new, same module) → `serve_sse_bridge(config.events, port=port, routes={"history": ...}, page_html_factory=...)` (`transport.py:1439-1478`) → `SseBridge.__init__(..., routes=...)` (`transport.py:1248-1277`) → factory, in a try/except that falls back to the placeholder: `resolve_tables(None, local_mode=...)` (`cli/artifact/dashboard.py:75`) → `build_dashboard_html(..., serve_context=ServeContext(events_url=bridge.url + "events", interaction_url=None, history_url=bridge.url + "history"))` (`dashboard.py:155`) → `build_history_payload(...)` (new, extracted from `dashboard.py:176-210`) → `build_snapshot_db(...)` (`session_store/queries.py:246`, via `_connect_readonly`) → `SseBridge.set_page_html(rendered.html)` (new, mirrors `transport.py:808-817`) → print-and-block body

Per request:
`_make_sse_bridge_handler.<locals>._Handler.do_GET` (`transport.py:1209-1230`) → Host check (`_expected_hosts`, 403) → token-prefix check (404) → `bridge._routes["history"]` → `make_history_route.<locals>.handler` → stat `db_path` → cache hit (or `If-None-Match` → 304) → else under lock: `resolve_tables` → `build_history_payload(allow_missing=True)` → `build_snapshot_db` → JSON response (`Cache-Control: no-store`, `ETag`); `ValueError` → 413

Page side (`templates/dashboard.llat/template.html.j2`):
existing sql.js boot (`:302` `initSqlJs` → `:307` `snapshotBytes = results[0]` → `:168-170` `instantiate()`) → new timer block (rendered only under a Jinja conditional on `serve_history_enabled`) → `fetch(serve_history_url_js)` → existing `decodeBase64` (`:147`) / `gunzip` (`:156`) helpers → `db.close()` → **`snapshotBytes = bytes; instantiate(); buildViews();`** → update the exported-at label. The interaction block (button at `:337-340`, handler script at `:342-360`) is omitted entirely by a Jinja conditional, not merely inert.

**Do not** write `db = new SQL.Database(bytes)` directly at `:169`'s site. That
skips `instantiate()`'s `db.run("PRAGMA query_only = 1")` (`:170`) — which the
template's own comment at `:163-167` identifies as the actual write rejection,
the `textCheck` at `:177` being message-only — and leaves the
"Reset snapshot" button (`:106`, handler at `:286-296`) restoring the *startup*
bytes forever, because Reset re-runs `instantiate()` off the module-level
`snapshotBytes` (`:136`). Reassigning `snapshotBytes` and calling
`instantiate()` fixes both; `buildViews()` (`:268`) is re-run because the
visible table set can change between snapshots.

Unchanged caller that must stay byte-identical: `cli/loop/run.py:625-647` (`ll-loop run --serve`), which still passes a non-null `interaction_url` and no `history_url`.

## Integration Map

- `scripts/little_loops/transport.py:1248-1277` — `SseBridge.__init__`
  `routes=` parameter; `_routes` dict seeded with `""` and `"events"`.
- `scripts/little_loops/transport.py:1191-1230` — `_make_sse_bridge_handler`
  dispatch; new route inherits Host/token checks for free.
- `scripts/little_loops/transport.py:1319-1325` — `SseBridge._serve_page`
  serves a static constant. Needs a `set_page_html` mirroring
  `LocalBridgeTransport.set_page_html` (`transport.py:808-817`), because the
  page needs `bridge.url` (token) which is only known after construction.
- `scripts/little_loops/transport.py:1439-1478` — `serve_sse_bridge`; builds
  the bridge and blocks, and owns the `"socket" not in transports` /
  no-producer-socket stderr notices. Extend it with keyword-only `routes=`
  and `page_html_factory=`; do **not** move its body into `cmd_serve`
  (`test_feat3323_sse_bridge.py:799`'s docstring names it as the intended
  call for that stub's not-yet-written body — see § Verification Notes —
  and the AC requires that file to pass unchanged).
- `scripts/little_loops/cli/artifact/dashboard.py:~250` — the D18 escaping
  block. `serve_events_url` uses `html.escape` because it lands in an HTML
  attribute (`hx-sse:connect`); `serve_interaction_url_js` uses `json.dumps`
  because it lands in a JS string literal. The history URL is consumed by
  `fetch()` inside `<script>`, so it follows the **`json.dumps`** pattern and
  is named `serve_history_url_js`. Do not `html.escape` it.
- `scripts/little_loops/cli/artifact/serve.py:36-64` — `cmd_serve`; already
  resolves `BRConfig` and port.
- `scripts/little_loops/cli/artifact/dashboard.py:133-144` — `ServeContext`;
  `interaction_url: str` becomes `str | None = None`.
- `scripts/little_loops/cli/artifact/dashboard.py:155-262` —
  `build_dashboard_html`; the snapshot-building block (`:176-210`) is the
  code to extract into a shared payload helper so the route and the page
  render share one implementation. `:253-259` stamps the serve data keys.
- `scripts/little_loops/cli/artifact/dashboard.py:75-105` — `resolve_tables`
  (shareable-mode allowlist enforcement, D16/D22).
- `scripts/little_loops/session_store/queries.py:~250-300` —
  `build_snapshot_db`; opens via `_connect_readonly` (`file:…?mode=ro`,
  never `session_store.connect()`, D19). **This is the read-only opener to
  reuse.** Do not use `history_reader/_base.py:73-80`: it calls `ensure_db`
  first, which creates the file and runs migrations.
- `scripts/little_loops/templates/dashboard.llat/template.html.j2:119,169`
  — `SNAPSHOT_B64` constant and `db = new SQL.Database(snapshotBytes)`;
  the timer replaces `db` here. `:319-360` — serve block; `:337-340` is the
  interaction form button (`id="ll-interaction-send"`), `:342-360` its
  click-handler script and POST — both must be wrapped in the conditional on
  the interaction URL being present; wrapping only `:342-360` leaves the
  button rendered and fails the corresponding AC.
- `scripts/little_loops/templates/dashboard.llat/manifest.yaml:37-44` —
  serve-mode data keys; add `serve_history_enabled` (boolean),
  `serve_history_url_js` (string) and `serve_history_poll_s` (integer) to
  `properties`. None of them go in `required` (the `file://` path stamps
  none of them), matching how the existing `serve_*` keys are declared.
- `scripts/little_loops/artifact_templates.py:277` — the frozen Jinja
  environment sets `undefined=StrictUndefined`. **Every `serve_*` key the
  template body references inside `[[% if serve_enabled %]]` must be stamped
  unconditionally whenever `serve_enabled` is true**, using `"null"` / `false`
  / `0` for the unused case — never omitted. Omitting one raises at render
  time, which is the most likely first-run failure of this change.
- `scripts/little_loops/artifact_templates.py:259-279` + FEAT-3308 — the
  frozen delimiter set and the byte-exact round-trip contract. Editing
  `template.html.j2` / `manifest.yaml` puts `ll-artifact templatize` /
  `extract` / `render` round-trip tests in the blast radius; run them.
- `scripts/little_loops/config/features.py:1300-1326` — `BridgeEventsConfig`;
  add `history: bool = False`.
- `scripts/little_loops/config-schema.json` — `events.bridge.properties`;
  add `history` with `default: false` and a description.
- `scripts/tests/test_config_schema.py:1291` (Guard 1, value parity) and
  `:1433` (Guard 2, completeness) — BUG-3192 guards; both cover the new key
  automatically once dataclass and schema agree.
- `scripts/tests/test_feat3323_sse_bridge.py` — existing bridge tests;
  route tests follow its fixture pattern (bind port 0, real HTTP client).
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md:58-59` — "Declared levels by
  render target" table; the FEAT-3323 row ("live event stream page, Level
  1") is updated to cover the served dashboard page, still Level 1.
- `docs/reference/CLI.md:4813` — `ll-artifact serve` section; document the
  `history` gate and the route.

## Implementation Steps

1. **Extract the payload builder.** Move `build_dashboard_html`'s
   snapshot-to-base64 block (`dashboard.py:176-210`, including the
   missing-db-with-serve-context branch and the `max_artifact_bytes`
   pre-check) into `build_history_payload(*, db_path, config, tables,
   since_iso, mode, allow_missing=False) -> HistoryPayload` — the five-field
   frozen dataclass from § Program Design, plus `to_dict()`. Have
   `build_dashboard_html` call it with
   `allow_missing=serve_context is not None`. No behavior change for
   `dashboard` or `ll-loop run --serve`.
2. **Relax `ServeContext`.** `interaction_url: str | None = None`; add
   `history_url: str | None = None` and `history_poll_s: int = 5`. In
   `build_dashboard_html`, whenever `serve_context is not None`, stamp **all**
   serve keys unconditionally (`StrictUndefined` — see § Integration Map):
   `serve_interaction_enabled` (bool), `serve_interaction_url_js`
   (`json.dumps(url)` or the literal `"null"`), `serve_history_enabled`
   (bool), `serve_history_url_js` (`json.dumps(url)` or `"null"`), and
   `serve_history_poll_s` (int). Update `manifest.yaml` `properties`
   accordingly; leave them out of `required`.
3. **Template.** Wrap the interaction form and its script
   (`template.html.j2:337-360`) in a **Jinja** conditional on
   `serve_interaction_enabled` so the markup is absent, not merely inert —
   a JS-only guard leaves `ll-interaction-send` in the HTML and fails the
   corresponding AC. Add a timer block under a Jinja conditional on
   `serve_history_enabled` that fetches `serve_history_url_js` every
   `serve_history_poll_s` seconds, base64-decodes and gunzips with the
   existing `decodeBase64`/`gunzip` helpers, then
   `if (db) db.close(); snapshotBytes = bytes; instantiate(); buildViews();`
   and updates the exported-at label. Going through `instantiate()` (rather
   than assigning `db` directly) is what preserves `PRAGMA query_only` and
   keeps "Reset snapshot" pointed at the latest snapshot — see § Call Path.
   A failed fetch sets the status line and leaves the current `db` in place;
   the timer keeps running. Keep the user's query text and rendered results
   untouched until they re-run.
4. **Route.** In `cli/artifact/serve.py` (or a sibling `history_route.py`),
   define `make_history_route(config) -> Callable[[handler], None]` that
   calls `build_history_payload(allow_missing=True)` with
   `resolve_tables(None, local_mode=config.artifacts.export.mode == "local")`
   and writes JSON with `Content-Type: application/json`,
   `Cache-Control: no-store`, and an `ETag`. A `ValueError` from the size
   pre-check becomes a 413 with the message body.
5. **Cache the payload.** Give the closure a `threading.Lock` and a
   `(cache_key, body, etag)` slot, `cache_key = (st_mtime_ns, st_size)` of
   `db_path` or `None` when absent. Reuse on an unchanged key; rebuild under
   the lock with a double-check; return `304` on a matching `If-None-Match`.
   This is not an optimization — without it the route rebuilds the whole
   snapshot per tab per 5s, unbounded, since `max_clients` gates only the SSE
   stream.
6. **Bridge page hook.** Add `SseBridge.set_page_html(html: str)` mirroring
   `LocalBridgeTransport.set_page_html` (`transport.py:808-817`);
   `_serve_page` reads the instance attribute, initialized to
   `_SSE_BRIDGE_PAGE_HTML`, instead of the module constant.
7. **Wire `serve_sse_bridge` and `cmd_serve`.** Add keyword-only `routes=`
   and `page_html_factory=` to `serve_sse_bridge`, passing `routes` through to
   `SseBridge(...)` and calling `bridge.set_page_html(factory(bridge))` after
   the bind, inside a `try/except Exception` that logs a warning and leaves
   the placeholder in place. `cmd_serve` builds both only when
   `config.events.bridge.history` is true, with
   `ServeContext(events_url=bridge.url + "events", interaction_url=None,
   history_url=bridge.url + "history")`; when the gate is false it calls
   `serve_sse_bridge(config.events, port=port)` unchanged.
8. **Config.** `BridgeEventsConfig.history: bool = False` — in the dataclass
   field list *and* in `from_dict` (`features.py:1316-1324`, which enumerates
   every key explicitly); `config-schema.json` `events.bridge.properties.history`
   with `default: false`. Run the BUG-3192 guards.
9. **Docs.** `ARTIFACT_CONTROL_LEVELS.md` row and `CLI.md` section.
10. **Tests** (see Acceptance Criteria).

## API/Interface

- `GET /{token}/history` on `ll-artifact serve`, JSON body:

  ```json
  {
    "snapshot_gzip_b64": "<base64 of gzip(snapshot.db)>",
    "exported_at": "2026-09-03T18:00:00Z",
    "source_schema_version": "12",
    "export_mode": "shareable",
    "filter_tables": ["loop_run", "usage_event"]
  }
  ```

  Response headers: `Content-Type: application/json`,
  `Cache-Control: no-store`, `ETag: "<mtime_ns>-<size>"`. `If-None-Match`
  matching that ETag returns `304` with no body. `413` when the raw snapshot
  exceeds `artifacts.export.max_artifact_bytes`, with the same message the
  export path prints. `403` on a bad `Host` and `404` without the token
  prefix, both inherited from `_make_sse_bridge_handler`.

  Note `snapshot_gzip_b64` decodes to a SQLite file whose tables are
  `loop_runs` / `usage_events`; `filter_tables` carries the
  `_EXPORT_TABLE_MAP` *type* names (`loop_run`, `usage_event`), which is what
  the existing dashboard stamps.

- Config: `events.bridge.history` (`bool`, default `false`). Gates the route
  *and* the dashboard page; with it false `ll-artifact serve` is byte-for-byte
  FEAT-3323 behavior. No `history_poll_s` config key — the interval is a
  5-second default on `ServeContext.history_poll_s`; add a key only if asked.
- Python: `build_history_payload(...)` / `HistoryPayload` in
  `cli/artifact/dashboard.py`; `ServeContext.interaction_url: str | None`,
  `.history_url`, `.history_poll_s`; `SseBridge.set_page_html`;
  `serve_sse_bridge(..., routes=, page_html_factory=)`;
  `make_history_route(config)` in `cli/artifact/serve.py`.

## Acceptance Criteria

- [x] `GET /{token}/history` returns the JSON payload above. A test loads
      the decoded snapshot with `sqlite3` and asserts that in shareable mode
      only ENH-075 allowlisted columns are present on the `loop_runs` and
      `usage_events` **tables** (the `loop_run` / `usage_event` type names
      appear in `filter_tables`, not as table names), and in local mode all
      columns are present.
- [x] The route never migrates or creates the database. A test points the
      bridge at a project dir with no `history.db`, hits the route, asserts a
      200 with an empty snapshot, and asserts the file still does not exist.
      A second test asserts `_connect_readonly` is the opener (an `INSERT`
      on that connection raises `sqlite3.OperationalError`).
- [x] New rows appear without reload. A test inserts a `loop_run` row via
      `session_store` between two route fetches and asserts the second
      decoded snapshot contains it and the first does not. Because the route
      caches on `(st_mtime_ns, st_size)`, the test must not rely on
      coarse-grained mtime — assert on the decoded rows, and if the fixture
      writes fast enough to collide, `os.utime` the file or assert via the
      changed `size`.
- [x] Repeated identical polls do not rebuild. A test monkeypatches or
      wraps `build_snapshot_db`, fetches the route three times with no
      intervening write, and asserts exactly one build; a fourth fetch with
      `If-None-Match` set to the returned `ETag` returns `304` with an empty
      body. A concurrency test fires N simultaneous fetches against a cold
      cache and asserts a single build.
- [x] A page-render failure does not take down the server. A test forces
      `build_dashboard_html` to raise (e.g. `max_artifact_bytes=1`), starts
      the bridge, and asserts `GET /{token}/` returns 200 with the
      `_SSE_BRIDGE_PAGE_HTML` placeholder, `GET /{token}/events` still
      streams, and the process did not exit non-zero.
- [x] The served page renders with `interaction_url=None` and emits no
      interaction POST: a test asserts the rendered HTML contains
      `hx-sse:connect` and the history timer, and does **not** contain
      `ll-interaction-send` (i.e. the interaction markup is omitted by the
      Jinja conditional, not merely guarded in JS).
- [x] The refreshed page keeps its guardrails: a test asserts the timer
      block reassigns `snapshotBytes` and calls `instantiate()` (so
      `PRAGMA query_only` is re-applied and "Reset snapshot" restores the
      latest snapshot), rather than assigning `new SQL.Database(...)` to `db`
      directly.
- [x] `serve_history_url_js` is stamped via `json.dumps`, not `html.escape`:
      a test renders with a URL containing `&` and `'` and asserts the
      stamped value is a valid JS string literal with no HTML entities.
- [x] `ll-loop run --serve` output is unchanged modulo the `exported_at`
      timestamp (interaction wiring still present, no history timer),
      guarded by the existing ENH-3351 render tests passing unchanged.
- [x] `events.bridge.history` defaults to `false`; with it false, `GET
      /{token}/history` is 404 **and** `GET /{token}/` serves the
      `_SSE_BRIDGE_PAGE_HTML` placeholder (no dashboard page, no timer).
      BUG-3192 Guards 1 and 2 pass.
- [x] Existing `test_feat3323_sse_bridge.py` passes unchanged (see §
      Verification Notes on its `:799` stub). New tests assert the
      history route inherits both gates: a request with a foreign `Host`
      header is 403, and a request without the token prefix is 404.
- [x] FEAT-3308 round-trip tests for `ll-artifact templatize`/`extract`/
      `render` pass unchanged after the `template.html.j2` + `manifest.yaml`
      edits.
- [x] `docs/reference/ARTIFACT_CONTROL_LEVELS.md` render-target table and
      `docs/reference/CLI.md` `ll-artifact serve` section updated.

## Out of Scope

- Any write path into `.ll/history.db` (write-bridge stays deferred).
- Arbitrary SQL over HTTP.
- SSE-triggered refresh (re-fetch on `loop_run`/`usage_event`-bearing
  events instead of a timer). Cheap follow-up once the timer path exists.
- Folding live behavior into `ll-artifact render`/`templatize`/`extract`/
  `refresh`; the `file://` export path is untouched.
- Multi-user or remote access; loopback-only via FEAT-3323's controls.
- A `provided_routes` extension protocol for out-of-tree pages.
- A `--local` flag on `ll-artifact serve`; the route reads
  `artifacts.export.mode` only.
- An `events.bridge.history_poll_s` config key (see § Open Questions).
- Carrying `schema_version_warning` in the refresh payload.

## Impact

- **Priority**: P3 - developer-experience live view; no correctness impact.
- **Effort**: Medium - the route and timer are small, but the extraction in
  step 1, the payload cache, the render-failure fallback, and the
  `ServeContext` relaxation touch the template, manifest, `serve_sse_bridge`,
  and two render callers.
- **Risk**: Low - read-only opener already proven by the export path;
  loopback and token gating inherited from FEAT-3323; off by default.
- **Breaking Change**: No.

## Open Questions

None outstanding. Both prior questions are resolved in the body:

1. **Poll interval** — resolved 2026-09-03: fixed 5s, carried as
   `ServeContext.history_poll_s: int = 5` and stamped as
   `serve_history_poll_s`. No `events.bridge.history_poll_s` config key in
   v1; add one only if asked.
2. **Oversize behavior** — resolved 2026-09-03: `413` with the same message
   the export path prints, no `row_cap`-style truncation metadata. The page
   surfaces it in the status line and keeps the previous snapshot loaded.

One deliberate limitation, recorded rather than asked: `schema_version_warning`
is stamped once at render time from the startup snapshot and is **not** carried
in the payload, so it does not track refreshes. Acceptable because the source
db's schema version cannot change while the server runs without the installed
code also changing; revisit only if `ll-artifact serve` ever survives an
in-place upgrade.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-artifact serve`, `ll-artifact dashboard`
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — render-target level table
- `docs/reference/EVENT-SCHEMA.md` — SSE frame shape the page already
  consumes

## History

- 2026-08-26: created as "Local realtime web UI for live-querying
  history.db" with an arbitrary-SQL query route and its own `artifacts`
  config block; EPIC-3299 had named this out of scope for the template kit.
- 2026-08-26 / 2026-08-28: `/ll:audit-issue-conflicts` recorded that
  FEAT-3323 owns `ll-artifact serve`; ENH-3351 (`94a676582`) landed
  `ll-loop run --serve` and `LocalBridgeTransport`.
- 2026-09-03: `/ll:verify-issues` corrected `history_reader` citations
  after the subpackage split (`a25e1d688`). Pre-implementation review
  re-scoped the issue to a payload route on the existing page.
- 2026-09-03: FEAT-3323 completed (`92670a9de`); `SseBridge` shipped with a
  `routes=` mount point for this issue. Issue rewritten and retitled to
  match the re-scope; review findings folded into the body above.
- 2026-09-03: second pre-implementation review against the tree. Three design
  decisions settled — (a) `events.bridge.history` now gates the page as well
  as the route, so the default path stays the FEAT-3323 placeholder rather
  than a frozen multi-MB dashboard; (b) a page-render failure falls back to
  the placeholder instead of preventing the bridge from starting; (c) the
  route caches on `(st_mtime_ns, st_size)` with an `ETag`/`304` and a lock,
  since an uncached route rebuilds the whole snapshot per tab per poll with
  no bound. Plan defects corrected — the refresh goes through the template's
  `instantiate()` (preserving `PRAGMA query_only` and "Reset snapshot");
  `serve_history_url_js` uses `json.dumps`, not `html.escape`; the
  interaction block is removed by a Jinja conditional, not a JS guard (a JS
  guard failed its own AC); `StrictUndefined` requires all `serve_*` keys be
  stamped unconditionally; `loop_run`/`usage_event` type names vs
  `loop_runs`/`usage_events` table names disambiguated in the Use Case and
  ACs; `HistoryPayload`'s field list and `allow_missing` reconciled between
  § Program Design and § Implementation Steps; `serve_sse_bridge` is extended
  rather than moved, since `test_feat3323_sse_bridge.py:799` calls it
  directly. Both Open Questions closed; FEAT-3308 round-trip blast radius,
  the absent `--serve --local` flag, and the render-time-only
  `schema_version_warning` recorded. Effort raised Small-Medium → Medium.
- 2026-09-03: `/ll:verify-issues` re-verified all file:line citations against
  the tree. Six minor line-drift corrections applied throughout (see §
  Verification Notes). Two material corrections: the interaction-block Jinja
  conditional now targets `template.html.j2:337-360` (was `:342-366`, which
  excluded the `id="ll-interaction-send"` button itself and would have
  failed the corresponding AC); and the "extend, not move" justification for
  `serve_sse_bridge` no longer cites `test_feat3323_sse_bridge.py:799` as an
  existing positional caller — that line is a stub whose body calls
  `SseBridge(...)` directly, with the cited call string appearing only in a
  TODO docstring for not-yet-written test code. The extend-not-move
  conclusion is unchanged; it now rests on `serve_sse_bridge` owning the
  stderr producer-socket notices and the print-and-block body, not on a
  currently-nonexistent test dependency.

## Verification Notes

- **Line-drift corrections** (content confirmed present, cited line numbers
  off by a few): `dashboard.py` snapshot-to-base64 block is `:176-210` (was
  `:176-198`); `transport.py` stderr producer-socket notices are `:1457-1470`
  (was `:1455-1477`); `template.html.j2` `textCheck` starts `:177` (was
  `:174-176`); its reset handler starts `:286` (was `:287`); `decodeBase64`
  is `:147` (was `:146`); `gunzip` is `:156` (was `:157`).
- **Material correction — interaction block range.** `template.html.j2` is
  363 lines total. The interaction form's button
  (`id="ll-interaction-send"`) is at `:337-340`; its click-handler script and
  POST are at `:342-360`. The issue previously cited only `:342-366` for the
  Jinja conditional, which would have wrapped the script but left the button
  rendered — failing the AC that requires `ll-interaction-send` to be absent
  from the HTML entirely. Corrected throughout to `:337-360`.
- **Material correction — `test_feat3323_sse_bridge.py:799`.** The issue
  cited this line three times as proof that `serve_sse_bridge(config,
  port=0)` is called positionally today, used to justify extending rather
  than relocating `serve_sse_bridge`. Verified false: line 799 is
  `test_serve_sse_bridge_binds_loopback_and_prints_url`, a stub whose body
  calls `SseBridge(...)` directly; `serve_sse_bridge` is invoked nowhere in
  that file. The cited call string exists only inside a `TODO(FEAT-3323)`
  docstring describing test code not yet written. Corrected throughout; the
  design decision to extend `serve_sse_bridge` in place still holds (it owns
  the stderr notices and print-and-block body cited elsewhere in the issue),
  it just no longer depends on this false premise.
- All other checked citations (≈30 items across `dashboard.py`, `serve.py`,
  `transport.py`, `config/features.py`, `session_store/queries.py`,
  `history_reader/_base.py`, `manifest.yaml`, `cli/loop/run.py`,
  `extension.py`, `config-schema.json`, `ARTIFACT_CONTROL_LEVELS.md`,
  `CLI.md`, and the `test_config_schema.py` BUG-3192 guards) matched exactly.
  `ll-verify-evidence` and the decisions-log check both came back clean; no
  active required decision rules exist to violate. Both `relates_to` issues
  (FEAT-3323, ENH-3351) are confirmed `done`, and their cited fix commits
  (`92670a9de`, `94a676582`) exist and touch the claimed files. Nothing this
  issue proposes as new already exists in the tree.

## Resolution

Implemented per § Program Design / § Implementation Steps, with one recorded
deviation (see § Program Design → Deviations): `serve_history_enabled` is
stamped unconditionally rather than only inside the `serve_context is not
None` block, because the refresh timer must live inside the base query-box
`<script>` IIFE (not the `[[% if serve_enabled %]]`-gated region) to reach
its closure-local `db`/`snapshotBytes`/`instantiate`/`buildViews`.

All Acceptance Criteria pass with new tests in `test_feat3304_artifact_dashboard.py`
(`TestBuildHistoryPayload`, `TestServeContextRelaxation`) and
`test_feat3323_sse_bridge.py` (`TestHistoryRoute`, `TestPageHtmlFactoryFallback`,
`TestCmdServeHistoryGate`). Full suite: `python -m pytest scripts/tests/` —
22676 passed, 43 skipped, 0 failed. `ruff check scripts/` and
`python -m mypy scripts/little_loops/` both clean.

## Status

**Open** | Created: 2026-08-26 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-09-04T03:01:54 - `7d2a9c3e-7b09-4945-b21f-1cd41c9099d8.jsonl`
- `/ll:confidence-check` - 2026-09-04T02:18:58 - `30019f0e-09fb-48fa-82e7-9bf0c84b9638.jsonl`
- `/ll:verify-issues` - 2026-09-04T02:16:09 - `371c81cf-6cd1-4bb0-94f4-43941447dbc7.jsonl`
- `/ll:confidence-check` - 2026-09-04T01:56:22 - `01d833b6-5f4d-404a-bfc0-c03d3ef153b3.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:56 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:59 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-26T21:32:44 - `ce0d899f-b243-4b9b-9802-1a5047cda0de.jsonl`
