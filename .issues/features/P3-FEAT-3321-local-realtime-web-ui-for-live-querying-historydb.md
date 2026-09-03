---
id: FEAT-3321
type: FEAT
title: Local realtime web UI for live-querying history.db
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T01:39:46Z'
depends_on:
- FEAT-3323
---

# FEAT-3321: Local realtime web UI for live-querying history.db

## Summary

`ll-artifact dashboard` exports a point-in-time snapshot of `.ll/history.db`
into a single self-contained HTML file with an inlined `sql.js` — great for
sharing, but not live: the embedded data is frozen at export time and the
only way to see new rows is to re-run the export and reload the page.

This issue adds a second, standalone capability: a local dev-server view of
`.ll/history.db` that stays live as new `loop_run`/`usage_event` rows land,
for a user actively watching a running sprint/loop/parallel session.

EPIC-3299 explicitly named this "the history.db write-bridge and live-query
work" and declared it **out of scope**, tracked separately with no issue of
its own until now. This issue is that tracking issue.

## Current Behavior

The only browser view of `.ll/history.db` is `ll-artifact dashboard`, a
point-in-time export: the embedded data is frozen at export time, and seeing
new `loop_run`/`usage_event` rows means re-running the export and reloading
the page. Watching a live run otherwise means polling `ll-session query` /
`ll-issues show` by hand.

## Expected Behavior

A read-only query route mounted on FEAT-3323's `ll-artifact serve` server
exposes the live `.ll/history.db` (read-only connection, ENH-075 redaction
semantics), and a lightweight page polls it every few seconds — new rows
appear in the open browser tab without re-export or reload, and the live path
provably cannot mutate the database.

## Motivation

Today, watching an in-progress `ll-sprint`/`ll-parallel`/`ll-loop` run's
history data live means either polling `ll-session query`/`ll-issues show`
by hand, or re-running `ll-artifact dashboard` and reloading a browser tab.
Neither is a real live view. A small local server + polling page closes that
gap without pulling live-query complexity into the portable `.llat`
template/render pipeline, which is designed around single-file, offline,
`file://`-safe artifacts and should not take on a live-connection dependency.

## Proposed Solution

See Proposed Approach below (kept as the working sketch); firm up via
`/ll:refine-issue` once FEAT-3323's server exists to mount on.

## Integration Map

- `scripts/little_loops/history_reader/_base.py:78-80` — source of the
  read-only-connection pattern to reuse (`file:...?mode=ro` +
  `PRAGMA query_only = ON`; same pattern in `codequery/codegraph.py:86-88`
  and `issue_history/evolution.py:41-43`)
- `scripts/little_loops/cli/artifact/dashboard.py:76-105` — ENH-075
  redaction allowlist logic to reuse (shareable-mode column allowlist)
- `scripts/little_loops/session_store/queries.py` — existing query layer
  over history.db
- `scripts/little_loops/config-schema.json` — `artifacts` block, needs a new
  gating field for this capability
- `.issues/epics/P3-EPIC-3299-artifact-templates-deterministic-render-cheap-refresh-shared-kit.md`
  — names this as explicitly out of scope for that epic

## Implementation Steps

1. Mount a read-only query route on FEAT-3323's `ll-artifact serve` server
   (per the Scope Boundary below), reusing `history_reader/_base.py:78-80`'s
   read-only connection pattern and `cli/artifact/dashboard.py:76-105`'s
   ENH-075 redaction logic.
2. Add the polling page and the config gate (`artifacts`-adjacent block in
   `config-schema.json`, off by default).
3. Verify against a live `ll-sprint`/`ll-loop` run: new rows appear without
   reload, and write statements are rejected (`PRAGMA query_only`).

## Impact

- **Priority**: P3 - Developer-experience live view; no correctness impact,
  and sequenced behind FEAT-3323 (`depends_on`)
- **Effort**: Medium - The route and page are small, but redaction reuse,
  config gating, and schema-guard wiring span several files
