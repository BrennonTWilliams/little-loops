---
id: FEAT-3721
type: FEAT
title: ll-next shared read-only HistorySnapshot reader
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T01:29:51Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
blocks:
- FEAT-3711
- FEAT-3713
relates_to:
- ENH-3720
- ENH-3679
---

# FEAT-3721: ll-next shared read-only HistorySnapshot reader

## Summary

Add one injected, **local-SQLite-only** (v1) read-only `HistorySnapshot` reader for ll-next consumers. Split out of FEAT-3711 (Opus review, 2026-10-03) so FEAT-3713 (sprint recency from `cli_events`) and FEAT-3711 (`recommendation_events` lookup) share it without FEAT-3713 depending on FEAT-3711's migration/events work. FEAT-3561 stays history-free; this slice is where the first history read enters.

## Current Behavior

No ll-next history reader exists. Existing readers either create/migrate stores or use write-capable telemetry helpers.

## Expected Behavior

- `read_history_snapshot(store, *, as_of: datetime) -> HistorySnapshot` opens the resolved local store read-only through the existing backend chokepoint, never creates/migrates a store, honors `LL_HISTORY_DB` and project access checks, and returns typed per-source/table availability plus diagnostics. Remote (libsql/Hrana) targets report `unavailable(remote_unsupported_v1)`; remote support follows ENH-3720.
- One UTC `as_of`; bounded indexed queries with finite row budgets; the existing short busy timeout bounds lock waits. If a row cap prevents proving the newest qualified activity, the result is `partial`/unknown, never exact.
- Missing file/table, old schema, suppressed backend or lock timeout yields unavailable data, not an exception or guessed negative evidence. A missing `recommendation_events` table cannot erase valid `cli_events`/`loop_runs` data.
- No cache/marker file writes; no `connect_telemetry`.

## Scope Boundaries

- **In scope:** the reader, typed availability/diagnostics, bounded queries for `cli_events`, `loop_runs`, `orchestration_runs`, and (once FEAT-3711 lands) `recommendation_events`; tests for absent/old-schema/suppressed/locked/row-budget-saturated states.
- **Out of scope:** schema migration and events (FEAT-3711), producer/acceptance attribution and pressure (FEAT-3722, deferred), remote deadline budget (ENH-3720).

## Program Design

### Types

- Immutable `HistorySnapshot(availability_by_source, rows_by_source, diagnostics, as_of)`; availability is `available | partial | unavailable(reason)` per source.

### Signatures

- `read_history_snapshot(store, *, as_of: datetime, sources: Sequence[str]) -> HistorySnapshot` — read-only, fail-soft; reads only the requested sources/time slices.

### Call Path

CLI/generator → `read_history_snapshot` → backend read-only connect (existing chokepoint) → bounded indexed queries → typed snapshot.

## Acceptance Criteria

- [ ] Read-only; never creates/migrates a store or writes cache/marker files; honors `LL_HISTORY_DB` and project access checks.
- [ ] Per-source availability with tested absent/old-schema/suppressed/locked/remote-unsupported degradation; row-budget saturation cannot yield false exact results.
- [ ] Indexed bounded queries; tests prohibit full-store scans.
- [ ] Documented in `API.md`; `python -m pytest scripts/tests/` passes.

## Impact

- **Priority**: P3 — shared seam for FEAT-3711 and FEAT-3713.
- **Effort**: Small–Medium.
- **Risk**: Low — read-only, fail-soft.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-10-04 | Priority: P3
