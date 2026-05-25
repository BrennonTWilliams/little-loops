---
id: ENH-1690
type: ENH
priority: P2
status: done
parent: ENH-1686
discovered_date: 2026-05-24
completed_at: 2026-05-25T00:41:46Z
labels:
- enhancement
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1690: Extend SQLiteTransport to Handle Issue Events

## Summary

Extend `SQLiteTransport.send()` in `session_store.py` to handle `issue.*` event types (currently all non-loop events are silently dropped), add a unique constraint migration for deduplication, and cover the transport layer changes with unit tests. This is the prerequisite for ENH-1691.

## Current Behavior

`SQLiteTransport.send()` returns early for any event type not in `_LOOP_EVENT_TYPES` (a frozenset of FSM event names). All `issue.*` events are silently discarded regardless of content. `_backfill_issues()` uses a plain `INSERT` without `INSERT OR IGNORE`, so calling backfill multiple times on the same DB produces duplicate rows in `issue_events`.

## Expected Behavior

`SQLiteTransport.send()` handles `issue.*` event types by inserting rows into `issue_events` with correct `transition` values derived by a new `_derive_transition()` helper. `_backfill_issues()` uses `INSERT OR IGNORE` backed by a unique index on `(issue_id, transition)`, preventing duplicate rows. FTS `_index()` is called for live-written issue events so `ll-session search --fts` finds them.

## Impact

- **Priority**: P2 — Prerequisite for ENH-1691; without this fix live-write issue events produce no rows in `issue_events`
- **Effort**: Medium — Small, focused changes in a single file plus schema migration and new unit tests
- **Risk**: Low — Additive change; existing `_LOOP_EVENT_TYPES` branch is untouched; `INSERT OR IGNORE` is safe even if index is absent
- **Breaking Change**: No (schema migration is additive — constraint index only)

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Confirmed line numbers**: `SCHEMA_VERSION = 2` at line 42; early-return gate `if event_type not in _LOOP_EVENT_TYPES: return` at lines 331–333; `_backfill_issues()` plain `INSERT` at lines 448–464; `_MIGRATIONS` has exactly 2 entries (indices 0 and 1) — appending at index 2 + bumping `SCHEMA_VERSION` to `3` follows the established pattern.
- **`_derive_transition` does not exist** anywhere in the codebase; `session_store.py` and all other modules were searched — it must be created fresh.
- **`issue.failure_captured` event type**: `issue_lifecycle.py` emits a fourth live event `"issue.failure_captured"` (a failure sub-issue was created) that is not in the mapping table. Add a fallback mapping such as `"failure_captured"` or route it to `"open"` if only terminal transitions matter; alternatively, return `event_type.split(".", 1)[1]` as the default for any unmapped type so no future events are silently mis-mapped.
- **`_index()` `content` field richness**: `_backfill_issues()` builds `content=f"{issue_id} {status} {issue_type or ''}"` for better FTS coverage. The live-write `_index()` call should be at least as rich — e.g. `content=f"{event.get('issue_id', '')} {event.get('issue_type', '')}"` — so `ll-session search --fts` matches on type as well as ID.
- **`completed_date` column omission**: The proposed `INSERT` in Step 0 omits the `completed_date` column (a v2 column populated by `_backfill_issues()` from frontmatter). This is intentional for live events — `scan_completed_issues_from_db()` falls back to `completed_at.date()` when `completed_date IS NULL`, so omitting it from the live-write INSERT is safe.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `session_store.py` module docstring — replace "writing FSM events to `loop_events`" to also mention `issue_events` (in-scope: this file is already being modified)
- Handle `None` for optional columns — `issue_lifecycle.py` live payloads omit `issue_type`, `priority`, `captured_at`, `completed_at`; confirm all four use `event.get(...)` with `None` default in the INSERT (the Step 0 snippet already does this, but verify)
- Verify `TestSchemaV2.test_v1_db_upgrades_to_v2_idempotently` passes after `SCHEMA_VERSION` bump — the test inserts no `issue_events` rows so no unique-constraint conflict; should pass, but confirm in CI
- Add `CHANGELOG.md` entry for schema v2→v3 migration — follow the ENH-1621 entry pattern; do not use `[Unreleased]`
- Add end-to-end coverage in `test_transport.py` — emit `{"event": "issue.completed", "issue_id": "ENH-99", ...}` through `bus.emit()` after `wire_transports()`, assert row appears in `recent(db, kind="issue")`

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `SQLiteTransport.send()` (lines 326–365), `_backfill_issues()` (lines 418–474), `_MIGRATIONS` (lines 78–147), `SCHEMA_VERSION` (line 42)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/parsing.py:351–418` — `scan_completed_issues_from_db()` reads `WHERE transition = 'done'`; live-write rows must use exactly `"done"` to appear here
- `scripts/little_loops/transport.py` — `wire_transports()` wires `SQLiteTransport` onto `EventBus`; no change needed for ENH-1690 (wiring is ENH-1691 scope)
- `scripts/little_loops/events.py:117–138` — `EventBus.emit()` routes to `transport.send(event)`; this is the call path that will exercise the new `issue.*` branch

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_lifecycle.py` — **event source**: emits `issue.completed`, `issue.closed`, `issue.deferred`, `issue.failure_captured`; live payloads do NOT include `issue_type`, `priority`, `captured_at`, or `completed_at` (only backfill-sourced rows carry those) — `_derive_transition()` and the INSERT must handle `None` for these optional columns
- `scripts/little_loops/cli/loop/run.py` — calls `wire_transports(executor.event_bus, ...)` — no code change needed; runtime behavior changes when `issue.*` events start writing rows after ENH-1690
- `scripts/little_loops/cli/loop/lifecycle.py` — calls `wire_transports()` — same as above
- `scripts/little_loops/cli/parallel.py` — calls `wire_transports()` — same as above
- `scripts/little_loops/cli/sprint/run.py` — calls `wire_transports()` — same as above
- `scripts/little_loops/issue_history/__init__.py` — exports `scan_completed_issues_from_db` in public API; downstream consumers of this export depend on `transition = 'done'` rows existing

