---
id: BUG-3758
type: BUG
title: SQLite route events discard both transition endpoints
priority: P3
status: open
discovered_by: capture-issue
discovered_date: '2026-10-06'
captured_at: '2026-10-06T09:02:29Z'
labels:
- telemetry
- transport
- history-db
relates_to:
- BUG-3755
---

# BUG-3758: SQLite route events discard both transition endpoints

## Summary

`FSMExecutor` emits `route` events with `from`, `to`, and `reason`, but `SQLiteTransport.send` reads only `state`. Production route events have no `state` field, so persisted route rows retain neither transition endpoint. This is separate from BUG-3755's loop-name lookup defect and does not block that identity fix.

## Current Behavior

- `scripts/little_loops/fsm/executor.py:869` and `:948` emit route payloads with `from`/`to` and no `state`; ordinary routing uses the same shape.
- `scripts/little_loops/session_store/writers.py:3088` reads `state` and `:3098` inserts only `ts, loop_name, state, transition, retries`. The stored `transition` is the event type (`route`), not the destination.
- `scripts/little_loops/session_store/schema.py:163` defines `loop_events` without a target-state or general payload/details column. Its current version is 59.
- FTS content at `scripts/little_loops/session_store/writers.py:3110` includes name, state, and event type; neither endpoint of a production route is searchable today. OTel already records route payload attributes and needs no endpoint-storage change.

## Expected Behavior

A live SQLite route row keeps its source in `state` and destination in nullable `to_state`, while `transition` remains `route`. The canonical `from` value takes precedence over a legacy `state` field; legacy state-only route payloads keep that source when `from` is absent/null. Missing destinations stay NULL. Non-route rows and historical rows have NULL `to_state`.

Both endpoints are included in route FTS content. Existing FTS identity and anchor conventions remain compatible. Existing snapshot backfill keeps its raw current-state meaning and leaves the new target column NULL.

## Motivation

Stored route events cannot answer which edge was taken, limiting transition diagnosis and search. This is a P3 diagnostics defect in an optional sink. It does not change loop execution or metrics derived from `loop_runs`.

## Proposed Solution

Persist route source and target together, with a nullable `to_state TEXT` column added by one appended `_MIGRATIONS` entry. No existing v59 field can hold the destination without changing the meanings of `transition` or `retries`; searchable FTS text alone cannot support structured endpoint queries. A new column is therefore justified for this separate fix.

Determine the next schema version at implementation time. At review HEAD `3286729a2`, that is v60; do not overwrite a migration added by another issue. Regenerate `schema_manifest.json` and update current-version assertions and relevant history/schema documentation together. Historical rows stay NULL; no inferred endpoint backfill is part of this change.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/writers.py` — source/target mapping, insert, and route FTS content.
- `scripts/little_loops/session_store/schema.py` — next additive migration and matching `SCHEMA_VERSION`.
- `scripts/little_loops/session_store/schema_manifest.json` — regenerate with the recipe in `TestSchemaManifest` in `scripts/tests/test_session_store_schema.py`.
- `scripts/tests/test_session_store_schema.py` and `scripts/tests/test_session_store_writers.py` — migration and route semantics coverage, plus current-version assertions.
- `scripts/tests/test_assistant_messages.py` and `scripts/tests/test_bug3736_usage_replay_holds.py` — version assertions; the latter also has `_downgrade_and_remigrate` (`:99`) that currently lowers meta to v58 without removing later columns.
- A producer-to-sink regression module under `scripts/tests/` — source/target persistence and searchable endpoints. Pin `LL_HISTORY_DB` and loop paths to temporary locations; close transports even if execution fails.
- `docs/reference/EVENT-SCHEMA.md`, `docs/reference/API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, and release notes — route storage contract and migration impact.

### Dependent Files

- `scripts/little_loops/session_store/remote_schema.py:222` — opens never migrate; writes require the exact installed version. New clients against an old store need explicit `ll-session migrate`; older clients also refuse writes after the store is upgraded. Coordinate remote-client upgrades and migration; ordinary additive local-schema compatibility does not remove this operational requirement.
- `scripts/little_loops/session_store/queries.py` — recent/export projections use `SELECT *`, so the column surfaces without hand-written reader changes; verify this behavior.
- `scripts/little_loops/session_store/lifecycle.py` — `_REBUILD_TABLES` and `_REBUILD_SEARCH_KINDS` omit event-level loop storage and its FTS rows; existing historical rows are not repaired by rebuild.
- `scripts/little_loops/session_store/writers.py:3547` — snapshot backfill uses explicit old-column inserts; new target defaults to NULL.
- `scripts/tests/test_history_store_chokepoint_gate.py` scans production files under `scripts/little_loops/`, not test files. Temporary test DB inspection with `sqlite3.connect` is allowed; production opens still use the backend chokepoint.

