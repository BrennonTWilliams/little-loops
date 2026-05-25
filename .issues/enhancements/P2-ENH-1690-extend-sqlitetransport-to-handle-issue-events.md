---
id: ENH-1690
type: ENH
priority: P2
status: open
parent: ENH-1686
discovered_date: 2026-05-24
labels:
- enhancement
---

# ENH-1690: Extend SQLiteTransport to Handle Issue Events

## Summary

Extend `SQLiteTransport.send()` in `session_store.py` to handle `issue.*` event types (currently all non-loop events are silently dropped), add a unique constraint migration for deduplication, and cover the transport layer changes with unit tests. This is the prerequisite for ENH-1691.

## Parent Issue

Decomposed from ENH-1686: Live-Write Issue Events to history.db (Eliminate Backfill Requirement)

## Motivation

`SQLiteTransport.send()` at `session_store.py:332` returns early for any event type not in `_LOOP_EVENT_TYPES`. Since `_LOOP_EVENT_TYPES` contains only FSM event names (`loop_start`, `state_enter`, etc.), all `issue.*` events are silently discarded — even after the lifecycle wiring in ENH-1691 is complete. Without this fix, live writes produce no rows in `issue_events`.

## Scope

- **In scope**: `SQLiteTransport.send()` `issue.*` branch; `_backfill_issues` `INSERT OR IGNORE` change; unique constraint migration (`SCHEMA_VERSION` 2→3); FTS `_index()` call for live writes; unit tests for the transport layer.
- **Out of scope**: lifecycle wiring (ENH-1691); parallel orchestrator path; doc updates (ENH-1691).

## Implementation Steps

### Step 0 — Fix `SQLiteTransport.send()` (`session_store.py:326`)

Add an `elif event_type.startswith("issue."):` branch before the `return` at line 332:

```python
elif event_type.startswith("issue."):
    transition = _derive_transition(event_type, event)  # e.g. "issue.completed" → "done"
    conn.execute(
        "INSERT OR IGNORE INTO issue_events(ts, issue_id, transition, discovered_by, "
        "issue_type, priority, captured_at, completed_at) VALUES (?,?,?,?,?,?,?,?)",
        (event.get("ts"), event.get("issue_id"), transition,
         event.get("discovered_by"), event.get("issue_type"),
         event.get("priority"), event.get("captured_at"), event.get("completed_at")),
    )
    _index(conn, content=event.get("issue_id", ""), kind="issue",
           ref=str(event.get("issue_id", "")),
           anchor=event.get("issue_file", ""), ts=event.get("ts", ""))
```

### Step 7 — `transition` value alignment (critical)

`scan_completed_issues_from_db()` in `issue_history/parsing.py` queries `WHERE transition = 'done'`. The new `send()` branch must derive `transition` from the event type:
- `issue.completed` → `"done"`
- `issue.closed` → `"done"`
- `issue.deferred` → `"deferred"`
- `issue.skipped` → `"cancelled"`
- `issue.created` → `"open"`
- `issue.started` → `"in_progress"`

Add a helper `_derive_transition(event_type: str, event: dict) -> str` in `session_store.py`.

### Step 4 — Update `_backfill_issues()` (`session_store.py:448`)

Change `INSERT INTO issue_events(...)` → `INSERT OR IGNORE INTO issue_events(...)`. The unique constraint from Step 6 makes this effective.

### Step 6 — Add schema migration (`session_store.py:_MIGRATIONS`)

Append migration at index 2 (after current v2 migration at index 1):
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_events_dedup ON issue_events(issue_id, transition);
```
Bump `SCHEMA_VERSION` from `2` → `3`.

> Note: Scope says "no schema changes" — this is a constraint index addition (not a column change); it enables `INSERT OR IGNORE` deduplication and is required for the dedup requirement to work.

### Step: FTS `_index()` call

The live-write path in `send()` must call `_index()` alongside the INSERT, matching the pattern in `_backfill_issues()`:
```python
_index(conn, content=event.get("issue_id", ""), kind="issue",
       ref=str(event.get("issue_id", "")),
       anchor=event.get("issue_file", ""), ts=event.get("ts", ""))
```
Without this, `ll-session search --fts` misses live-written issue events.

## Files to Modify

- `scripts/little_loops/session_store.py` — `SQLiteTransport.send()`, `_backfill_issues()`, `_MIGRATIONS`, `SCHEMA_VERSION`

## Tests

Add to `scripts/tests/test_session_store.py` in `TestSQLiteTransport`:

- **`test_records_issue_event`**: Follow pattern of `test_records_loop_event` (line 123). `transport.send({"event": "issue.completed", "ts": "...", "issue_id": "ENH-99", ...})` → `assert recent(db, kind="issue")[0]["issue_id"] == "ENH-99"`.
- **`test_issue_event_transition_mapping`**: Verify each `issue.*` type produces the correct `transition` value (especially `issue.completed` → `"done"`).
- **`test_loop_event_does_not_create_issue_row`**: Verify existing `_LOOP_EVENT_TYPES` events still route to `loop_events` only after the new branch is added.
- **`TestBackfill` dedup test**: Call `backfill()` twice on same DB with same issue file, assert single row after second call (validates `INSERT OR IGNORE`).

## Acceptance Criteria

- [ ] `transport.send({"event": "issue.completed", "issue_id": "ENH-99", ...})` produces a row in `issue_events` with `transition = "done"`
- [ ] Calling `backfill()` twice on the same DB produces no duplicate rows
- [ ] Existing loop event tests still pass (no regression)
- [ ] `ll-session search --fts` can find live-written issue events

## Session Log
- `/ll:issue-size-review` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/898f7f18-27df-4e97-81bc-d975051952e8.jsonl`
