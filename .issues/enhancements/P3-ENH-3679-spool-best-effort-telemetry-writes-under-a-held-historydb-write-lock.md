---
id: ENH-3679
type: ENH
title: Spool best-effort telemetry writes under a held history.db write lock
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:01Z'
relates_to:
- ENH-3666
- ENH-3678
- ENH-3680
blocks:
- ENH-3680
---

# ENH-3679: Spool best-effort telemetry writes under a held history.db write lock

## Summary

Make best-effort telemetry writers (`cli_events` and similar) resilient to a held write lock: use a short busy timeout (~250-500 ms) and, on lock failure, append the row to a bounded local JSONL spool drained on the next successful connect. Split out of ENH-3666 after its 2026-09-29 Opus review.

## Current Behavior

Every `ll-*` writer waits `_BUSY_TIMEOUT_MS` (5000 ms) then logs `cli_event_context: enter failed ... database is locked` and drops its row; the command also takes ~12 s wall time. Observed with a detached `--rebuild` holding the lock, but the same happens under any long lock holder (usage-trigger worker, `refresh_raw_events`, `recompress_raw_events`).

## Expected Behavior

Telemetry writes never stall a command beyond the short timeout and are not lost: on `OperationalError: database is locked` the row goes to a spool (`.ll/` scoped, size- and age-bounded, one small JSON line per row so appends stay atomic) and is drained/idempotently inserted on the next successful connect. Non-telemetry writers keep the 5000 ms timeout.

## Design Decisions (2026-09-30, `/ll:advise` Opus review)

- **No schema change.** `cli_events` rows carry no idempotency key and adding a UUID column would force a `SCHEMA_VERSION` bump. Instead make the drain idempotent **per spool file**: claim a file by atomic `rename` (so two concurrent drainers never process the same file), then insert its rows and a `meta` marker `spool_drained:<file-uuid>` in one transaction; skip any file whose marker exists.
- **Short timeout applies only to best-effort telemetry writers** (`cli_event_context` and siblings), set per-connection; shared `connect()` and non-telemetry writers keep `_BUSY_TIMEOUT_MS` (5000 ms).
- **One shared mechanism.** ENH-3680 (the `context-monitor.sh` hook spool) consumes this spool format and drain; do not build two. Blocks ENH-3680 accordingly.
- **No longer blocks ENH-3666.** It mitigates the symptom (dropped rows, ~12 s stalls) under any long lock holder; ENH-3666's shadow-build keeps lock windows short regardless.
- **Spool safety:** `.ll/`-scoped, mode 0600, one JSON line per row under `PIPE_BUF` (4 KB) for atomic `O_APPEND`, bounded by size and age; when the DB is permanently unavailable, oldest lines are dropped, never unbounded growth.

## Integration Map

- `scripts/little_loops/session_store/writers.py` — `cli_event_context` and the other best-effort telemetry writers (`_log_degraded`, `_DEGRADE_ERRORS`); a new spool module under `scripts/little_loops/session_store/`; drain on next successful connect (`schema.connect`/`ensure_db` path, telemetry only).
- Must not add a raw `sqlite3.connect(` (`test_history_store_chokepoint_gate.py`); remote (libsql) path stays on its own unreachable-marker route (`libsql.py` `warn_once`).
- Tests (`test_session_store_writers.py` shape): real second connection holding `BEGIN IMMEDIATE` (thread + barrier, post-state assertions, no wall clock); concurrent drainers insert each row once; bounded spool under permanent unavailability; remote path unchanged.
- Docs: `docs/reference/API.md` `cli_event_context` paragraph (documents the 5000 ms timeout and `enter failed` warning), `docs/guides/HISTORY_SESSION_GUIDE.md` — end-user shape.

## Program Design

### Types

- `SpoolRow` dataclass in a new `little_loops.session_store.spool` module: `table: str`, `values: dict[str, Any]`; serialized as one JSON line under 4 KB.

### Signatures

- `spool_append(db: Path | str, row: SpoolRow) -> None` — O_APPEND one line to the `.ll/`-scoped spool; bounded by size and age, never raises into the caller.
- `drain_spool(conn: sqlite3.Connection, db: Path | str) -> int` — rename-claims each spool file, inserts its rows plus a `spool_drained:<file-uuid>` `meta` marker in one transaction, and returns rows inserted.

### Call Path

- `cli_event_context` (`little_loops.session_store.writers`) → short-timeout connect → `OperationalError: database is locked` → `spool_append`; next successful telemetry connect → `drain_spool`.

## Scope Boundaries

- **In scope**: a short busy timeout for best-effort telemetry writers, a bounded local JSONL spool, and an idempotent drain on the next successful connect.
- **Out of scope**: `rebuild()` internals (ENH-3666), the rebuild trigger (ENH-3678), the `context-monitor.sh` hook spool (ENH-3680), remote-backend telemetry (its own unreachable-marker path).

## Impact

- **Priority**: P3 - telemetry rows dropped and ~12s command stalls under any long lock holder
- **Effort**: Small/Medium - short timeout, a bounded spool file, and an idempotent drain
- **Risk**: Medium - new durability surface (spool) on the telemetry path
- **Breaking Change**: No

## Acceptance Criteria

- [ ] With a real second connection holding `BEGIN IMMEDIATE`, a `cli_event_context` write returns within the short timeout and its row appears after the lock is released and the spool drains.
- [ ] Spool is bounded (size/age), drained idempotently via rename-claim + transactional `spool_drained:<uuid>` marker (no duplicate rows, two concurrent drainers safe, no schema change), and never grows unbounded when the DB is permanently unavailable.
- [ ] Remote (libsql) backend behavior unchanged (its own unreachable-marker path).
- [ ] Existing telemetry-writer tests pass; docs describe the spool.

## Related

- ENH-3666, ENH-3678; ENH-3680 (hook spool, same drain idea: consider one shared spool mechanism).

## Status

**Open** | Created: 2026-09-30 | Priority: P3