### Tests
- `scripts/tests/test_session_store.py` — `TestSQLiteTransport` (lines 115–156); `TestBackfill` (lines 209–273); `TestSchemaV2` (lines 360–407) shows the v1→v2 upgrade test pattern for reference

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_transport.py` — `TestWireTransports.test_sqlite_registered_by_name` (line 244): currently emits only a loop event; add a complementary test emitting `{"event": "issue.completed", ...}` through `bus.emit()` after `wire_transports()` and asserting `recent(db, kind="issue")` returns a row (end-to-end coverage of the new branch)
- `scripts/tests/test_issue_history_parsing.py` — `TestScanCompletedIssuesFromDb` calls `backfill()` once; `INSERT OR IGNORE` change is invisible to single-call tests, but run in CI to confirm no regression
- `scripts/tests/test_issue_lifecycle.py` — **reference only** (no changes needed): documents live event payload shapes — `issue.completed` payload contains `ts`, `issue_id`, `file_path` but omits `issue_type`, `priority`, `captured_at`, `completed_at`; the new `send()` INSERT must tolerate `None` for those columns
- `TestSchemaV2.test_v1_db_upgrades_to_v2_idempotently` (line 360 in `test_session_store.py`) — **at-risk**: asserts `int(version) == SCHEMA_VERSION` via the imported constant; after the v2→v3 bump the assertion will pass (no duplicate rows in test data so the v3 `CREATE UNIQUE INDEX` migration succeeds), but verify explicitly in CI

### Similar Patterns
- `session_store.py:352–362` — `_index()` call inside `send()` for loop events (model for the live-write `_index()` call)
- `session_store.py:464–472` — `_index()` call inside `_backfill_issues()` with `content=f"{issue_id} {status} {issue_type or ''}"` (richer `content` than the bare `issue_id` in Step 0's snippet — the live-write `_index()` call should match this richness)
- `session_store.py:169–173` — `ON CONFLICT(key) DO UPDATE` pattern in `_apply_migrations()`; closest existing dedup-style write before `INSERT OR IGNORE` is added

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add a concrete version entry for the schema v2→v3 migration (per project convention, do not use `[Unreleased]`; follow the ENH-1621 entry pattern)
- `scripts/little_loops/session_store.py` module docstring — says "SQLiteTransport: EventBus Transport sink writing FSM events to `loop_events`"; update to also mention `issue_events` (in-scope: this file is already being modified)
- `docs/reference/CONFIGURATION.md` — `events.sqlite` section describes "FSM loop events only"; should be updated to include `issue.*` events [deferred to ENH-1691 per scope]
- `docs/reference/CLI.md` — `### ll-history` section implies `ll-session backfill` is required to populate `issue_events`; should note live writes as an alternative path [deferred to ENH-1691 per scope]

