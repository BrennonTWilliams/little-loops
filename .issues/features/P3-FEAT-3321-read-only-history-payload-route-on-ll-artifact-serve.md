---
id: FEAT-3321
type: FEAT
title: Read-only history payload route on `ll-artifact serve`
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T01:39:46Z'
relates_to:
- FEAT-3323
- ENH-3351
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

- `ll-artifact serve` serves the `dashboard.llat` page at `GET /{token}/`
  rendered with `ServeContext(events_url=..., interaction_url=None)`, so the
  page has the SSE sentinel but no Level 3 interaction POST.
- `GET /{token}/history` returns a JSON payload
  `{"snapshot_gzip_b64", "exported_at", "source_schema_version",
  "export_mode", "filter_tables"}` produced by the same
  `build_snapshot_db` path the export uses, filtered by
  `artifacts.export.mode`.
- The page re-fetches `./history` every N seconds (default 5) and replaces
  the sql.js `db` instance (`template.html.j2:169`) in place, so new rows
  appear in the query box without reload.
- The route is mounted only when `events.bridge.history` is `true`
  (default `false`); otherwise `GET /{token}/history` is 404 and the served
  page carries no timer.
- The route's connection is opened `mode=ro` and never runs migrations; a
  missing `history.db` yields an empty payload and does not create the file.

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
`SELECT loop, state, ended_at FROM loop_run ORDER BY started_at DESC LIMIT 20`
re-run a minute later shows the runs that finished in between, with no
re-export and no reload. Closing and re-opening the tab, or restarting an
individual loop, does not affect the server. The user never edits config
beyond setting `events.bridge.history: true` once.

## Program Design

New and changed Python surface; all names live in existing modules.

```python
# scripts/little_loops/cli/artifact/dashboard.py

@dataclass(frozen=True)
class HistoryPayload:
    snapshot_gzip_b64: str
    source_version: str | None
    exported_at: str
    export_mode: str
    filter_tables: list[str]

def build_history_payload(
    *, db_path: Path, config: BRConfig, tables: list[str],
    since_iso: str | None, mode: str, allow_missing: bool,
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
  the page render consume; `to_dict()` is the JSON body of the route.
- `build_history_payload(...)` — extracted from the snapshot block of
  `build_dashboard_html`; calls `build_snapshot_db` (read-only opener),
  applies the `max_artifact_bytes` pre-check, raises `ValueError` on
  overflow. `allow_missing=True` returns an empty gzip payload when the db
  file is absent instead of raising, matching the serve-context branch.
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
  `Cache-Control: no-store`; maps `ValueError` to 413.

```python
# scripts/little_loops/transport.py

class SseBridge:
    def set_page_html(self, page_html: str) -> None: ...
