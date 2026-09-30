---
id: ENH-3683
type: ENH
title: Spool completed CLI telemetry under a held history.db write lock (deferred
  Phase 2)
priority: P4
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T05:06:41Z'
deferred_by: human
deferred_date: '2026-09-30T05:07:04Z'
blocked_by:
- ENH-3679
relates_to:
- ENH-3678
---

# ENH-3683: Spool completed CLI telemetry under a held history.db write lock (deferred Phase 2)

## Summary

Deferred Phase 2 split out of ENH-3679 (2026-09-30). If, after ENH-3678 ships and ENH-3679 Phase 1 measures drop counts, `cli_event_context` still loses material telemetry under a held local SQLite write lock, persist the **completed** event to a bounded local spool drained on the next successful telemetry connect. Otherwise close this issue as not needed.

## Current Behavior

`cli_event_context` waits the short telemetry timeout (ENH-3679 Phase 1) and then drops the event, counting it in the sidecar drop counter.

## Expected Behavior

When the gate below is met, a lock-failed completed event is spooled and later applied exactly once instead of dropped.

## Program Design

### Types

- `SpoolEvent` dataclass in a new `little_loops.session_store.spool` module: closed `op` variant, event UUID, validated payload.

### Signatures

- `spool_publish(db: Path | str, event: SpoolEvent) -> None` — atomically publish one immutable `.ll/`-scoped file; bounded by size and age, never raises into the caller.
- `drain_local_spool(conn: sqlite3.Connection, db: Path | str) -> int` — rename-claims pending or recovered files, applies the typed insert/update plus a `spool_drained:<file-uuid>` `meta` marker in one transaction, returns operations applied.

### Call Path

- `cli_event_context` (`little_loops.session_store.writers`) → short-timeout entry/exit → lock failure → collect completed event/update → `spool_publish`; next successful local telemetry connect → `drain_local_spool`.

## Impact

- **Priority**: P4 - only justified by measured telemetry loss after ENH-3678/ENH-3679
- **Effort**: Medium - immutable files, recovery, idempotent drain
- **Risk**: Medium - new durability surface on the telemetry path
- **Breaking Change**: No

## Activation Gate

Do not start until ENH-3679's sidecar drop counter (surfaced by `ll-doctor`) shows material loss with ENH-3678 in place. The motivating lock holder (a multi-minute detached `--rebuild`) is largely removed by ENH-3678; record the measured counts here before proceeding.

## Design (from ENH-3679, `/ll:advise` Opus review 2026-09-30)

- **No schema change.** `cli_events` rows carry no idempotency key. Persist each typed operation as an immutable, mode-0600 event file: write a unique temporary file, close it, and atomically publish it by rename. A drainer rename-claims a complete file, so a writer cannot append to a claimed inode. Process recovered claimed files after a crash; insert/update plus a `spool_drained:<file-uuid>` marker in one SQLite transaction, then unlink. Prune old markers only after the corresponding file is absent and the crash-recovery retention window has passed.
- If entry fails on `database is locked`, collect exit code and duration, then spool **one completed event** at exit. If entry succeeds but the exit update fails, spool a typed completion update keyed by the inserted row ID. Drain on the next successful local telemetry connect.
- **Spool safety:** `.ll/`-scoped immutable files, mode 0600, bounded by total size and age; when the DB is permanently unavailable, oldest pending files may be dropped and a count reported. Validate a closed set of operation types (`cli_event_insert_complete`, `cli_event_update_complete`); never interpolate a table name from spool JSON into SQL.
- **Local only.** ENH-3680's remote target-aware drain is independent; do not couple the two. The local SQLite transaction API must not be assumed to work with libSQL.

## Scope Boundaries

- **In scope**: the local immutable-file spool, idempotent local drain, and their bounds for `cli_event_context` only.
- **Out of scope**: the short timeout and drop counter (ENH-3679), other telemetry writers, the remote hook spool (ENH-3680), `rebuild()` and its trigger (ENH-3666/ENH-3678).

## Acceptance Criteria

- [ ] Activation gate recorded (measured drop counts) before implementation.
- [ ] With a real second connection holding `BEGIN IMMEDIATE`, both the entry-failure and exit-update-failure paths return within the short timeout; completed event data appears once after the lock is released and the spool drains.
- [ ] Immutable event files prevent an append/claim race; a crash before or after claim/commit neither loses nor duplicates an unpruned event; two concurrent drainers are safe without a schema change.
- [ ] Spool size and age are bounded; every pruned event increments a visible drop count; claimed-file recovery and marker retention are covered.
- [ ] No raw `sqlite3.connect(` added (`test_history_store_chokepoint_gate.py`); remote (libsql) behavior unchanged.

## Related

- ENH-3679 (Phase 1, parent scope), ENH-3678 (removes the main lock holder), ENH-3680 (independent remote hook spool).

## Status

**Deferred** | Created: 2026-09-30 | Priority: P4
