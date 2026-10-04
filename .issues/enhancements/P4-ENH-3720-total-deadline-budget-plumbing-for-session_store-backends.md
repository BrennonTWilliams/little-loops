---
id: ENH-3720
type: ENH
title: Total-deadline budget plumbing for session_store backends
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T01:29:51Z'
relates_to:
- ENH-3682
- FEAT-3711
- FEAT-3721
- EPIC-3710
---

# ENH-3720: Total-deadline budget plumbing for session_store backends

## Summary

Add a monotonic total-deadline budget to `session_store/backend.py`, `libsql.py` and `hrana.py` so optional history reads/writes can honor a whole-operation bound (cold verification + queries + transactions + response reads). Split out of FEAT-3711 after an Opus review (2026-10-03): it is shared infrastructure, not an ll-next feature. v1 `ll-next` reads **local SQLite only**, so this is **not** a prerequisite of EPIC-3710; it unlocks remote-history reads for ll-next and any other optional-telemetry caller.

## Current Behavior

`LibsqlBackend.connect_readonly` ignores its timeout argument and each Hrana request starts a fresh budget, so a cold verification followed by a stalled query can exceed any caller-intended total. SQLite lock timeouts bound waiting for a lock but not query execution. ENH-3679 bounds only `cli_event_context` (250 ms per connection).

## Expected Behavior

- A caller passes one monotonic deadline; the remaining budget is carried through cold access verification, queries, transactions and response reads in the libsql/Hrana backends. SQLite gets a progress-handler cancellation bound in addition to a remaining-budget lock timeout.
- Existing readers keep their default (unbounded-as-today) behavior when no deadline is passed.
- No timed-out task continues writing after the caller reports a timeout.
- Read-only paths never use `connect_telemetry` (its file-backed verification/unreachable caches violate no-write contracts).
- Coordinate with ENH-3682 (budget best-effort remote prepatch reads): share the common primitive; keep prepatch/cache behavior independent.

## Acceptance Criteria

- [ ] Deadline primitive threaded through `backend.py`, `libsql.py`, `hrana.py`; tests cover cold slow verification followed by a stalled query/write, with request counts and a documented small scheduling tolerance.
- [ ] SQLite query cancellation via progress handler bounded by remaining budget.
- [ ] Default behavior of existing callers unchanged; no background worker continues a write after timeout.
- [ ] Documented in `docs/guides/HISTORY_SESSION_GUIDE.md`/`API.md`; `python -m pytest scripts/tests/` passes.

## Impact

- **Priority**: P4 — not on the ll-next critical path (v1 is local-only).
- **Effort**: Medium — three backends plus concurrency-sensitive tests.
- **Risk**: Medium — timing-sensitive tests; touches shared backend code.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-10-04 | Priority: P4
