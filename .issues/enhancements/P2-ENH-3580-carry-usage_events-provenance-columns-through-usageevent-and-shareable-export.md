---
id: ENH-3580
type: ENH
title: Carry usage_events provenance columns through UsageEvent and shareable export
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T22:26:39Z'
completed_at: '2026-09-27T10:15:55Z'
parent: EPIC-3562
labels:
- observability
- multi-host
relates_to:
- ENH-3528
- ENH-3543
confidence_score: 98
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

### Export boundary with ENH-3543

This issue remains independently implementable and exports raw observation metadata only. Seven additional columns do not prove live/rollout reconciliation, and `recent_usage_events` must remain a raw row listing. ENH-3543 owns a privacy-safe selection/qualification representation in snapshots, built-in dashboard aggregation, and an exported-snapshot-versus-source regression for matched/partial/unresolved coverage. It must preserve qualification when private source identifiers are omitted. Any later allowlist expansion receives a new version/hash; it must not silently redefine this issue's v2 seven-column contract. Docs must distinguish raw row provenance from aggregate coverage claims.

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

- [x] Raw row listings/exports retain their observation semantics; docs do not claim that the seven-column projection reconciles overlap. ENH-3543 owns selected aggregate/export parity and any subsequent allowlist version.

- [x] `UsageEvent` gains the nine trailing fields with `None` defaults; existing positional/keyword constructions and iterator consumers are unchanged.
- [x] `recent_usage_events` populates the new fields, surfaces NULL `provenance` as `"unknown"`, and reads pre-v54 and pre-v55 schemas without error.
- [x] `_SHAREABLE_COLUMNS["usage_events"]` gains exactly the seven listed columns (a test asserts the exact set); the allowlist version is 2 and the pinned hash is updated; the existing free-text/absolute-path exclusion test still passes.
- [x] Shareable dashboard export of a v55 fixture includes the new columns; a pre-v55 DB exports without error.
- [x] `docs/reference/API.md` documents the new `UsageEvent` fields; the dashboard/export docs list the shareable additions.

## Scope Boundaries

- **In scope**: `UsageEvent` fields, `recent_usage_events` SELECT, shareable allowlist v2 and its lockstep test/fixture.
- **Out of scope**: provenance labeling, aggregation metadata, `token_provenance` and the `select_usage_observations` chokepoint (ENH-3528); coverage selection (ENH-3543).

## Related Key Documentation

- `docs/reference/API.md` — `little_loops.history_reader` (`UsageEvent`, `recent_usage_events`).
- `docs/guides/HISTORY_SESSION_GUIDE.md` — shareable export columns.

## Resolution

Implemented as specified. `UsageEvent` (`history_reader/models.py`) gains the
nine trailing `str | None = None` fields. `recent_usage_events`
(`history_reader/usage.py`) detects present columns via `PRAGMA
table_info(usage_events)` and selects `NULL`/`COALESCE(provenance, 'unknown')`
for absent ones via a new `_USAGE_EVENT_OPTIONAL_COLUMNS` tuple (narrower than
the existing `_OPTIONAL_USAGE_COLUMNS` used by `select_usage_observations` —
excludes `state` and `provider_vendor`, out of scope here).
`_SHAREABLE_COLUMNS["usage_events"]` (`session_store/queries.py`) gains the
seven columns; `_SHAREABLE_ALLOWLIST_VERSION` bumped to 2.
`_snapshot_select` now takes the open `conn` and intersects the allowlist with
`PRAGMA table_info(table)` so a pre-v54/v55 source DB exports only the columns
it actually has, instead of raising `sqlite3.OperationalError`. Tests added to
`test_history_reader_usage.py::TestUsageEventReaders` (provenance population,
NULL→`"unknown"`, pre-v54 schema via a patched `_connect_readonly`, since the
normal read path migrates the DB before every query) and
`test_feat3304_artifact_dashboard.py` (fixture DDL gains an
`include_provenance_columns` toggle; new `test_pre_v55_db_exports_without_error`;
`TestAllowlistVersionLockstep` pinned hash updated). Docs updated:
`docs/reference/API.md` gains a `UsageEvent` / `recent_usage_events` section;
`docs/reference/CLI.md`'s `ll-artifact dashboard` section documents the v2
allowlist columns and pre-v55 tolerance.

Full suite: 26822 passed, 1 pre-existing unrelated failure
(`test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo`,
confirmed failing on unmodified `main` via `git stash`). `ruff check` clean;
`mypy` clean except 4 pre-existing errors in untouched
`cli/loop/cleanup.py`.

## Status

**Done** | Created: 2026-09-24 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- Pre-v55 export tolerance is a stated requirement, but `session_store/queries.py` has no `PRAGMA table_info` handling today; check how the shareable export selects columns (Step 2).

## Session Log
- `/ll:manage-issue` - 2026-09-27T10:14:54 - `5367b437-ba01-4119-ba04-0245b00cfd97.jsonl`
- `/ll:confidence-check` - 2026-09-25T01:02:59 - `42a934e3-5df9-4ac6-9296-d0ced0bc2261.jsonl`
