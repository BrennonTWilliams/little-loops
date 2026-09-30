---
id: ENH-3682
type: ENH
title: Budget best-effort remote prepatch history reads
priority: P4
status: open
relates_to:
- BUG-3652
- ENH-3668
blocks:
- ENH-3657
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T01:30:56Z'
---

# ENH-3682: Budget best-effort remote prepatch history reads

## Summary

Bound the remote advisory reads used by FSM prepatch (`read_base_sha` and `read_base_dirty`) and reuse the remote unreachable marker. This independent latency fix was split from ENH-3668's larger typed-reader work.

## Current Behavior

BUG-3652 made the two prepatch reads remote-aware through relative `DEFAULT_DB_PATH`. They use the standard readonly path with `ensure=True`; a black-holed endpoint can hold the FSM thread for about 10 seconds per read, and these reads do not set the telemetry unreachable marker. A stopped stub fails immediately and does not test the stall.

## Ordering and Exception Contract (2026-09-30 Opus review)

**Land before ENH-3657's seam slice.** `read_base_sha`/`read_base_dirty` use `ensure=True`, so under remote they reach `ensure_schema` → `check_access(write=True)`, which raises `HistoryUnsupported` for a behind, foreign or read-only-token store. Today `_connect_readonly` swallows it into `None`; ENH-3657's re-raise would push it into the FSM prepatch path, which promises never to raise. The `best_effort` path therefore skips ensure **and** catches `HistoryError` including `HistoryUnsupported` (the never-raises contract stays with these two readers regardless of ENH-3657's re-raise, which must be narrowed to the guard's own subclass).

## Expected Behavior

Best-effort prepatch reads use a connection limited by `history.backend.telemetry_timeout_ms`, skip remote ensure/migration, and return `None` on an unavailable endpoint. The first timeout sets the unreachable marker; another advisory read while the marker is active makes no request. Other history reads retain their existing timeout and errors. Local SQLite behavior is unchanged.

## Motivation

Base-SHA/dirty-state history is advisory to prepatch. A slow remote store should not delay an FSM step twice when the same step can continue using its existing branch/merge-base fallback.

## Proposed Solution

Add `open_history_readonly(..., best_effort: bool = False)` and a remote `LibsqlBackend.connect_readonly_telemetry` path. For `RemoteTarget` plus `best_effort=True`, skip `ensure_schema`, use a read-only `LibsqlConnection` with telemetry timeout and marker behavior, and return `None` on `HistoryError` through the existing reader helper. Set `best_effort=True` only in the two prepatch readers. `telemetry_scope()` alone is insufficient because `open_history_readonly` does not consult it. Keep the relative default path so backend config is resolved normally and no shadow local database is created.

## Scope Boundaries

- **In scope:** only `read_base_sha` and `read_base_dirty`, the best-effort readonly connection seam, timeout/marker tests and API docs.
- **Out of scope:** typed-target propagation to user-facing reader CLIs/MCP (ENH-3668), all other reader timeouts, remote migrations, and changes to prepatch fallback decisions.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/backend.py` / `libsql.py` (readonly best-effort connection), `history_reader/_base.py` (narrow parameter), `history_reader/runs.py` (two call sites), focused prepatch/remote tests, and `docs/reference/API.md`.

### Similar Patterns and Configuration

- Reuse the existing telemetry timeout and unreachable marker from the remote writer connection. No new config key or schema migration.

## Program Design

### Signatures

- `open_history_readonly(target=None, *, ensure: bool = False, best_effort: bool = False)` — keeps the default standard read behavior.

### Call Path

`history_reader.runs.read_base_sha` / `read_base_dirty` → `_connect_readonly(..., best_effort=True)` → `open_history_readonly(..., best_effort=True)` → bounded remote readonly query or `None` fallback. A local target follows the existing local path.

## Implementation Steps

1. Implement the opt-in remote readonly telemetry connection and marker-aware timeout at the backend seam.
2. Enable it at only the two prepatch reads. Preserve the existing `None` fallback on open and mid-query errors.
3. Test with a socket that accepts but never replies, plus a local twin; update API docs and run the suite.

## Impact

- **Priority:** P4 — an opt-in remote backend can delay an advisory FSM step.
- **Effort:** Small/Medium — one connection seam and two callers.
- **Risk:** Medium — timeout or marker behavior must not leak into normal reads.
- **Breaking Change:** No.

## Acceptance Criteria

- [ ] A black-holed-socket test shows each prepatch read returns `None` within the configured telemetry timeout budget, sets the unreachable marker, and sends no new request while that marker is active.
- [ ] Both readers still return actual remote data through a reachable `HranaStub`; local SQLite and standard reader timeouts remain unchanged.
- [ ] Open and mid-query remote failures preserve each function's documented never-raises/`None` fallback, including a behind/foreign-schema store and a read-only token (`HistoryUnsupported`); no local shadow DB is created.
- [ ] A regression test for the `HistoryUnsupported` case passes both before and after ENH-3657's `_connect_readonly` re-raise lands.
- [ ] `python -m pytest scripts/tests/` passes; the new API behavior is documented.

## Related

- BUG-3652 (done startup/read path correction), ENH-3668 (larger remote-reader feature; independent), FEAT-3535 (remote backend).

## Related Key Documentation

- `docs/reference/API.md` (history reader and backend opener), `docs/reference/CONFIGURATION.md` (remote timeout).

## Status

**Open** | Created: 2026-09-30 | Priority: P4
