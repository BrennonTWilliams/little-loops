---
id: FEAT-3321
type: FEAT
title: Local realtime web UI for live-querying history.db
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T01:39:46Z'
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

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

Today, watching an in-progress `ll-sprint`/`ll-parallel`/`ll-loop` run's
history data live means either polling `ll-session query`/`ll-issues show`
by hand, or re-running `ll-artifact dashboard` and reloading a browser tab.
Neither is a real live view. A small local server + polling page closes that
gap without pulling live-query complexity into the portable `.llat`
template/render pipeline, which is designed around single-file, offline,
`file://`-safe artifacts and should not take on a live-connection dependency.

## Proposed Solution

TBD - requires investigation

## Integration Map

- `scripts/little_loops/cli/artifact/dashboard.py` — source of the
  read-only-connection pattern and ENH-075 redaction logic to reuse
- `scripts/little_loops/session_store/queries.py` — existing query layer
  over history.db
- `scripts/little_loops/config-schema.json` — `artifacts` block, needs a new
  gating field for this capability
- `.issues/epics/P3-EPIC-3299-artifact-templates-deterministic-render-cheap-refresh-shared-kit.md`
  — names this as explicitly out of scope for that epic

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Use Case

A user kicks off a long `ll-sprint` run across several issues and wants a
browser tab open showing loop runs and usage events as they happen, without
manually re-exporting a dashboard every few minutes.

## Proposed Approach

- New capability, deliberately **not** an `.llat` template and **not** part
  of the `ll-artifact render`/`templatize`/`extract`/`refresh` pipeline —
  this is a localhost dev-server experience, not a portable artifact.
- Reuse the existing read-only connection pattern from
  `scripts/little_loops/cli/artifact/dashboard.py` (`ATTACH` +
  `file:...?mode=ro`, `PRAGMA query_only = 1`) so serving `.ll/history.db`
  live cannot mutate it.
- Reuse the ENH-075 column-allowlist/redaction logic that `dashboard`
  already applies for `shareable` vs `local` export mode — the same
  distinction should gate what a live view exposes.
- A minimal local HTTP server exposing a read-only query endpoint over the
  live database, plus a lightweight page that polls it every few seconds
  (SSE/websocket only if it's cheap; polling is an acceptable v1).
- Gate behind project config (an `artifacts`-adjacent config block,
  parallel to `artifacts.export.mode`) since it opens a live read path
  against a project's real database rather than a redacted export.

## Out of Scope

- Anything that writes to `.ll/history.db` (write-bridge stays deferred/未定)
- Folding this into the `.llat` template kit or `ll-artifact render` pipeline
- Multi-user/remote access — this is a localhost-only dev convenience

## API/Interface

- New subcommand, working name `ll-artifact serve` (alternatively a separate
  `ll-history-server` entry point) — naming is a decision for whoever picks
  this up, not fixed here.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-artifact dashboard`

## Status

**Open** | Created: 2026-08-26 | Priority: P3