## Files to Modify

- `scripts/little_loops/session_store.py` — `SQLiteTransport.send()`, `_backfill_issues()`, `_MIGRATIONS`, `SCHEMA_VERSION`

## Tests

Add to `scripts/tests/test_session_store.py` in `TestSQLiteTransport`:

- **`test_records_issue_event`**: Follow pattern of `test_records_loop_event` (line 123). `transport.send({"event": "issue.completed", "ts": "...", "issue_id": "ENH-99", ...})` → `assert recent(db, kind="issue")[0]["issue_id"] == "ENH-99"`.
- **`test_issue_event_transition_mapping`**: Verify each `issue.*` type produces the correct `transition` value (especially `issue.completed` → `"done"`).
- **`test_loop_event_does_not_create_issue_row`**: Verify existing `_LOOP_EVENT_TYPES` events still route to `loop_events` only after the new branch is added.
- **`TestBackfill` dedup test**: Call `backfill()` twice on same DB with same issue file, assert single row after second call (validates `INSERT OR IGNORE`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`test_records_loop_event` confirmed at lines 123–131**: fixture is `tmp_path` only; pattern is `SQLiteTransport(db)` → `transport.send({...})` → `transport.close()` → `recent(db, kind="loop")`. Mirror exactly for `kind="issue"`.
- **`test_ignores_unrecognized_event` at lines 133–138**: this existing test sends `{"event": "action_output", ...}` and asserts `recent(db, kind="loop") == []`. After the new `elif event_type.startswith("issue.")` branch is added, `"action_output"` still passes neither the frozenset check nor the `startswith("issue.")` check, so this test should continue to pass without modification — confirm in CI.
- **`TestSchemaV2` at lines 360–407**: shows the upgrade-test pattern — bootstrap a v1 schema manually, call `ensure_db(db)`, then assert new columns exist. A `TestSchemaV3` test should follow this pattern to verify the unique index is applied when upgrading from v2.
- **No existing dedup test in `TestBackfill`**: `test_backfill_issues` at lines 212–222 calls `backfill()` once. The new dedup test should call `backfill()` twice on the same `tmp_path` DB and assert `len(recent(db, kind="issue")) == 1`.

## Acceptance Criteria

- [ ] `transport.send({"event": "issue.completed", "issue_id": "ENH-99", ...})` produces a row in `issue_events` with `transition = "done"`
- [ ] Calling `backfill()` twice on the same DB produces no duplicate rows
- [ ] Existing loop event tests still pass (no regression)
- [ ] `ll-session search --fts` can find live-written issue events

## Resolution

Implemented in `session_store.py` (2026-05-25):

- Added `_ISSUE_TRANSITION_MAP` and `_derive_transition()` helper mapping `issue.*` event types to canonical status strings
- Added `elif event_type.startswith("issue.")` branch in `SQLiteTransport.send()` with `INSERT OR IGNORE` and `_index()` call for FTS coverage
- Changed `_backfill_issues()` to use `INSERT OR IGNORE` for idempotent backfill
- Added v3 migration: `CREATE UNIQUE INDEX idx_issue_events_dedup ON issue_events(issue_id, transition)`
- Bumped `SCHEMA_VERSION` from 2 → 3
- Updated module docstring to mention `issue_events`
- Added tests in `TestDeriveTransition`, `TestSQLiteTransportIssueEvents`, `TestSchemaV3`, `TestBackfillDedup`
- Added end-to-end test in `test_transport.py::TestWireTransports::test_sqlite_records_issue_event_end_to_end`
- All 7720 tests pass; lint and mypy clean

## Session Log
- `/ll:ready-issue` - 2026-05-25T00:33:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf859df2-ced2-4fbc-99a8-d11080c94f8d.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ff68644-f610-4773-bcdb-dacc9c11d51c.jsonl`
- `/ll:wire-issue` - 2026-05-25T00:28:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86f56276-46cd-4119-ba95-4532109f6d87.jsonl`
- `/ll:refine-issue` - 2026-05-25T00:21:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/18ee2016-452f-4c6f-9b7f-f3f22047abd0.jsonl`
- `/ll:issue-size-review` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/898f7f18-27df-4e97-81bc-d975051952e8.jsonl`
- `/ll:manage-issue` - 2026-05-25T00:41:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
