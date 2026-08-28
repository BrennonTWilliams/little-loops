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

- `scripts/little_loops/history_reader.py:440-442` — source of the
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
   (per the Scope Boundary below), reusing `history_reader.py:440-442`'s
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
  `scripts/little_loops/history_reader.py:440-442` (`file:...?mode=ro`,
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

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-artifact dashboard`

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:59 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-26T21:32:44 - `ce0d899f-b243-4b9b-9802-1a5047cda0de.jsonl`