### Existing Draft

Reference only: branch `fix/BUG-3755-transport-loop-key` at `b37b20a05` in `.claude/worktrees/bug-3755`. Commit `256ab0ad1` mixes identity resolution and source-state recovery; `b37b20a05` adds `to_state` and the migration. Reconcile relevant portions with the final source-state precedence, FTS, migration, and remote-policy criteria. The draft is not a completed implementation on main and must not be merged wholesale as BUG-3755.

## Program Design

### Types

- `loop_events.to_state: TEXT NULL` — the destination of a route, otherwise NULL.
- Route source: canonical `event["from"]` when non-null, else legacy `event["state"]`.
- `transition` remains an event-type string; `retries` remains an integer/NULL.

### Signatures

- `SQLiteTransport.send(self, event: dict[str, Any]) -> None`

The writer keeps its signature and best-effort failure behavior. Route mapping does not mutate the shared input event.

### Call Path

`FSMExecutor._emit("route", ...)` → `PersistentExecutor._handle_event` → `EventBus.emit` → `SQLiteTransport.send` → structured row and FTS content. Schema changes use the existing local/remote migration paths.

## Implementation Steps

1. The source/target storage contract above holds for live and legacy payloads, with FTS searchable endpoints and non-route behavior preserved.
2. The next additive migration upgrades a genuine predecessor DB, keeps legacy rows nullable, and stays aligned with the manifest, replay fixtures, and current-version checks.
3. Temporary producer-to-sink, migration, export, and remote-policy tests establish the acceptance criteria; the full local suite passes.
4. History and release documentation explain the new mapping and explicit remote migration requirement.

## Impact

- **Priority**: P3 — ongoing loss of diagnostic transition data in an optional sink.
- **Effort**: Small/medium — mapping plus schema, FTS, fixtures, and documentation.
- **Risk**: Moderate operational impact for remote stores because exact-version write policy requires coordinated upgrades.
- **Breaking Change**: Additive local schema; remote writers require version coordination.

## Steps to Reproduce

1. Use a temporary history DB and a real `PersistentExecutor` with an injected deterministic action runner for a `work` → `done` loop.
2. Attach `SQLiteTransport` to its event bus and capture the producer events.
3. Confirm the route payload has `from=work` and `to=done`.
4. Read `loop_events` through the session-store API: its route row has `state` NULL and no target column. Search content also omits both endpoints.

## Root Cause

- **File**: `scripts/little_loops/session_store/writers.py`
- **Anchor**: `SQLiteTransport.send`, loop-event branch (`:3086-3117`)
- **Cause**: the writer assumes a common `state` key instead of interpreting the route event's distinct `from`/`to` contract; the table has no structured destination field.

## Acceptance Criteria

- [ ] A real executor → event-bus → SQLite test persists a `work` → `done` route with `state=work`, `to_state=done`, and `transition=route`; a self-transition retains both identical endpoints.
- [ ] Route tests establish canonical `from` precedence, legacy state-only source compatibility, and NULL behavior for missing/null endpoints. Non-route state storage and `loop_complete`'s `map_final_status` buckets keep their existing meaning, and non-route `to_state` is NULL.
- [ ] Route FTS content contains both endpoints, with matching rows returned by endpoint searches; stored loop identity/ref/anchor remain compatible with BUG-3755.
- [ ] Fresh-schema, genuine previous-version upgrade, and repeated-open tests verify the nullable column, retained pre-upgrade data, and NULL legacy values. Schema version, migration count, and generated manifest agree.
- [ ] The BUG-3736 downgrade/replay fixture represents the schema it claims before replaying later migrations; it does not replay `ADD COLUMN to_state` against a column already present. Existing replay-hold tests pass.
- [ ] Remote schema-policy tests verify an unmigrated libSQL store refuses writes with migrate guidance, a migrated store accepts the new route insert, and an older client refuses writes to the newer store. The additive SQL remains compatible with the Hrana statement splitter.
- [ ] Export/recent queries surface `to_state`; snapshot backfill rows leave it NULL and retain their existing state meaning. No rebuild-derived fingerprint bump is needed solely for this table change.
- [ ] The transport/session-store suites and `python -m pytest scripts/tests/` exit 0; documentation and release guidance describe the migration and endpoint mapping.

## Related

- BUG-3755 — loop identity repair, separately implementable; neither issue blocks the other.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| architecture | `docs/ARCHITECTURE.md` | Separate loop-event and loop-run storage paths. |
| architecture | `docs/reference/API.md` | SQLite transport and session-store interfaces. |

## Status

**Open** | Created: 2026-10-06 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-06T09:04:30 - `da8cdf64-7ea1-489f-a22f-62d03c35c5b9.jsonl`
