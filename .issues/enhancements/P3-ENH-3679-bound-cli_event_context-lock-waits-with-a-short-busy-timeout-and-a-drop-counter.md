---
id: ENH-3679
type: ENH
title: Bound cli_event_context lock waits with a short busy timeout and a drop counter
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
- ENH-3683
confidence_score: 90
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3679: Bound cli_event_context lock waits with a short busy timeout and a drop counter

## Summary

Make `cli_event_context` resilient to a held local SQLite write lock: use a short end-to-end busy timeout (~250-500 ms) via an explicit `busy_timeout_ms` parameter, and count every dropped event in a sidecar drop counter surfaced by `ll-doctor`, so loss is measurable. The bounded spool that would retain dropped events is **deferred to ENH-3683**, to be built only if measured drops justify it. Split out of ENH-3666 after its 2026-09-29 Opus review; rescoped 2026-09-30.

## Current Behavior

`cli_event_context` can wait `_BUSY_TIMEOUT_MS` (5000 ms) at entry and again at exit, then drop the event or its completion data under a held lock. Observed with a detached `--rebuild` holding the lock, but any long local writer can cause it.

## Expected Behavior

`cli_event_context` never stalls a command beyond the short telemetry timeout, on connection setup, entry insert and exit update. When the lock wait times out, the event (or its completion update) is dropped best-effort and a counter in an `.ll/`-scoped sidecar file is incremented; `ll-doctor` reports the count. Non-telemetry writers keep the 5000 ms timeout.

## Scope Phasing (2026-09-30 Opus review)

- **This issue (former Phase 1):** a short end-to-end timeout for `cli_event_context` via an **explicit `busy_timeout_ms` parameter** threaded through `schema.connect` → `_configure_connection` (not a contextvar; `_configure_connection` hard-codes `_BUSY_TIMEOUT_MS` today), plus the sidecar drop counter. Set the timeout before any `ensure_db`/`schema.connect` lock wait; shared `connect()` and other writers keep `_BUSY_TIMEOUT_MS`.
- **ENH-3683 (deferred, former Phase 2):** the immutable-file spool and idempotent drain. Its motivating lock holder (a multi-minute detached `--rebuild`) is largely removed by ENH-3678; activate it only if the drop counter, measured after ENH-3678 ships, shows material loss.

## Integration Map

- `scripts/little_loops/session_store/writers.py` — `cli_event_context` entry and exit handling; `session_store/schema.py` `connect`/`_configure_connection` (explicit `busy_timeout_ms`); the drop-counter sidecar and its `ll-doctor` line. `skill_event_context` and other writers are out of scope.
- Must not add a raw `sqlite3.connect(` (`test_history_store_chokepoint_gate.py`); remote (libsql) path stays on its own unreachable-marker route (`libsql.py` `warn_once`).
- Tests (`test_session_store_writers.py` shape): real second connection holding `BEGIN IMMEDIATE` (thread + barrier, end-to-end duration bound and post-state assertions) for both entry and exit; drop counter increments once per dropped event and `ll-doctor` reports it; other writers keep 5000 ms; remote path unchanged.
- Docs: `docs/reference/API.md` `cli_event_context` paragraph (documents the 5000 ms timeout and `enter failed` warning), `docs/guides/HISTORY_SESSION_GUIDE.md` — end-user shape; `ll-doctor` drop-count line.

## Program Design

### Signatures

- `connect(path=DEFAULT_DB_PATH, *, busy_timeout_ms: int | None = None)` (`little_loops.session_store.schema`) — `None` keeps `_BUSY_TIMEOUT_MS`; `cli_event_context` passes the short value.
- `record_dropped_cli_event(db: Path | str) -> None` — increments the `.ll/`-scoped sidecar counter; never raises into the caller. **Counter spec:** one file `<db>.cli-event-drops` holding an integer, updated under an `fcntl.flock(LOCK_EX)` on the same file (read-modify-write, so concurrent CLI processes count exactly once each); `ll-doctor` reads it without locking.
- **Threading the timeout:** `busy_timeout_ms` must reach every lock-waiting step of `cli_event_context`: `ensure_db` (its own `sqlite3.connect` + pragma setup), `_configure_connection`, the entry insert and the exit update. "End-to-end" means one total deadline of ~500 ms across setup, entry and exit (not per step); pick the value here and pin it in a test. Grep for `connect` monkeypatches in the test suite and update any that do not accept the new keyword. No raw `sqlite3.connect(` (`test_history_store_chokepoint_gate.py`).

### Call Path

- `cli_event_context` (`little_loops.session_store.writers`) → short-timeout `connect` → lock failure → `record_dropped_cli_event`; `ll-doctor` reads the sidecar.

## Scope Boundaries

- **In scope**: a short end-to-end timeout for `cli_event_context` and the drop counter with its `ll-doctor` line.
- **Out of scope**: the spool and drain (ENH-3683), other telemetry writers, `rebuild()` internals (ENH-3666), the rebuild trigger (ENH-3678), the `context-monitor.sh` remote hook spool (ENH-3680, no coupling), remote-backend CLI telemetry (its own unreachable-marker path).

## Impact

- **Priority**: P3 - telemetry rows dropped and ~12s command stalls under any long lock holder
- **Effort**: Small - timeout plumbing, a sidecar counter, one doctor line
- **Risk**: Low - no new durability surface; drops are counted, not retained
- **Breaking Change**: No

## Acceptance Criteria

- [ ] With a real second connection holding `BEGIN IMMEDIATE`, `cli_event_context` returns within the short timeout on both entry and exit, and other writers keep 5000 ms.
- [ ] Each dropped event increments the sidecar counter exactly once and `ll-doctor` reports the count.
- [ ] Remote (libsql) backend behavior unchanged (its own unreachable-marker path).
- [ ] Existing telemetry-writer tests pass; docs describe the timeout and drop counter.
- [ ] ENH-3683 (spool) stays deferred unless the measured drop count justifies activating it.

## Related

- ENH-3666, ENH-3678; ENH-3683 (deferred spool, former Phase 2); ENH-3680 (independent remote hook spool; no envelope coupling).

## Status

**Open** | Created: 2026-09-30 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-30T05:10:59 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
