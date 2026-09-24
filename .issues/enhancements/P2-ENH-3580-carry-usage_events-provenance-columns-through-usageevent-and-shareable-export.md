---
id: ENH-3580
type: ENH
title: Carry usage_events provenance columns through UsageEvent and shareable export
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T22:26:39Z'
parent: EPIC-3562
labels:
- observability
- multi-host
relates_to:
- ENH-3528
- ENH-3543
---

# ENH-3580: Carry usage_events provenance columns through UsageEvent and shareable export

## Summary

Carry `usage_events` provenance columns (schema v54/v55) through the history reader `UsageEvent` dataclass and the shareable dashboard export. Split out of ENH-3528 (formerly its Implementation Step 4): this slice is independent of ENH-3528's aggregation/labeling work and lower risk, so it can land on its own.

## Current Behavior

- The `UsageEvent` dataclass has nine fields (last: the cost field). The `history_reader.usage` row-listing reader selects only those columns, so v54/v55 metadata (`channel`, `host`, `host_basis`, `provenance`, `scope_kind`, `observed_at`, `observed_at_basis`) and `invocation_id`/`run_id` are invisible to reader consumers.
- `_SHAREABLE_COLUMNS["usage_events"]` (`session_store/queries.py`) lists 12 columns with no provenance; `_SHAREABLE_ALLOWLIST_VERSION = 1`, pinned by `TestAllowlistVersionLockstep` (`PINNED_VERSION`/`PINNED_HASH`) in `test_feat3304_artifact_dashboard.py`.

## Expected Behavior

- Append to `UsageEvent` after `cost_usd`, each defaulting to `None`: `channel`, `host`, `host_basis`, `provenance`, `scope_kind`, `observed_at`, `observed_at_basis`, `invocation_id`, `run_id`. Keyword and positional construction of the existing nine fields keeps working (`_row_to_dataclass` already ignores unmatched keys).
- `recent_usage_events` widens its SELECT to populate them, detecting columns missing from pre-v54/v55 schemas via `PRAGMA table_info` and selecting `NULL` for them. A NULL stored `provenance` surfaces as `"unknown"`; other fields surface NULL as `None`. Filtering, ordering and `LIMIT` stay in SQL.
- Append exactly these columns to `_SHAREABLE_COLUMNS["usage_events"]`: `channel`, `host`, `host_basis`, `provenance`, `scope_kind`, `observed_at`, `observed_at_basis`. Nothing else: no transcript paths, `raw_events` columns or source identifiers.
- Bump `_SHAREABLE_ALLOWLIST_VERSION` to 2. In the same commit set `PINNED_VERSION = 2`, recompute `PINNED_HASH` (`sha256(repr(sorted(_SHAREABLE_COLUMNS.items())))`), and add the v54/v55 columns to the fixture DDL.

## Motivation

Stored provenance is useless to consumers who read it through `history_reader` or a shared dashboard snapshot: both drop the columns today, so an exported token figure cannot be told apart as measured, unknown, verified-host or legacy-host. ENH-3528's labeling needs these fields to reach readers and exports; shipping them separately de-risks ENH-3528 (outcome confidence 63).

## Proposed Solution

Additive only. Extend the dataclass and the one row-listing reader, then extend the shareable allowlist under its existing version-lockstep control. `recent_usage_events` is a row listing, not an aggregation, so it does **not** route through ENH-3528's `select_usage_observations` chokepoint. The shareable export must tolerate DBs that predate v54/v55: select only allowlisted columns that exist in the source table.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/models.py` — `UsageEvent` trailing fields.
- `scripts/little_loops/history_reader/usage.py` — `recent_usage_events` SELECT and old-schema column detection.
- `scripts/little_loops/session_store/queries.py` — `_SHAREABLE_COLUMNS`, `_SHAREABLE_ALLOWLIST_VERSION`.

### Tests

- `scripts/tests/test_feat3304_artifact_dashboard.py` — `PINNED_VERSION`/`PINNED_HASH`, fixture DDL, exact-column-set test.
- `scripts/tests/test_history_reader_usage.py` — new fields, NULL→`"unknown"`, pre-v54/v55 schemas.

## Implementation Steps

1. Add the `UsageEvent` trailing fields; widen `recent_usage_events` with `PRAGMA table_info` column detection and NULL→`"unknown"` provenance.
2. Append the seven shareable columns, bump the allowlist to v2, update `PINNED_VERSION`/`PINNED_HASH` and the fixture DDL in the same commit; confirm pre-v55 export tolerance.
3. Update docs; run focused tests (`test_history_reader_usage.py`, `test_feat3304_artifact_dashboard.py`), then the full suite, lint and mypy.

## Program Design

### Types

- `UsageEvent` (dataclass) gains nine trailing `str | None` fields defaulting to `None`: `channel`, `host`, `host_basis`, `provenance`, `scope_kind`, `observed_at`, `observed_at_basis`, `invocation_id`, `run_id`.

### Signatures

- `recent_usage_events(session_id: str | None = None, model: str | None = None, *, since: str | None = None, limit: int = 20, db: Path | str = DEFAULT_DB_PATH) -> list[UsageEvent]` — unchanged signature; widened SELECT with `PRAGMA table_info` column detection.
- `_SHAREABLE_COLUMNS: dict[str, list[str]]` — `usage_events` list gains seven columns; `_SHAREABLE_ALLOWLIST_VERSION: int` becomes 2.

### Call Path

- `recent_usage_events` → `_row_to_dataclass` → `UsageEvent` (NULL `provenance` → `"unknown"`).
- `ll-artifact dashboard --mode shareable` → `_SHAREABLE_COLUMNS` filter → exported `usage_events` rows.

## Impact

- **Priority**: P2 — enables provenance-aware downstream consumers of readers/exports.
- **Effort**: Small.
- **Risk**: Low — additive fields and columns; the allowlist change is gated by the lockstep test.
- **Breaking Change**: No (shareable exports gain columns; allowlist version stamp changes 1 → 2).

## Acceptance Criteria

- [ ] `UsageEvent` gains the nine trailing fields with `None` defaults; existing positional/keyword constructions and iterator consumers are unchanged.
- [ ] `recent_usage_events` populates the new fields, surfaces NULL `provenance` as `"unknown"`, and reads pre-v54 and pre-v55 schemas without error.
- [ ] `_SHAREABLE_COLUMNS["usage_events"]` gains exactly the seven listed columns (a test asserts the exact set); the allowlist version is 2 and the pinned hash is updated; the existing free-text/absolute-path exclusion test still passes.
- [ ] Shareable dashboard export of a v55 fixture includes the new columns; a pre-v55 DB exports without error.
- [ ] `docs/reference/API.md` documents the new `UsageEvent` fields; the dashboard/export docs list the shareable additions.

## Scope Boundaries

- **In scope**: `UsageEvent` fields, `recent_usage_events` SELECT, shareable allowlist v2 and its lockstep test/fixture.
- **Out of scope**: provenance labeling, aggregation metadata, `token_provenance` and the `select_usage_observations` chokepoint (ENH-3528); coverage selection (ENH-3543).

## Related Key Documentation

- `docs/reference/API.md` — `little_loops.history_reader` (`UsageEvent`, `recent_usage_events`).
- `docs/guides/HISTORY_SESSION_GUIDE.md` — shareable export columns.

## Status

**Open** | Created: 2026-09-24 | Priority: P2
