---
id: ENH-3682
type: ENH
title: Budget best-effort remote prepatch history reads
priority: P4
status: open
relates_to:
- BUG-3652
- ENH-3668
- ENH-3657
blocked_by:
- ENH-3677
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T01:30:56Z'
confidence_score: 86
outcome_confidence: 72
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3682: Budget best-effort remote prepatch history reads

## Summary

Bound the remote advisory reads used by FSM prepatch (`read_base_sha` and `read_base_dirty`) and reuse the remote unreachable marker. This independent latency fix was split from ENH-3668's larger typed-reader work.

## Current Behavior

BUG-3652 made the two prepatch reads remote-aware through relative `DEFAULT_DB_PATH`. They use the standard readonly path with `ensure=True`; a black-holed endpoint can hold the FSM thread for about 10 seconds per read, and these reads do not set the telemetry unreachable marker. A stopped stub fails immediately and does not test the stall.

## Ordering and Exception Contract (2026-09-30 Opus review, revised)

**No longer a prerequisite of ENH-3657** (edge dropped 2026-09-30). ENH-3657 narrows its `_connect_readonly` re-raise to the guard's own `HistoryRemoteRefused` subclass, so remote `ensure_schema` refusals (`HistoryUnsupported` for a behind, foreign or read-only-token store) still degrade to `None`, and `read_base_sha`/`read_base_dirty` use the relative `DEFAULT_DB_PATH`, which the guard never touches. This issue keeps independent value: it removes the ~10 s black-holed-endpoint stall per read and sets the unreachable marker. It is `blocked_by` ENH-3677 because it plans `HranaStub` tests and must use the hoisted `remote` fixture rather than add a seventh copy.

The `best_effort` path still skips ensure **and** catches `HistoryError` including `HistoryUnsupported`, so the never-raises contract of these two readers holds regardless of what any other issue does to `_connect_readonly`.

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
- **Effort:** Small/Medium — one connection seam and two callers; uses the ENH-3677 `remote` fixture.
- **Risk:** Medium — timeout or marker behavior must not leak into normal reads.
- **Breaking Change:** No.

## Acceptance Criteria

- [ ] A black-holed-socket test shows each prepatch read returns `None` within the configured telemetry timeout budget, sets the unreachable marker, and sends no new request while that marker is active.
- [ ] Both readers still return actual remote data through a reachable `HranaStub`; local SQLite and standard reader timeouts remain unchanged.
- [ ] Open and mid-query remote failures preserve each function's documented never-raises/`None` fallback, including a behind/foreign-schema store and a read-only token (`HistoryUnsupported`); no local shadow DB is created.
- [ ] A regression test for the `HistoryUnsupported` case passes both before and after ENH-3657's (narrowed) `_connect_readonly` re-raise lands, whichever order they merge in.
- [ ] `python -m pytest scripts/tests/` passes; the new API behavior is documented.

## Related

- BUG-3652 (done startup/read path correction), ENH-3668 (larger remote-reader feature; independent), FEAT-3535 (remote backend).

## Related Key Documentation

- `docs/reference/API.md` (history reader and backend opener), `docs/reference/CONFIGURATION.md` (remote timeout).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-30_

**Readiness Score**: 86/100 → STOP — ADDRESS GAPS (Dependencies hard override; aggregate would be PROCEED WITH CAUTION)
**Outcome Confidence**: 72/100 → MODERATE

### Concerns
- Only `blocked_by` entry ENH-3677 (hoisted `remote` fixture) is still `open`; the code change itself is unblocked but the planned `HranaStub` tests must use that fixture.
- `LibsqlConnection(..., telemetry=True, read_only=True)` is a new combination; `connect_telemetry` today builds a writer, so read-only plus marker semantics must be verified when adding `connect_readonly_telemetry`.

### Gaps to Address
- Unresolved dependency: ENH-3677 (open). Wait for it, or drop the `blocked_by` edge if the fixture is not needed for the first slice.

### Outcome Risk Factors
- Timeout/marker behavior must not leak into normal reads (Risk: Medium); the `best_effort` kwarg must thread through `_connect_readonly` (~70 callers) without changing defaults.
- Black-holed-socket test is timing-based and can be flaky; keep the budget small and assert on the marker, not wall clock alone.

## Status

**Open** | Created: 2026-09-30 | Priority: P4


## Session Log
- `/ll:confidence-check` - 2026-09-30T05:10:31 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
