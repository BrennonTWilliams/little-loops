---
id: ENH-2462
title: Add explicit session_id column to issue_events, replacing inferred view
type: ENH
priority: P3
status: done
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - issue-events
  - captured
---

# ENH-2462: Add explicit session_id column to issue_events, replacing inferred view

## Summary

`issue_events` (ENH-1686 — now live-written) has no `session_id` column. The `issue_sessions` relation is a SQL VIEW inferred from timestamp overlap between `issue_events` and `message_events` — a heuristic that produces false positives (when an issue transition and an unrelated message land within seconds) and false negatives (when a long-running session straddles multiple issue transitions). Replace the inferred view with an authoritative `session_id` column captured at transition time by the EventBus producer. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #5: *"replace the inferred `issue_sessions` view with a real column captured at transition time, removing false-positive/negative joins from timestamp overlap."*

## Motivation

The current `issue_sessions` view's reliance on timestamp overlap is a known weakness:

- **False positive**: A user opens a session at 14:00:00Z, writes an unrelated message at 14:00:05Z, and an automation loop transitions `ENH-1` to `done` at 14:00:01Z. The view associates that transition with the user's session even though the agent was the actor.
- **False negative**: An `ll-parallel` worker session lasts 30 minutes and issues BUG-2, BUG-3, BUG-4 transitions within it. Timestamp-overlap derives a single session association, but the worker may have multiple distinct logical sessions.
- **No provenance**: When asking "which session closed this issue?", a probability-style association is unsafe to act on in automation (e.g., `refine-issue` might surface a session that never touched the issue).

Per `ENH-1686`'s findings, the `SQLiteTransport.send()` writes for `issue.*` events carry the necessary data via `event.get("session_id")` — we just need a column to receive it.

## Current Behavior

- `issue_events` schema: `id, ts, issue_id, transition, discovered_by, issue_type, priority, completed_date, captured_at, completed_at` (per FEAT-1623 schema, extended by ENH-1686 live-write path).
- No `session_id` column. EventBus events carry `session_id` in their payload but `SQLiteTransport.send()`'s `issue.*` branch (added in ENH-1686 / ENH-1690) drops it.
- `issue_sessions` is a SQL VIEW defined in `session_store.py` that joins on ts ranges; results are probabilistic.

## Expected Behavior

- `issue_events` gains a `session_id TEXT` column (nullable; populated for events emitted from a session-known context).
- `SQLiteTransport.send()`'s `issue.*` branch writes `session_id = event.get("session_id") or event.get("sessionId") or NULL` for each event.
- New `issue_sessions` table (or materialised view) joins on authoritative `session_id` rather than timestamp overlap; the old inferred view is renamed to `legacy_issue_sessions_ts_overlap` and documented as deprecated.
- `history_reader.related_issue_events(issue_id, session_id=None)` accepts an optional `session_id` filter; default is to return all rows, ordered by ts.
- A regression test asserts `issue_sessions` joins are now exact (assert on a known session/transition pair without ambiguity).

## Proposed Solution

### Schema migration (append to `_MIGRATIONS` in `session_store.py`)

```sql
ALTER TABLE issue_events ADD COLUMN session_id TEXT;
CREATE INDEX IF NOT EXISTS idx_issue_events_session_id ON issue_events(session_id);
```

`session_id` is nullable so legacy live-written rows preserve `NULL`. Bump `SCHEMA_VERSION`.

### Producer wiring

- Update `SQLiteTransport.send()`'s `issue.*` branch (added in ENH-1686 / ENH-1690) to capture and write `session_id`:
  ```python
  elif event_type.startswith("issue."):
      # ... existing INSERT ...
      session_id = event.get("session_id") or event.get("sessionId")
      conn.execute(
          "INSERT INTO issue_events(..., session_id) VALUES (..., ?)",
          (..., session_id),
      )
  ```
- Audit the EventBus producer sites (`scripts/little_loops/issue_lifecycle.py` lines 408/517/611/706) — confirm each `event_bus.emit(...)` call constructs the payload with `session_id` from the orchestrator context.
- `cli/issues/set_status.py` direct-write path (per ENH-2151 Decision 2 / Option C): when calling `record_issue_snapshot()` and emitting any side-effect event, pass through the current `session_id` if available.

### Materialise `issue_sessions` as a real table

Two options:

- **Option A (table)**: Materialise a real `issue_sessions` table on each new issue event via a trigger or explicit INSERT in the producer:
  ```sql
  CREATE TABLE IF NOT EXISTS issue_sessions (
    issue_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    first_ts TEXT,
    PRIMARY KEY (issue_id, session_id)
  );
  ```
