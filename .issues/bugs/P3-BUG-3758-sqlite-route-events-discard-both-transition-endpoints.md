---
id: BUG-3758
type: BUG
title: SQLite route search omits destination and prefers legacy source
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

# BUG-3758: SQLite route search omits destination and prefers legacy source

## Summary

The merged BUG-3755 work already persists both route endpoints in schema v60. Two gaps remain: route FTS content omits the destination, and a legacy `state` value wins over canonical `from` when both appear. Narrow this issue to those mapping/search fixes; no further migration is needed.

## Current Behavior

Verified on 2026-10-06 after merge commit `31d2b07fa`:

- `scripts/little_loops/session_store/writers.py`, `SQLiteTransport.send`, stores route `to` in nullable `to_state`. It takes `state` first and falls back to `from` only when `state` is null.
- Route search content joins loop name, source state and event type, excluding `to_state`.
- `scripts/little_loops/session_store/schema.py` is already version 60, with `ALTER TABLE loop_events ADD COLUMN to_state TEXT` in the v60 migration. The manifest and current-version assertions are updated.
- `scripts/tests/test_bug3755_transport_loop_identity.py` already drives a real executor through the event bus and asserts a persisted `work` → `done` route. It does not cover destination search or conflicting source keys.
- `scripts/tests/test_bug3736_usage_replay_holds.py`, `_downgrade_and_remigrate`, already removes the v60 column before replaying v59/v60. No fixture repair remains in this issue.

## Expected Behavior

For routes, a non-null canonical `from` takes precedence over legacy `state`; absent/null `from` falls back to `state`. Missing/null sources and destinations stay NULL. Both endpoints appear in FTS content for newly received route events. `transition` remains the event type `route`; input events are not mutated.

Non-route rows retain their current state semantics, NULL `to_state`, and search behavior. Loop identity/ref/anchor and `loop_complete` final-status buckets remain intact. Existing structured endpoints and schema v60 remain intact.

## Steps to Reproduce

1. Use a temporary DB and `SQLiteTransport`; send a route with distinct `from`, legacy `state`, and `to` values.
2. Inspect `loop_events`: the destination is stored but the source is the legacy value.
3. Search for a unique destination token: no route result is returned, because destination is absent from route FTS content.
4. Drive a real executor route: its source/target are already stored correctly because the producer has `from`/`to` and no `state`. This isolates the remaining search defect from the synthetic compatibility case.

## Root Cause

`SQLiteTransport.send` applies a legacy-first source fallback and builds FTS text without the destination. The original endpoint-storage defect was repaired by BUG-3755; the issue's prior schema-v59/missing-column claims are outdated.

## Proposed Solution

Change only route source precedence and add the route destination to the FTS content tuple. Keep explicit row inserts, event identity handling, and best-effort sink behavior. Reuse the producer-to-sink test module rather than creating a second harness for the same event path.

This affects new search-index entries only. Existing historical FTS content is not repaired: rebuild omits event-level loop storage, and reconstructing old index entries is outside scope. Neither a migration nor a rebuild-derived fingerprint bump is justified.

## Program Design

### Types

- Existing `loop_events.state`: route source, canonical non-null `from` then legacy `state`.
- Existing `loop_events.to_state`: route destination, nullable; schema v60 already provides it.
- Existing `transition`: event type, unchanged.

### Signatures

`SQLiteTransport.send(self, event: dict[str, Any]) -> None`

The existing signature stays intact.

### Call Path

`FSMExecutor` → `PersistentExecutor` event bus → `SQLiteTransport.send` → existing structured route row plus route FTS text containing both endpoints.

## Implementation Steps

1. Add failing destination-search and source-precedence cases to the existing live-loop/transport tests. Keep history and loop paths temporary and close transports in `finally`.
2. Prefer non-null `from` for routes, preserving the legacy fallback; include destination in route FTS text without changing non-route behavior.
3. Run the transport/live-loop/session-store writer tests, then `python -m pytest scripts/tests/`. Update current history/API wording where it omits route destination search.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/writers.py` — route mapping and FTS content only.
- `scripts/tests/test_bug3755_transport_loop_identity.py` — real producer destination-search regression.
- `scripts/tests/test_session_store_writers.py` — synthetic key precedence, nulls, self-transitions and non-route behavior.
- `docs/reference/API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md` — current route search contract as needed.

### Dependent Files

- `scripts/little_loops/session_store/schema.py` and `scripts/little_loops/session_store/schema_manifest.json` — v60 is already sufficient; no edit.
- `scripts/little_loops/session_store/queries.py` — recent/export projections already surface `to_state`; retain existing behavior.
- `scripts/little_loops/session_store/lifecycle.py` — event-level loop storage/search is not rebuilt; document new-row-only search improvement.
- `scripts/little_loops/session_store/remote_schema.py` — existing exact-version write policy remains unchanged. This fix introduces no additional remote upgrade requirement.

## Acceptance Criteria

- [ ] A real executor route is returned when searching for its destination; its row still contains `state=work`, `to_state=done`, `transition=route` and the correct loop identity/ref/anchor.
- [ ] Synthetic routes prefer non-null `from` over conflicting `state`, fall back for absent/null `from`, retain missing/null endpoint semantics, and preserve self-transitions. No input payload mutation occurs.
- [ ] Non-route state/search behavior, NULL destinations and completion-status mapping remain unchanged.
- [ ] Schema remains v60 with no new migration/manifest churn; existing migration, replay-hold and endpoint-persistence tests pass. Historical FTS repair is neither performed nor promised.
- [ ] Targeted tests and the full local suite pass; current documentation describes both searchable endpoints for new route events.

## Impact

- **Priority**: P3 — optional diagnostic search/legacy-payload correctness.
- **Effort**: Small — writer mapping plus focused regression coverage.
- **Risk**: Low — no schema change; search terms expand for new routes.
- **Breaking Change**: No.

## Review Notes

Reviewed on 2026-10-06. A temporary DB probe stored the destination, selected the conflicting legacy source, and returned zero destination FTS matches. The merged BUG-3755 tests cover endpoint persistence and passed in the 338-test baseline. Opus supported narrowing the remaining scope (consult confidence 0.72). No implementation edits were made. BUG-3755 is completed background context, not an outstanding dependency.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| architecture | `docs/reference/API.md` | SQLite transport and search contract. |

## Status

**Open** | Reviewed: 2026-10-06 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-10-06T09:04:30 - `da8cdf64-7ea1-489f-a22f-62d03c35c5b9.jsonl`
