---
id: BUG-3761
title: rebuild() wipes hook-written tool_events and user_corrections rows that replay cannot regenerate
type: BUG
priority: P1
status: open
discovered_date: '2026-10-06'
labels: []
---

## Summary

`rebuild()` wipes every row in `tool_events` and `user_corrections`, then replays both tables from `raw_events`. Both tables also receive **live writes that never pass through `raw_events`**, so every rebuild permanently deletes those rows. This affects more than a manual `ll-session rebuild`: a `REBUILD_DERIVE_VERSION` mismatch forces one full wipe-and-replay on every store, so each derive-version bump silently drops this telemetry in every project.

This is the same class of defect as BUG-3530 (live `usage_events`) and BUG-3715 (retention `summary_nodes`). Both were fixed by adding a `_REBUILD_TABLE_PREDICATES` entry that spares rows replay cannot regenerate. `tool_events` and `user_corrections` have no such predicate, and no column that could support one.

## Steps to Reproduce

1. Use a store whose PostToolUse hook has been recording for a while (any project with hooks installed). Count the rows: `SELECT count(*) FROM tool_events WHERE length(ts) = 20` (the hook's second-precision timestamps), and the same for `user_corrections WHERE source = 'user_prompt_submit'`.
2. Run `ll-session rebuild`.
3. Re-count. The hook-written rows are gone. Replay re-derives `tool_events` from transcripts, but those rows carry different fields and millisecond timestamps, and only some of them correspond to hook rows.

Observed on a consumer project's 1.1 GB store under v1.167.0: one rebuild deleted 2,396 hook-written `tool_events` rows across 78 sessions (Bash 2,288, Read 78, Edit 44, Agent 43, Write 42, Skill 12) and 2 `user_corrections` rows. Net `tool_events` went from 41,593 to 40,567. The rows were recovered only because a backup had been taken first.

## Current Behavior

- `_REBUILD_TABLES` (`scripts/little_loops/session_store/lifecycle.py:1039`) lists `tool_events` and `user_corrections`. `rebuild()` (`scripts/little_loops/session_store/lifecycle.py:1774`) runs `DELETE FROM {table}` for each, applying `_REBUILD_TABLE_PREDICATES` only where an entry exists (`scripts/little_loops/session_store/lifecycle.py:1817-1819`). Neither table has an entry.
- The PostToolUse hook inserts `tool_events` directly (`scripts/little_loops/hooks/post_tool_use.py:202`), with `ts = _now()` (`session_store/writers.py:234`, second precision, `%Y-%m-%dT%H:%M:%SZ`). It records `latency_ms`, `bytes_in`/`bytes_out`, `cache_hit` and `mcp_outcome`, which replay does not reproduce.
- `record_correction()` (`session_store/writers.py:341`, insert at `:365`) writes `user_corrections` live with `source = 'user_prompt_submit'`.
- The `tool_events` and `user_corrections` schemas (`session_store/schema.py:136`, `:171`) have no channel or source column that tells live rows apart from replayed ones. `usage_events` has `channel`, which is what made the BUG-3530 predicate possible.
- The matching `search_index` rows (kinds `tool` and `correction`) are deleted with them.

## Expected Behavior

A rebuild re-derives only what replay can regenerate. Live-written `tool_events` and `user_corrections` rows, and their search-index entries, survive a manual rebuild and the automatic derive-version rebuild unchanged.

## Proposed Direction

- Add a discriminator to both tables, such as `channel TEXT` (`'live'` vs `'transcript'`), set by every writer. This needs a schema migration that backfills existing rows. A plausible classification heuristic: live hook rows have second-precision `ts` (length 20), while replayed rows have millisecond `ts`. For `user_corrections`, use the `source` value. Verify the heuristic against the writers before relying on it.
- Add `_REBUILD_TABLE_PREDICATES` entries (`channel IS NOT 'live'`) and keep the `search_index` deletion consistent with them.
- Decide how a live row and its replayed counterpart for the same tool call relate (today both exist; about 750 of the 2,396 had a replayed row in the same second). Keep that behavior unchanged unless deduplication is deliberately in scope.
- Bump `REBUILD_DERIVE_VERSION` only if the fix changes replay output.

## Program Design

### Types

- New `tool_events.channel: TEXT`, nullable: `'live'` for hook-written rows, `'transcript'` for replayed rows. Added by a schema migration (current `SCHEMA_VERSION = 60`).
- New `user_corrections.channel: TEXT`, nullable, same values. Live rows are those written by `record_correction`, with `source = 'user_prompt_submit'`.
- Existing `_REBUILD_TABLE_PREDICATES: dict[str, str]`: gains `"tool_events"` and `"user_corrections"` entries, each `"channel IS NOT 'live'"`, mirroring the `usage_events` entry.

### Signatures

- `handle(event: LLHookEvent) -> LLHookResult`: PostToolUse hook; its `tool_events` INSERT sets `channel = 'live'`.
- `record_correction(db_path: Path | str, session_id: str | None, content: str, source: str, config: dict | None = None) -> None`: its `user_corrections` INSERT sets `channel = 'live'`.
- `_backfill_tool_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int`: replay path; sets `channel = 'transcript'`.
- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]`: signature unchanged. The `search_index` delete for kinds `tool` and `correction` must exclude the entries of surviving live rows.

### Call Path

`handle` -> `connect` -> `tool_events` INSERT (`channel = 'live'`)

`rebuild` -> `_REBUILD_TABLE_PREDICATES` -> `DELETE FROM tool_events WHERE channel IS NOT 'live'` -> `_backfill_tool_events`

## Acceptance Criteria

- [ ] A store holding live-written `tool_events` and `user_corrections` rows keeps every one of them, with all field values intact, across `rebuild()`.
- [ ] The same holds for the automatic wipe-and-replay triggered by a `REBUILD_DERIVE_VERSION` mismatch.
- [ ] Rows that replay derives are still fully wiped and re-derived (no duplicate accumulation across repeated rebuilds).
- [ ] Existing stores are migrated: rows already present are classified so the first post-upgrade rebuild does not delete them.
- [ ] A regression test drives the real PostToolUse hook writer and `record_correction()`, runs `rebuild()`, and asserts row-for-row preservation. It fails on the current code.

## Impact

- **Priority**: P1 - silent, permanent loss of live telemetry on every manual rebuild and on every `REBUILD_DERIVE_VERSION` bump, across all projects; observed 2,396 `tool_events` rows and 2 `user_corrections` rows lost in one rebuild.
- **Effort**: Medium - one schema migration with a backfill classifier, two writer changes, two predicate entries and a `search_index` delete adjustment; follows the BUG-3530 pattern.
- **Risk**: Medium - touches the schema migration path and the rebuild wipe; mitigated by the row-for-row regression test and by backfilling existing rows conservatively, so ambiguous rows are preserved rather than wiped.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-10-06 | Priority: P1


## Session Log
- `/ll:format-issue` - 2026-10-06T23:51:08 - `be24ca19-aef3-4138-b6f0-d60a7d2187c1.jsonl`