- **Option B (rename the view)**: Replace the inferred view with an exact view keyed on `session_id`:
  ```sql
  CREATE VIEW issue_sessions_v2 AS
    SELECT DISTINCT issue_id, session_id
    FROM issue_events
    WHERE session_id IS NOT NULL;
  ```

Recommend Option A — materialised table populated by the producer; consumers query without recomputation; old inferred view kept as `legacy_issue_sessions_ts_overlap` for one release.

### Read API

- Extend `history_reader.related_issue_events(issue_id, session_id=None)` to filter by exact `session_id` when provided.
- Add `find_session_for_issue_transition(issue_id, transition)` returning the `session_id` recorded for that transition (or `NULL` for legacy rows).

## Acceptance Criteria

- Schema migration lands; legacy `issue_events` rows preserve `NULL` session_id.
- A new `issue.*` event emitted from `SQLiteTransport.send()` while `session_id` is in the event payload writes that `session_id` to the new column.
- `issue_sessions` view (or new materialised table) returns exact matches, no probabilistic joins.
- `history_reader.find_session_for_issue_transition(ENH-2457, 'done')` returns a session_id when the closure event was emitted from a session-known context (verified by integration test).
- The legacy `issue_sessions` view (timestamp-overlap based) is renamed/preserved but documented as legacy; consumers migrate.
- `idx_issue_events_session_id` index exists; `EXPLAIN QUERY PLAN` shows it being used for `WHERE session_id = ?` queries.
- Tests cover: schema migration, producer with and without session_id, legacy row NULL preservation, read API exact match.

## Implementation Steps

1. Add `ALTER TABLE` for `session_id` and index migration; bump `SCHEMA_VERSION`.
2. Update `SQLiteTransport.send()` `issue.*` branch to write `session_id` from event payload.
3. Audit issue event-emit sites in `issue_lifecycle.py` to ensure payloads carry `session_id`.
4. Update `cli/issues/set_status.py` direct-write path to thread `session_id`.
5. Materialise `issue_sessions` as a real table (Option A); preserve legacy inferred view as `legacy_issue_sessions_ts_overlap`.
6. Extend `history_reader.related_issue_events()` and add `find_session_for_issue_transition()`.
7. Audit `ll-deps` / `ll-history` consumer paths to use the materialised table.
8. Tests: `TestSchemaV15`, `TestIssueEventsSessionId` (writer, producer, read API), regression test for legacy rows.
9. Docs: `docs/ARCHITECTURE.md` schema row; `docs/reference/API.md` for the new read APIs.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 5 ("Issue ↔ session linkage — inferred only"), §3 ranked recommendation #5
- `.issues/enhancements/P2-ENH-1686-live-write-issue-events-to-history-db.md` — established `SQLiteTransport` issue-event writer site
- `scripts/little_loops/issue_lifecycle.py` — emit sites at lines 408, 517, 611, 706
- `scripts/little_loops/cli/issues/set_status.py` — direct-write path (per ENH-2151 Decision 2)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; producer/consumer flow |
| `docs/reference/API.md` | `history_reader` module reference (extended functions) |

## Status

**Done** | Created: 2026-07-02 | Completed: 2026-07-03 | Priority: P3

Implemented as schema v16: `issue_events.session_id TEXT` + `idx_issue_events_session_id`.
`SQLiteTransport.send()` writes `session_id` from the event payload (snake_case or camelCase);
all six `issue_lifecycle.py` emit sites now stamp `session_id` via the new
`session_log.get_current_session_id()` (CLAUDE_SESSION_ID env → newest session JSONL stem,
best-effort). Instead of Option A's materialised table, the `issue_sessions` relation was
rebuilt as a VIEW that prefers exact `session_id` joins and falls back to the old
timestamp-overlap inference (preserved as `legacy_issue_sessions_ts_overlap`, deprecated) only
for issues with no authoritative rows — this keeps every existing consumer
(`sessions_for_issue`, `issue_effort`, `lookup_session_metadata`, `condensed_nodes_for_issue`)
working with zero data backfill while making new rows exact. Read side:
`related_issue_events(session_id=...)` filter + `find_session_for_issue_transition()`.
`cli/issues/set_status.py` needed no change — its direct-write path writes `issue_snapshots`
only, not `issue_events`. Tests: `TestSchemaV16IssueSessionId` (incl. EXPLAIN QUERY PLAN index
use and v14-upgrade NULL preservation), reader tests in test_history_reader.py.

## Session Log
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
