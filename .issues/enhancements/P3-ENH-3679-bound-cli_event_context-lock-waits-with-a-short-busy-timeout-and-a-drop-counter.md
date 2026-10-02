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
- EPIC-3693
- ENH-3698
- ENH-3658
- ENH-3666
- ENH-3678
- ENH-3680
blocks:
- ENH-3683

---

# ENH-3679: Bound cli_event_context lock waits with a short busy timeout and a drop counter

## Summary

Make `cli_event_context` resilient to a held local SQLite write lock: use a short **per-phase** busy-timeout budget (setup + entry <= 250 ms, exit <= 250 ms) via an explicit `busy_timeout_ms` parameter, and count every dropped event in a sidecar drop counter surfaced by `ll-doctor`, so loss is measurable. The bounded spool that would retain dropped events is **deferred to ENH-3683**, to be built only if measured drops justify it. Split out of ENH-3666 after its 2026-09-29 Opus review; rescoped 2026-09-30. Detached from EPIC-3693 2026-10-02 (local-store fix; `relates_to` only).

## Current Behavior

`cli_event_context` can wait `_BUSY_TIMEOUT_MS` (5000 ms) at entry and again at exit, then drop the event or its completion data under a held lock. Observed with a detached `--rebuild` holding the lock, but any long local writer can cause it.

## Expected Behavior

`cli_event_context` bounds SQLite lock waiting in two phases: **setup + entry insert share 250 ms** and **exit update gets a fresh 250 ms**. Use a monotonic deadline within each phase, passing only the remaining budget to every connection/pragma/query lock wait. Never measure a single deadline across the arbitrary command body. This bounds lock waiting, not arbitrary filesystem or migration CPU time; tests on an already migrated store assert elapsed time with a documented small scheduling tolerance. A timed-out event/completion is dropped best-effort and counted in an `.ll/` sidecar; `ll-doctor` reports the count. Non-telemetry writers keep 5000 ms.

**Drop-count rule (defines "exactly once per dropped event"):** if the entry was dropped, the exit skips entirely with **no second count**; if the entry succeeded and the exit was dropped, **one completion drop** is counted. A single command therefore adds at most one to the counter.

## Scope Phasing (2026-09-30 Opus review)

- **This issue (former Phase 1):** a short per-phase timeout budget for `cli_event_context` (setup + entry <= 250 ms, exit <= 250 ms) via an **explicit `busy_timeout_ms` parameter** threaded through `schema.connect` → `_configure_connection` (not a contextvar; `_configure_connection` hard-codes `_BUSY_TIMEOUT_MS` today), plus the sidecar drop counter. Set the timeout before any `ensure_db`/`schema.connect` lock wait; shared `connect()` and other writers keep `_BUSY_TIMEOUT_MS`.
- **ENH-3683 (deferred, former Phase 2):** the immutable-file spool and idempotent drain. Its motivating lock holder (a multi-minute detached `--rebuild`) is largely removed by ENH-3678; activate it only if the drop counter, measured after ENH-3678 ships, shows material loss.

## Integration Map

- `scripts/little_loops/session_store/writers.py` — `cli_event_context` entry and exit handling; `session_store/schema.py` `connect`/`_configure_connection` (explicit `busy_timeout_ms`); the drop-counter sidecar and its `ll-doctor` line. `skill_event_context` and other writers are out of scope.
- Must not add a raw `sqlite3.connect(` (`test_history_store_chokepoint_gate.py`); remote (libsql) path stays on its own unreachable-marker route (`libsql.py` `warn_once`).
- Tests (`test_session_store_writers.py` shape): real second connection holding `BEGIN IMMEDIATE` (thread + barrier, per-phase duration bounds of 250 ms each and post-state assertions) for both entry and exit, including the drop-count rule (entry dropped -> exit skipped, one count; entry ok + exit dropped -> one completion count); drop counter increments once per dropped event and `ll-doctor` reports it; other writers keep 5000 ms; remote path unchanged.
- Docs: `docs/reference/API.md` `cli_event_context` paragraph (documents the 5000 ms timeout and `enter failed` warning), `docs/guides/HISTORY_SESSION_GUIDE.md` — end-user shape; `ll-doctor` drop-count line. **Sequencing:** the drop-count line edits `cli/doctor.py` and the `ll-doctor` check list/count in `docs/reference/CLI.md`, as do ENH-3698 (rebuild-pending check) and ENH-3658 (`--trim` remote guard); land them in sequence (after or with ENH-3698 and ENH-3658), never as parallel branches.