```

- `SseBridge.set_page_html(page_html)` — replaces the static placeholder
  served at `GET /{token}/`, mirroring the existing
  `LocalBridgeTransport.set_page_html`; needed because the page embeds
  `bridge.url`, which exists only after the bind.

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

Server startup:
`cmd_serve()` (`cli/artifact/serve.py:36-64`) → `BRConfig` → `make_history_route(config)` (new, same module; only when `config.events.bridge.history`) → `SseBridge.__init__(config.events, port=port, routes={"history": ...})` (`transport.py:1248-1277`) → `resolve_tables(None, local_mode=...)` (`cli/artifact/dashboard.py:75`) → `build_dashboard_html(..., serve_context=ServeContext(events_url=bridge.url + "events", interaction_url=None, history_url=bridge.url + "history"))` (`dashboard.py:155`) → `build_history_payload(...)` (new, extracted from `dashboard.py:176-198`) → `build_snapshot_db(...)` (`session_store/queries.py`, via `_connect_readonly`) → `SseBridge.set_page_html(rendered.html)` (new, mirrors `transport.py:808-817`) → `serve_sse_bridge` print-and-block body (`transport.py:1439-1478`)

Per request:
`_make_sse_bridge_handler.<locals>._Handler.do_GET` (`transport.py:1209-1230`) → Host check (`_expected_hosts`) → token-prefix check → `bridge._routes["history"]` → `make_history_route.<locals>.handler` → `resolve_tables` → `build_history_payload(allow_missing=True)` → `build_snapshot_db` → JSON response (`Cache-Control: no-store`); `ValueError` → 413

Page side (`templates/dashboard.llat/template.html.j2`):
existing sql.js boot (`:302` `initSqlJs` → `:169` `new SQL.Database`) → new timer block (only when `serve_history_url` stamped) → `fetch(history_url)` → existing base64/gunzip helpers → `db.close()` → `db = new SQL.Database(bytes)`; interaction block (`:342-366`) skipped when `serve_interaction_url_js` is `null`.

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
- `scripts/little_loops/transport.py:1439-1478` — `serve_sse_bridge`;
  builds the bridge and blocks. Page rendering and route registration wire
  in here (or in `cli/artifact/serve.py:cmd_serve`, which calls it).
- `scripts/little_loops/cli/artifact/serve.py:36-64` — `cmd_serve`; already
  resolves `BRConfig` and port.
- `scripts/little_loops/cli/artifact/dashboard.py:133-144` — `ServeContext`;
  `interaction_url: str` becomes `str | None = None`.
- `scripts/little_loops/cli/artifact/dashboard.py:155-262` —
  `build_dashboard_html`; the snapshot-building block (`:176-198`) is the
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
  the timer replaces `db` here. `:319-366` — serve block; `:342-366` is the
  interaction form and POST, to be wrapped in a conditional on the
  interaction URL being present.
- `scripts/little_loops/templates/dashboard.llat/manifest.yaml:37-44` —
  serve-mode data keys; add `serve_history_url` and `serve_history_poll_s`,
  make `serve_interaction_url_js` optional or emit `null`.
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
   snapshot-to-base64 block (`dashboard.py:176-198`, including the
   missing-db-with-serve-context branch and the `max_artifact_bytes`
   pre-check) into `build_history_payload(db_path, config, tables,
   since_iso, mode) -> HistoryPayload` (frozen dataclass:
   `snapshot_gzip_b64`, `source_version`, `exported_at`). Have
   `build_dashboard_html` call it. No behavior change for `dashboard` or
   `ll-loop run --serve`.
2. **Relax `ServeContext`.** `interaction_url: str | None = None`. In
   `build_dashboard_html`, stamp `serve_interaction_url_js` as `"null"` when
   `None`. Add `serve_history_url: str | None` and `serve_history_poll_s:
   int` to `ServeContext` and the stamped data. Update `manifest.yaml`.
3. **Template.** Wrap the interaction form and its script
   (`template.html.j2:342-366`) in a JS guard on the interaction URL being
   non-null (or a Jinja conditional on a new `serve_interaction_enabled`
   flag). Add a timer block, active only when `serve_history_url` is set,
   that fetches the URL, base64-decodes and gunzips with the existing
   helpers, closes the old `db`, assigns `db = new SQL.Database(bytes)`, and
   updates the exported-at label. Keep the user's current query text and
   results untouched until they re-run.
4. **Route.** In `cli/artifact/serve.py` (or a sibling `history_route.py`),
   define `make_history_route(config) -> Callable[[handler], None]` that
   calls `build_history_payload` with
   `resolve_tables(None, local_mode=config.artifacts.export.mode == "local")`
   and writes JSON with `Content-Type: application/json` and
   `Cache-Control: no-store`. A `ValueError` from the size pre-check becomes
   a 413 with the message body.
5. **Bridge page hook.** Add `SseBridge.set_page_html(html: str)` mirroring
   `LocalBridgeTransport.set_page_html`; `_serve_page` reads the instance
   attribute instead of the module constant.
6. **Wire `cmd_serve`.** Construct `SseBridge(config.events, port=port,
   routes={"history": route} if config.events.bridge.history else None)`,
   then render the page with
   `ServeContext(events_url=bridge.url + "events", interaction_url=None,
   serve_history_url=bridge.url + "history" if enabled else None, ...)` and
   call `bridge.set_page_html(rendered.html)`. Refactor `serve_sse_bridge`
   to accept a pre-built bridge, or move its print-and-block body into
   `cmd_serve`.
7. **Config.** `BridgeEventsConfig.history: bool = False`;
   `config-schema.json` `events.bridge.properties.history`. Run the
   BUG-3192 guards.
8. **Docs.** `ARTIFACT_CONTROL_LEVELS.md` row and `CLI.md` section.
9. **Tests** (see Acceptance Criteria).

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

- Config: `events.bridge.history` (`bool`, default `false`).
- Python: `build_history_payload(...)` in `cli/artifact/dashboard.py`;
  `ServeContext.interaction_url: str | None`; `SseBridge.set_page_html`.

## Acceptance Criteria

- [ ] `GET /{token}/history` returns the JSON payload above. A test loads
      the decoded snapshot with `sqlite3` and asserts that in shareable mode
      only ENH-075 allowlisted columns are present for `loop_run` and
      `usage_event`, and in local mode all columns are present.
- [ ] The route never migrates or creates the database. A test points the
      bridge at a project dir with no `history.db`, hits the route, asserts a
      200 with an empty snapshot, and asserts the file still does not exist.
      A second test asserts `_connect_readonly` is the opener (an `INSERT`
      on that connection raises `sqlite3.OperationalError`).
- [ ] New rows appear without reload. A test inserts a `loop_run` row via
      `session_store` between two route fetches and asserts the second
      decoded snapshot contains it and the first does not.
- [ ] The served page renders with `interaction_url=None` and emits no
      interaction POST: a test asserts the rendered HTML contains
      `hx-sse:connect` and the history timer, and does not contain
      `ll-interaction-send`.
- [ ] `ll-loop run --serve` output is byte-identical before and after
      (interaction wiring still present, no history timer), guarded by the
      existing ENH-3351 render tests.
- [ ] `events.bridge.history` defaults to `false`; with it false the route
      is 404 and the page has no timer. BUG-3192 Guards 1 and 2 pass.
- [ ] Existing `test_feat3323_sse_bridge.py` passes unchanged (Host/token
      checks apply to the new route; a request without the token prefix is
      404).
- [ ] `docs/reference/ARTIFACT_CONTROL_LEVELS.md` render-target table and
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

## Impact

- **Priority**: P3 - developer-experience live view; no correctness impact.
- **Effort**: Small-Medium - the route and timer are small; the extraction
  in step 1 and the `ServeContext` relaxation touch the template, manifest,
  and two render callers.
- **Risk**: Low - read-only opener already proven by the export path;
  loopback and token gating inherited from FEAT-3323; off by default.
- **Breaking Change**: No.

## Open Questions

1. Poll interval: fixed default of 5s, or a `events.bridge.history_poll_s`
   key? Recommendation: fixed 5s constant in v1, no config; add the key only
   if someone asks.
2. Should the payload include `row_cap`-style truncation info when the
   snapshot exceeds `max_artifact_bytes`, or just 413? Recommendation: 413
   with the same message the export prints; the page shows it in the
   warning banner.

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

## Status

**Open** | Created: 2026-08-26 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-09-03T17:47:56 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:59 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-26T21:32:44 - `ce0d899f-b243-4b9b-9802-1a5047cda0de.jsonl`
