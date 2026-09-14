---
id: ENH-3476
type: ENH
title: Persist ll-harness widened evidence (channels + side effects) to harness_events
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-14'
captured_at: '2026-09-14T18:43:06Z'
parent: EPIC-3475
labels:
- evals
- reliability
---

# ENH-3476: Persist ll-harness widened evidence (channels + side effects) to harness_events

## Summary

ENH-3462 widens `ll-harness`'s verdict to a `HarnessEvalOutcome.channels: list[ChannelRecord]` record (stdout/stderr/declared-artifact/git-clean evidence, examined-vs-not-examined) plus per-side-effect pass/fail, but keeps that record in memory only (D4 of ENH-3462's Design → Decisions). Nothing about the widened evidence survives past the single CLI report/`--json` payload — `harness_events` gains no new column, so `ll-session`/`history_reader`/baseline-matching/doctor never see it. This issue is the deferred persistence follow-up ENH-3462's AC13 requires and its Session Log must link.

## Current Behavior

`_record_harness_event()` (`scripts/little_loops/cli/harness.py:214-261`) is the harness CLI's assembly point for `record_attempt()`/`record_harness_event()` writes; `record_attempt()` (`session_store/writers.py:1367-1452`) is the actual write path for 6 of its 7 call sites, `record_harness_event()` for the 7th. `_insert_harness_event()` (`session_store/writers.py:1109-1207`) has a fixed column list (:1156-1164) with no channel-provenance or side-effect-result columns. `HarnessEvent` (`history_reader/harness.py:53-98`) and `_HARNESS_EVENT_COLUMNS` (:101-108) are the read-side counterpart. `HarnessEventVariant` (`observability/schema.py:731-734`) is a third, independent enumeration of the row shape for the DES audit. Once ENH-3462 ships, `outcome.channels` and the side-effect check results exist for every run but are discarded when the process exits — never queryable via `ll-session recent/search --kind harness`, never available to `baseline_for()` (`history_reader/harness.py:315-392`) for cross-run comparison, and absent from `ll-doctor`'s schema-drift check.

## Expected Behavior

`outcome.channels` (serialized, e.g. JSON) and the side-effect check results are persisted alongside every `harness_events` row via a new `SCHEMA_VERSION` migration, readable back through `HarnessEvent` and surfaced through the existing `ll-session --kind harness` / `history_reader` consumers, and validated by `ll-doctor`'s schema-drift check against `schema_manifest.json`. This issue does not change grading logic or add new CLI flags — it only makes the evidence ENH-3462 already computes durable.

## Motivation

Every downstream consumer of a harness verdict — candidate selection, regression detection, improvement loops — currently sees only the in-run report. Without persistence, a baseline comparison, a post-hoc audit, or `ll-session search` cannot distinguish "stderr was never examined" from "stderr was examined and empty" once the run is gone, reproducing ENH-3462's original blind spot one layer downstream.

## Proposed Solution

