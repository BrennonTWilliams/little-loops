---
id: ENH-3679
type: ENH
title: Spool completed CLI telemetry under a held history.db write lock
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:01Z'
relates_to:
- ENH-3666
- ENH-3678
- ENH-3680
---

# ENH-3679: Spool completed CLI telemetry under a held history.db write lock

## Summary

Make `cli_event_context` resilient to a held local SQLite write lock: use a short end-to-end busy timeout (~250-500 ms) and, on lock failure, persist its **completed** event to a bounded local spool drained on the next successful telemetry connect. Other writers require separate scope decisions because some update an entry row or maintain `search_index`. Split out of ENH-3666 after its 2026-09-29 Opus review.

## Current Behavior

`cli_event_context` can wait `_BUSY_TIMEOUT_MS` (5000 ms) at entry and again at exit, then drop the event or its completion data under a held lock. Observed with a detached `--rebuild` holding the lock, but any long local writer can cause it.

## Expected Behavior

`cli_event_context` never stalls a command beyond the short telemetry timeout. If entry fails on `database is locked`, collect the exit code and duration, then spool **one completed event** at exit. If entry succeeds but the exit update fails, spool a typed completion update keyed by the inserted row ID. Drain on the next successful local telemetry connect. This is best-effort retention: when the size/age bound is reached, old pending events may be dropped with a visible count. Non-telemetry writers keep the 5000 ms timeout.

## Design Decisions (2026-09-30, `/ll:advise` Opus review)

- **No schema change.** `cli_events` rows carry no idempotency key. Persist each typed operation as an immutable, mode-0600 event file: write a unique temporary file, close it, and atomically publish it by rename. A drainer rename-claims a complete file, so a writer cannot append to a claimed inode. Process recovered claimed files after a crash; insert/update plus `spool_drained:<file-uuid>` marker in one SQLite transaction, then unlink. Prune old markers only after the corresponding file is absent and the crash-recovery retention window has passed.
- **Short timeout applies only to `cli_event_context`**, including connection setup, entry insert and exit update. Set it before any `ensure_db`/`schema.connect` lock wait; shared `connect()` and other writers keep `_BUSY_TIMEOUT_MS` (5000 ms).
- **Shared format, separate replay.** ENH-3680 may reuse the immutable event-file envelope and claim/recovery rules, but owns its remote target-aware drain. This local SQLite transaction API must not be assumed to work with libSQL.
- **No longer blocks ENH-3666.** It mitigates the symptom (dropped rows, ~12 s stalls) under any long lock holder; ENH-3666's shadow-build keeps lock windows short regardless.
- **Spool safety:** `.ll/`-scoped immutable files, mode 0600, bounded by total size and age; when the DB is permanently unavailable, oldest pending files may be dropped and a count is reported. Validate a closed set of operation types; never interpolate a table name from spool JSON into SQL.

## Integration Map

- `scripts/little_loops/session_store/writers.py` — `cli_event_context` entry and exit handling; a new spool module under `scripts/little_loops/session_store/`; drain on the next successful local telemetry connect without recursively opening another connection. `skill_event_context` and other writers are out of scope.
- Must not add a raw `sqlite3.connect(` (`test_history_store_chokepoint_gate.py`); remote (libsql) path stays on its own unreachable-marker route (`libsql.py` `warn_once`).
- Tests (`test_session_store_writers.py` shape): real second connection holding `BEGIN IMMEDIATE` (thread + barrier, end-to-end duration bound and post-state assertions); entry failure produces a completed event, exit-update failure replays once, concurrent drainers insert/update once, an already-open writer cannot lose an event during claim, a crash after claim/commit recovers, bounded spool reports drops; remote path unchanged.
- Docs: `docs/reference/API.md` `cli_event_context` paragraph (documents the 5000 ms timeout and `enter failed` warning), `docs/guides/HISTORY_SESSION_GUIDE.md` — end-user shape.

## Program Design

### Types

- `SpoolEvent` dataclass in a new `little_loops.session_store.spool` module: closed `op` variant (`cli_event_insert_complete` or `cli_event_update_complete`), event UUID, and validated payload. The envelope can also carry ENH-3680's typed hook events, but this issue implements only the CLI variants.

### Signatures

- `spool_publish(db: Path | str, event: SpoolEvent) -> None` — atomically publish one immutable `.ll/`-scoped file; bounded by size and age, never raises into the caller.
- `drain_local_spool(conn: sqlite3.Connection, db: Path | str) -> int` — rename-claims pending or recovered files, applies the typed insert/update plus a `spool_drained:<file-uuid>` `meta` marker in one transaction, and returns operations applied.

### Call Path

- `cli_event_context` (`little_loops.session_store.writers`) → short-timeout entry/exit → lock failure → collect completed event/update → `spool_publish`; next successful local telemetry connect → `drain_local_spool`.

## Scope Boundaries

- **In scope**: a short end-to-end timeout for `cli_event_context`, a bounded local immutable-file spool, and an idempotent local drain.
- **Out of scope**: other telemetry writers, `rebuild()` internals (ENH-3666), the rebuild trigger (ENH-3678), the `context-monitor.sh` remote hook spool (ENH-3680), remote-backend CLI telemetry (its own unreachable-marker path).

## Impact

- **Priority**: P3 - telemetry rows dropped and ~12s command stalls under any long lock holder
- **Effort**: Medium - two-phase CLI event handling, timeout plumbing, immutable files, recovery, and an idempotent drain
- **Risk**: Medium - new durability surface (spool) on the telemetry path
- **Breaking Change**: No

## Acceptance Criteria

- [ ] With a real second connection holding `BEGIN IMMEDIATE`, both the entry-failure and exit-update-failure paths return within the short end-to-end timeout; completed event data appears once after the lock is released and the spool drains.
- [ ] Immutable event files prevent an append/claim race; a crash before or after claim/transaction commit neither loses nor duplicates an unpruned event. Two concurrent drainers are safe without a schema change.
- [ ] Spool size and age are bounded; permanently unavailable storage cannot cause unbounded growth, and every pruned event increments a visible drop count. Claimed-file recovery and marker retention are covered.
- [ ] Remote (libsql) backend behavior unchanged (its own unreachable-marker path).
- [ ] Existing telemetry-writer tests pass; docs describe the spool.

## Related

- ENH-3666, ENH-3678; ENH-3680 (hook spool may reuse the immutable file envelope, with a separate remote replay).

## Status

**Open** | Created: 2026-09-30 | Priority: P3