- **Risk**: Low - Read-only connection against the live DB, loopback-only
  server (FEAT-3323's controls), gated off by default
- **Breaking Change**: No

## Use Case

A user kicks off a long `ll-sprint` run across several issues and wants a
browser tab open showing loop runs and usage events as they happen, without
manually re-exporting a dashboard every few minutes.

## Proposed Approach

- New capability, deliberately **not** an `.llat` template and **not** part
  of the `ll-artifact render`/`templatize`/`extract`/`refresh` pipeline —
  this is a localhost dev-server experience, not a portable artifact.
- Reuse the existing read-only connection pattern from
  `scripts/little_loops/history_reader/_base.py:78-80` (`file:...?mode=ro`,
  `PRAGMA query_only = ON`; same pattern in `codequery/codegraph.py:86-88`
  and `issue_history/evolution.py:41-43`) so serving `.ll/history.db`
  live cannot mutate it.
- Reuse the ENH-075 column-allowlist/redaction logic that `dashboard`
  already applies for `shareable` vs `local` export mode
  (`cli/artifact/dashboard.py:76-105`) — the same distinction should gate
  what a live view exposes.
- A read-only query route mounted on FEAT-3323's `ll-artifact serve` server
  (per the Scope Boundary below — FEAT-3323 owns the server; this issue
  does not stand up its own listener), plus a lightweight page that polls
  it every few seconds (SSE/websocket only if it's cheap; polling is an
  acceptable v1).
- Gate behind project config (an `artifacts`-adjacent config block,
  parallel to `artifacts.export.mode`) since it opens a live read path
  against a project's real database rather than a redacted export.

## Out of Scope

- Anything that writes to `.ll/history.db` (write-bridge stays deferred)
- Folding this into the `.llat` template kit or `ll-artifact render` pipeline
- Multi-user/remote access — this is a localhost-only dev convenience

## API/Interface

- A read-only query route mounted on FEAT-3323's `ll-artifact serve` server
  (see Scope Boundary — FEAT-3323 claims the subcommand and defines the
  server; this issue contributes the route, not an entry point).

## Acceptance Criteria

_Deferred by design: this issue's stated intent (Proposed Solution) is to
firm up via `/ll:refine-issue` once FEAT-3323's server exists to mount on.
Criteria below are the standing commitments; the refine pass will expand
them._

- [ ] Criteria to be firmed via `/ll:refine-issue` once FEAT-3323's
      `ll-artifact serve` server lands; until then this issue is
      intentionally not implementation-ready.
- [ ] (Standing) The live path is provably read-only: write statements are
      rejected (`file:...?mode=ro` + `PRAGMA query_only = ON`).
- [ ] (Standing) New `loop_run`/`usage_event` rows appear in the open
      browser tab without re-export or reload.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-3323 has already resolved
the server-ownership question ("Resolved 2026-08-26: since FEAT-3321 is still
`open` and unimplemented, this issue claims `ll-artifact serve` and defines the
server; FEAT-3321 mounts its read-only query route on the same server rather
than standing up a second listener"). If FEAT-3323 lands first, this issue
should mount its query route on FEAT-3323's server rather than defining its own
`ll-artifact serve` entry point.

**Note (2026-08-28)**: ENH-3351 landed (`94a676582`), adding
`ll-loop run --serve` / `LocalBridgeTransport`
(`scripts/little_loops/transport.py:567`) — a loopback SSE bridge for live
FSM dashboards. The product now has a second server surface alongside the
one FEAT-3323 plans to build; the mount-point decision for this issue's
query route should be confirmed when FEAT-3323 is re-refined against
ENH-3351's machinery.

## Pre-implementation Review Findings (2026-09-03)

_Verified against the live tree after ENH-3351 (`94a676582`) landed. These
supersede the Proposed Approach / Integration Map / Implementation Steps
above where they conflict; fold them in via `/ll:refine-issue` once
FEAT-3323's reconcile pass settles the server's route and token shape._

### Re-scope against what ENH-3351 already built

1. **The "deliberately not an `.llat` template" premise no longer holds.**
   `ll-loop run --serve` already serves the `dashboard.llat` template live:
   `build_dashboard_html(..., serve_context=ServeContext(events_url,
   interaction_url))` (`cli/artifact/dashboard.py:133-145`, `:155`) renders
   the same sql.js dashboard `ll-artifact dashboard` exports, plus htmx
   partials swapped in from SSE fragments (`render_live_fragment`,
   `:274-311`; wiring at `cli/loop/run.py:629-647`). This issue's page **is
   that page**, served by `ll-artifact serve` (FEAT-3323's server) instead of
   by a single loop process. Do not build a second page.
2. **Drop the arbitrary-SQL "read-only query route".** Accepting SQL text
   from the browser is a large surface, and `PRAGMA query_only` only stops
   writes (it does not constrain `ATTACH`, function calls, or resource use).
   The v1 route that reuses the most existing code is a
   **filtered-export payload route**: it returns the same table payload
   `build_dashboard_html` embeds at export time, produced by the existing
   export path with `resolve_tables(None, local_mode=...)`
   (`dashboard.py:75-105`), and the page re-loads it into the already-embedded
   sql.js on a timer. SQL stays client-side, exactly as the dashboard works
   today. SSE-triggered refresh (re-fetch on `loop_run`/`usage_event`-bearing
   events from FEAT-3323's stream) is an optional v2 on top of polling.
3. **Redaction: follow `artifacts.export.mode`, exactly as ENH-3351 does.**
   `cli/loop/run.py:636-646` already gates the served page on
   `_config.artifacts.export.mode == "local"` via `resolve_tables`. Reusing
   that call resolves the apparent conflict with FEAT-3323's "no redaction on
   the live path" decision: the SSE stream is unredacted bus data; the
   history route obeys the same shareable/local switch the dashboard export
   does. No new redaction config.
4. **One config gate, not two.** The Integration Map's "new gating field in
   the `artifacts` block" is withdrawn. FEAT-3323 defines `events.bridge`
   for the shared server; this issue adds a sub-key `events.bridge.history`
   (`bool`, default `false`) that mounts the history route. Both BUG-3192
   schema guards (`test_config_schema.py:1283-1336`, `:1346-1411`) apply to
   the new key; the dataclass field lives on FEAT-3323's bridge config
   dataclass, not a new one.
5. **`ServeContext` needs a no-interaction mode.** It currently requires
   `interaction_url` (`dashboard.py:143-144`), which the template renders as a
   Level 3 POST target. `ll-artifact serve` has no FSM executor behind it, so
   either `interaction_url: str | None = None` (template omits the interaction
   wiring when `None`) or the server 404s `POST .../interaction`. The former
   is cleaner and keeps `docs/reference/ARTIFACT_CONTROL_LEVELS.md` honest.
6. **`ARTIFACT_CONTROL_LEVELS.md` row required.** That doc makes a missing
   row a contract violation for any new render target. Add
   "`ll-artifact serve`'s history page — Level 1 (notify)" to "Declared
   levels by render target".
7. **"Provably read-only" is undercut by the cited opener.**
   `history_reader/_base.py:73` calls `ensure_db(db_path)` *before* opening
   `file:...?mode=ro` — `ensure_db` creates the file and runs migrations,
   i.e. it writes. The route must open with `mode=ro` + `PRAGMA query_only`
   **without** the `ensure_db` prelude; if the DB does not exist, the route
   returns an empty payload / clear error rather than creating it. Note
   `history.db` is WAL (`session_store/schema.py:1321`), so a `mode=ro`
   reader still needs the `-shm` file to be writable by the same user, which
   is the normal case here.
8. **Write real Acceptance Criteria.** The deferred placeholder is now
   actionable. Minimum set:
   - [ ] `GET /{token}/history` (route name per FEAT-3323's final shape)
         returns the filtered export payload for the configured tables and
         mode; a test asserts the shareable-mode payload contains only
         ENH-075 allowlisted columns and local mode contains all columns.
   - [ ] The route's connection is opened `mode=ro` + `query_only` with no
         `ensure_db` call; a test asserts a missing `history.db` is not
         created by hitting the route, and that an `INSERT` through the
         route's connection raises.
   - [ ] The served page reloads the payload on a timer and new
         `loop_run`/`usage_event` rows appear without page reload; asserted
         by a test that inserts a row between two fetches and diffs the
         payloads (the page-side swap is covered by the existing htmx kit).
   - [ ] The page renders with `ServeContext(interaction_url=None)` and emits
         no interaction POST; a test asserts the interaction wiring is absent
         from the rendered HTML.
   - [ ] Gated by `events.bridge.history` (default `false`); the route is
         404 when the key is false; schema guards pass.
   - [ ] `ARTIFACT_CONTROL_LEVELS.md` and `CLI.md` updated.

### Sequencing

- `depends_on: FEAT-3323` stands. Refine this issue (`/ll:refine-issue` →
  `/ll:confidence-check`) only after FEAT-3323's reconcile pass fixes the
  route prefix (token adoption), the `events.bridge` dataclass shape, and the
  `ARTIFACT_CONTROL_LEVELS.md` row, since every item above keys off those.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-artifact dashboard`
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — render-target level table
  (row required, see Review Findings #6)

## Status

**Open** | Created: 2026-08-26 | Priority: P3

## Verification Notes (2026-09-03)

- `scripts/little_loops/history_reader.py` no longer exists — split into a subpackage
  (commit `a25e1d688`). All 3 citations corrected to `history_reader/_base.py:78-80`.

## Session Log
- `/ll:verify-issues` - 2026-09-03T17:47:56 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:59 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-26T21:32:44 - `ce0d899f-b243-4b9b-9802-1a5047cda0de.jsonl`