Follow the v49/v50 `_MIGRATIONS` precedent (`session_store/schema.py:1390-1415`, nullable `ALTER TABLE ADD COLUMN`, no `DEFAULT`, fix-forward only) unless a `CHECK` constraint is needed, in which case follow the `verdict_events.abstention_reason` (v44) full-table-rebuild precedent (`session_store/schema.py:1178-1237`) instead. Thread the new column(s) through `_insert_harness_event()`'s column list/parameter tuple, `record_harness_event()`/`record_attempt()` kwargs, `_record_harness_event()` in `cli/harness.py`, `HarnessEvent`'s trailing-default fields, and `_HARNESS_EVENT_COLUMNS`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — bump `SCHEMA_VERSION` (currently 50) and add the migration entry.
- `scripts/little_loops/session_store/writers.py` — `_insert_harness_event()` (:1109-1207) and `record_harness_event()` (:1210-1299).
- `scripts/little_loops/cli/harness.py` — `_record_harness_event()` (:214-261), the assembly point on the dominant `record_attempt()` write path (6 of 7 call sites: :1762, :1896, :2016, :2135, :2299, :2382; `record_harness_event()` used only at :2276).
- `scripts/little_loops/history_reader/harness.py` — `HarnessEvent` dataclass (:53-98) and `_HARNESS_EVENT_COLUMNS` (:101-108).
- `scripts/little_loops/observability/schema.py` — `HarnessEventVariant` (:731-734, registered in the `DESVariant` registry at :884).
- `scripts/little_loops/session_store/schema_manifest.json` (`harness_events` entry, `:1089`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/doctor.py` — `_schema_manifest`/`_reference_manifest_at` (~:537-540), a second consumer of manifest correctness beyond the test gate.
- `scripts/little_loops/session_store/__init__.py` and `scripts/little_loops/history_reader/__init__.py` — package-level re-export points; no code change expected, confirm the public surface stays in sync.

### Similar Patterns
- v44 `verdict_events.abstention_reason` (`session_store/schema.py:1178-1237`) — the closest end-to-end precedent for a persisted enum/nullable-column addition with an explicit SQL-NULL-vs-Python-None contract documented on both the writer kwarg and reader field.

### Tests
- `scripts/tests/test_session_store_schema.py` — `TestHarnessEventsTable`, `TestHarnessEventsRunModelColumns` (~:1692), `TestHarnessEventsContentPinColumns` (~:2183), `TestHarnessEventsBaselineConditionColumns` (~:3332); the schema-manifest gate classes `test_schema_manifest_matches_checked_in_file` (:3152) and `test_manifest_schema_version_matches_live_schema_version` (:3169); a backfill test modeled on `test_v43_db_upgrades_preserving_existing_rows` (:2753-2787).
- `scripts/tests/test_session_store_writers.py::TestRecordAttemptAndAdmitRetry` (:2492-2723) — the actual write-path test class for `record_attempt()`; extend this, not `TestRecordHarnessEvent`.
- `scripts/tests/test_cli_doctor_install_checks.py::TestSchemaDrift` (:333-533) — extend alongside the schema-manifest gate.
- `scripts/tests/test_history_reader_harness.py` — read-side counterpart to `history_reader/harness.py`.
- `scripts/tests/test_ll_session.py` (`test_recent_kind_harness_outputs_row` / `test_search_kind_harness_matches_indexed_rows`, :1380-1409) — `ll-session recent/search --kind harness` CLI-surface consumer.

### Documentation
- `docs/ARCHITECTURE.md` — schema-migration table (rows through v49/v50, e.g. :670/:682); add the new version row.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — an independent copy of the same migration table (:57-99); already stale ("Current schema version: 45" at :57 vs. code's 50 — fix this drift while touching the table, not just adding a row).
- `docs/reference/EVENT-SCHEMA.md` § "CLI exit-code conventions" (:1795) — states *"Only `RunnerResult.timed_out` is persisted to `harness_events`; `RunnerResult.error` has no column."* — update once new fields are persisted.

## Implementation Steps

1. Design the persisted shape for `outcome.channels` (JSON-serialized `ChannelRecord` list) and side-effect results; decide plain `ALTER TABLE` vs. full-table-rebuild based on whether a `CHECK` constraint is needed.
2. Add the `SCHEMA_VERSION` bump and migration entry in `session_store/schema.py`; update `schema_manifest.json`.
3. Thread the new field(s) through `_insert_harness_event()` → `record_harness_event()`/`record_attempt()` → `_record_harness_event()` in `cli/harness.py`, sourcing from `HarnessEvalOutcome.channels`.
4. Add the trailing-default fields to `HarnessEvent` and extend `_HARNESS_EVENT_COLUMNS`.
5. Register the new columns on `HarnessEventVariant` (`observability/schema.py`).
6. Update `docs/ARCHITECTURE.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/EVENT-SCHEMA.md`.
7. Tests per Integration Map; full suite passes.

## Impact

- **Priority**: P3 — matches ENH-3462; internal-tooling durability follow-up, not a user-facing defect.
- **Effort**: Medium — one schema migration plus threading through ~5 files and their read-side counterparts, following an established migration precedent (v44/v49/v50).
- **Risk**: Low — additive, nullable column(s), fix-forward migration; the only sharper edge is choosing plain `ALTER TABLE` vs. full-table-rebuild if a `CHECK` constraint is wanted on the new field.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: persisting `outcome.channels` and side-effect check results to `harness_events`, plus the schema/manifest/DES/doctor/docs surfaces that follow from a new column.
- **Out of scope**: any change to grading logic, CLI flags, or the in-memory `ChannelRecord`/`HarnessEvalOutcome` shape — those are ENH-3462's scope, already shipped by the time this issue starts. This issue makes existing computed evidence durable; it does not compute new evidence.
- **Out of scope**: `FSMExecutor._evaluate()`'s identical single-channel gap (`fsm/executor.py`) — a separate issue, not persisted through `harness_events` at all.
- **Blocked by**: ENH-3462 (the `channels`/side-effect data this issue persists doesn't exist until ENH-3462 ships).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-14 | Priority: P3
