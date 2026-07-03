---
id: ENH-2465
title: Periodic epic-progress snapshots into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - epics
  - captured
---

# ENH-2465: Periodic epic-progress snapshots into history.db

## Summary

`ll-issues epic-progress <EPIC>` recomputes from live issue state every time — there's no historical snapshot. Once an EPIC closes (or a child moves from `open` → `in_progress` → `done`), the previous state of "what was open last Tuesday at 14:00?" is no longer recoverable from the DB. Add an `epic_progress_snapshots` table populated at child-issue transition time (and on `ll-issues epic-progress` invocation) carrying `(ts, epic_id, by_status_json, total_children, open_count, in_progress_count, done_count, deferred_count, blocked_count, cancelled_count, completion_fraction)`. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #8: *"periodically (e.g. on `epic-progress` invocation, or on child issue transitions) snapshot `by_status` counts so epic velocity is queryable historically, not just as a point-in-time computation."*

## Motivation

Epic velocity is one of the project-management signals most users ask for ("how fast does this EPIC close?"), but it cannot be reconstructed after the fact:

- **No "was BUG-3 open two weeks ago?" answer** — once an issue transitions to `done`, its status history is captured in `issue_events` (per ENH-1686), but a rollup-by-status view is missing.
- **No progress-over-time line chart** — `ll-history` cannot render an EPIC's burndown without the snapshot.
- **No trend anomaly detection** — "this EPIC went 30 days with no closes" requires historical data.
- **Sibling cache/calc** — `ll-sprint` consumes epic progress; if that consumer crashes mid-computation, the snapshot is the fallback.

The `issue_events` schema (ENH-1686) gives raw transition events; a rollup table aggregates them.

## Current Behavior

- `ll-issues epic-progress <EPIC>` reads current issue state from `.issues/<type>/*.md` files; computes `by_status` counts; returns a rollup. No persistence.
- `ll-issues show <EPIC>` lists children and their current statuses.
- `ll-session search --fts "<epic title>"` finds the EPIC file but no historical view.
- No "epic was 25% done last week" data.

## Expected Behavior

- `epic_progress_snapshots` table exists in schema v15+ with columns: `id`, `ts`, `epic_id`, `total_children`, `open_count`, `in_progress_count`, `done_count`, `deferred_count`, `blocked_count`, `cancelled_count`, `completion_fraction REAL`.
- A snapshot is written on each child issue transition (via the `issue.*` live-write path) keyed by parent epic; idempotent on `(epic_id, ts)` for within-second transitions.
- A snapshot is written on every `ll-issues epic-progress <EPIC>` invocation, regardless of outcome.
- `history_reader.epic_progress_history(epic_id, since=None)` returns a time-series of snapshots for an EPIC.
- `ll-sprint` and `ll-history` consumers can read the snapshot stream without recomputing on each call.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS epic_progress_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    epic_id TEXT NOT NULL,
    total_children INTEGER NOT NULL,
    open_count INTEGER,
    in_progress_count INTEGER,
    done_count INTEGER,
    deferred_count INTEGER,
    blocked_count INTEGER,
    cancelled_count INTEGER,
    completion_fraction REAL
);
CREATE INDEX IF NOT EXISTS idx_epic_snapshots_epic_id ON epic_progress_snapshots(epic_id);
CREATE INDEX IF NOT EXISTS idx_epic_snapshots_ts ON epic_progress_snapshots(ts);
```

Bump `SCHEMA_VERSION`. Add `"epic_progress"` to `_VALID_KINDS` and `"epic_progress": "epic_progress_snapshots"` to `_KIND_TABLE`.

### Producer wiring

- In `SQLiteTransport.send()` `issue.*` branch (per ENH-1686 / ENH-1690 / ENH-2462 — sibling work on this exact emit site), after the `issue_events` insert, walk the issue's `parent`/`relates_to` chain, find any ancestor EPIC, and compute the EPIC's current rollup. Insert a row into `epic_progress_snapshots`.
- In `scripts/little_loops/cli/issues/epic_progress.py` (the `cmd_epic_progress()` handler), on every invocation, after computing the rollup, write a snapshot row.
- Both writers use `contextlib.suppress(Exception)`. Walks degrade gracefully if `.issues/` files are missing or the parent chain is broken.

### Computation source

- Walk current `.issues/<type>/<epic-id>-*.md` files for `relates_to:` matches against the epic.
- Each child file's `status:` frontmatter drives the by_status count.
- For performance: cache the rollup calc in `scripts/little_loops/issue_progress.py` and re-use; existing `ll-issues epic-progress` already does this.

### Read API

Add to `history_reader.py`:
- `epic_progress_history(epic_id, since=None, limit=200)` — time-series for an EPIC.
- `epic_progress_latest(epic_id)` — most-recent snapshot.
- `epic_velocity(epic_id, window_days=14)` — derived rate (commits per day or done-count delta per day).

### CLI surface

- `ll-issues epic-progress --history <EPIC>` — print snapshot time-series.
- `ll-history epic-velocity --since 30d` — roll-up across all epics.

## Acceptance Criteria

- Schema migration lands; `epic_progress_snapshots` table exists.
- A child transition (`open` → `in_progress` → `done`) writes a new snapshot row for the parent EPIC each time.
- `ll-issues epic-progress <EPIC>` writes a snapshot row on every invocation.
- `history_reader.epic_progress_history(EPIC-1707)` returns the time-series.
- `ll-sprint` and `ll-history` consumers can switch from "compute on every call" to "read latest snapshot" with no observable behavior change.
- Idempotent on `(epic_id, ts)` for within-second transitions (use `INSERT OR IGNORE` with appropriate uniqueness constraint or de-dupe at write).
- Tests cover: schema migration, transition-triggered write, explicit-invocation write, read API, idempotency, graceful degradation when files missing.

## Implementation Steps

1. Schema migration for `epic_progress_snapshots`; bump `SCHEMA_VERSION`.
2. Add `"epic_progress"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_epic_progress_snapshot()` and `_backfill_epic_progress_snapshots()` in `session_store.py`.
4. Wire `SQLiteTransport.send()` `issue.*` branch to call snapshotter after each `issue_events` insert.
5. Wire `cmd_epic_progress()` to call snapshotter at end of each invocation.
6. Extend `history_reader.epic_progress_history()` (and `epic_progress_latest`, `epic_velocity`).
7. CLI: `--history` flag on `epic-progress`; new `ll-history epic-velocity` subcommand.
8. Update `ll-sprint` to read latest snapshot when computing epic rollups (fallback: existing on-the-fly compute).
9. Tests: `TestRecordEpicSnapshot`, `TestSchemaV15` (or higher), `TestEpicProgressHistoryRead`, idempotency on rapid transitions.
10. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md` updates, `docs/reference/CLI.md` for `--history` flag.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 7 ("Epic progress over time"), §3 ranked recommendation #8
- `scripts/little_loops/issue_progress.py` — existing `ll-issues epic-progress` computation; reference for rollup logic
- `scripts/little_loops/cli/issues/epic_progress.py` — invocation site
- `scripts/little_loops/session_store.py:SQLiteTransport.send()` — shared `issue.*` emit site (sibling of ENH-2462)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` extensions |
| `docs/reference/CLI.md` | New flags |

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