## Program Design

### Signatures

- `connect(path=DEFAULT_DB_PATH, *, busy_timeout_ms: int | None = None)` (`little_loops.session_store.schema`) — `None` keeps `_BUSY_TIMEOUT_MS`; `cli_event_context` passes the short value.
- `record_dropped_cli_event(db: Path | str) -> None` — counts a drop without a database write or blocking user-space lock; never raises. **Counter spec:** open `<db>.cli-event-drops.lock` with `O_CREAT | O_WRONLY | O_APPEND`, append exactly one byte with a single `os.write`, and close. Doctor uses file size as the count. No read-modify-write or `flock`: a contended counter must not replace the SQLite stall. The `.lock` suffix is already ignored. Counts are exact when append succeeds; an unwritable/full filesystem must fail softly and cannot guarantee an increment.
- **Threading the timeout:** cover `ensure_db` (its own connection and pragma setup), `_configure_connection`, insert/update and commit. A fresh 250 ms timeout at every step would multiply the budget: compute remaining monotonic time before each possible lock wait, and skip/drop when exhausted. Add an internal deadline parameter if needed; ordinary callers retain the existing timeout. Entry failure skips all exit work. A command body longer than 250 ms still receives a fresh exit budget and can persist its completion. Update connection monkeypatches for the new keyword; no raw `sqlite3.connect(` outside the existing chokepoint.

### Call Path

- `cli_event_context` (`little_loops.session_store.writers`) → short-timeout `connect` → lock failure → `record_dropped_cli_event`; `ll-doctor` reads the sidecar.

## Scope Boundaries

- **In scope**: a short per-phase timeout budget for `cli_event_context` and the drop counter with its `ll-doctor` line.
- **Out of scope**: the spool and drain (ENH-3683), other telemetry writers, `rebuild()` internals (ENH-3666), the rebuild trigger (ENH-3678), the `context-monitor.sh` remote hook spool (ENH-3680, no coupling), remote-backend CLI telemetry (its own unreachable-marker path).

## Impact

- **Priority**: P3 - telemetry rows dropped and ~12s command stalls under any long lock holder
- **Effort**: Small - timeout plumbing, a sidecar counter, one doctor line
- **Risk**: Low - no new durability surface; drops are counted, not retained
- **Breaking Change**: No

## Acceptance Criteria

- [ ] With a real second connection holding `BEGIN IMMEDIATE` on a migrated store, lock waiting uses one 250 ms setup/entry budget and a fresh 250 ms exit budget (values pinned); observed phase latency stays within that budget plus a documented small scheduling tolerance. Other writers keep 5000 ms. The arbitrary command body is excluded from these measurements.
- [ ] Each dropped event increments the sidecar counter exactly once per the drop-count rule (entry dropped -> exit skips, no second count; entry ok + exit dropped -> one completion drop) and `ll-doctor` reports the count.
- [ ] A command body longer than 250 ms does not consume the exit budget. Multi-step setup cannot reset the entry deadline. Concurrent processes append N known drops and doctor reports N; a held `flock` on the sidecar does not stall the append; sidecar write failure never escapes.
- [ ] Remote (libsql) backend behavior unchanged (its own unreachable-marker path).
- [ ] Existing telemetry-writer tests pass; docs describe the timeout and drop counter.
- [ ] ENH-3683 (spool) stays deferred unless the measured drop count justifies activating it.

## Related

- ENH-3666, ENH-3678; ENH-3683 (deferred spool, former Phase 2); ENH-3680 (independent remote hook spool; no envelope coupling).

## Confidence Check Notes

_Updated 2026-10-02 after the EPIC-3693 pre-implementation review._

Prior 90/79 scores were cleared: per-step timeout resets and a blocking counter lock undermined the intended bound. The revised plan uses two independent cumulative phase budgets and a one-byte append counter. Re-run `/ll:confidence-check` on this scope before implementation; planned lock-holder/concurrent-counter tests are verification requirements, not completed evidence.

## Status

**Open** | Created: 2026-09-30 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-30T05:10:59 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
