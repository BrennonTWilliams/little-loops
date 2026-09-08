---
id: ENH-3406
title: harness_events run-model columns + harness_admissions table (schema)
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
parent: ENH-3397
labels:
- harness
- evaluation
- statistics
---

# ENH-3406: harness_events run-model columns + harness_admissions table (schema)

## Summary

Add the schema foundation for ll-harness's run model: new columns on `harness_events`
(`cell_key`, `repetition`, `attempt_kind`, `continuations`, `superseded_by`) and a new
append-only `harness_admissions` audit table. First of three issues decomposed from
ENH-3397 (schema → writers/gate → read-path counting). This issue is additive schema
only — no existing CLI command's behavior changes here.

## Parent Issue

Decomposed from ENH-3397: Distinguish repetition, infrastructure retry, and continuation
in ll-harness.

## Design Decisions (inherited from parent)

- Cell identity: `cell_key = (target, task, subject)` where `subject = runner_label +
  head_sha`; `repetition` is a stamped index per cell, reused (not incremented) by an
  `infra_retry`.
- Admission reason enum: `timeout | host_crash | harness_error | network` — no free-text.
- `harness_admissions` is INSERT-only (matches `hook_events`/`test_run_events`/
  `commit_events` precedent in `writers.py`), never updated or deleted — the contrasting
  UPSERT shape (`correction_retirements`) does not apply here.

## Files to Modify

- `scripts/little_loops/session_store/schema.py` — add `cell_key`/`repetition`/
  `attempt_kind`/`continuations`/`superseded_by` columns to `harness_events` via an
  additive migration in `_MIGRATIONS` (next `SCHEMA_VERSION`, currently 47), following the
  "Fix-forward only" comment convention (`schema.py:931,947-948,973,1011-1018`). Add a new
  `harness_admissions` table: `attempt_id`, `superseded_id`, `reason`
  (`Literal["timeout","host_crash","harness_error","network"]`), `ts`.
- Registry decision: `harness_admissions` needs an explicit kinded (`VALID_KINDS` +
  `_KIND_TABLE` entry, `schema.py:27-83`) vs. kindless (`_KINDLESS_TABLES`,
  `schema.py:85-100`) placement — mirror the `credential_scope_events` precedent (v47,
  ENH-3204): `VALID_KINDS`/`_KIND_TABLE` entries plus a companion test asserting
  `"harness_admissions" not in _KINDLESS_TABLES` (`test_session_store_schema.py:2800-2812`
  is the worked example).
- Decide whether `harness_admissions` needs an `_EXPORT_TABLE_MAP` entry
  (`session_store/queries.py:88-134`) for `ll-history export` symmetry with
  `harness_events`.
- `scripts/little_loops/session_store/lifecycle.py:930-941` — add `harness_admissions` to
  the `_REBUILD_TABLES` exclusion comment alongside `harness_events` (documentation only;
  `rebuild()` already excludes new tables by default).
- `scripts/little_loops/session_store/schema_manifest.json` — regenerate after the DDL
  change (recipe in `test_session_store_schema.py:2852-2865`);
  `test_schema_manifest_matches_checked_in_file` fails otherwise.
- `docs/guides/HISTORY_SESSION_GUIDE.md:91-101,142` — add a new row to the
  schema-version-history table and update the line-142 `harness_events` prose to mention
  the new columns/table.
- `docs/ARCHITECTURE.md:142` — update the one-line `harness_events` description.

## Tests

- `scripts/tests/test_session_store_schema.py` — follow the existing `harness_events`
  migration coverage shape (`test_harness_events_columns` 1573,
  `test_harness_events_indexes_exist` 1604, `test_v30_db_upgrades_gains_harness_events`
  1621, `test_harness_is_kinded` 1635, `test_harness_events_excluded_from_rebuild_tables`
  1639): add equivalents for the new columns and a
  `test_vNN_db_upgrades_gains_harness_admissions`-style test, plus the kinded/kindless
  companion assertion.

## Acceptance Criteria

- `harness_events` gains `cell_key`, `repetition`, `attempt_kind` (`repetition` |
  `infra_retry`), `continuations` (nullable int) and `superseded_by` (nullable attempt
  id). Schema migration, live-write-only like the rest of the table.
- A new `harness_admissions` table exists: `attempt_id`, `superseded_id`, typed `reason`
  (`timeout` | `host_crash` | `harness_error` | `network`), `ts`.
- `schema_manifest.json` regenerated and `test_schema_manifest_matches_checked_in_file`
  passes.
- `harness_admissions` has a resolved kinded-vs-kindless registry placement with a
  companion test.

## Scope Boundaries

- **In scope**: schema/table DDL, migration tests, registry placement decision,
  schema_manifest regen, `HISTORY_SESSION_GUIDE.md`/`ARCHITECTURE.md` updates for the new
  columns/table.
- **Out of scope**: any writer function that populates these columns (ENH-3407), any
  read-path logic that consumes them (ENH-3408), the `--retry-of` CLI flag (ENH-3407), the
  "no UPDATE/DELETE path" writer test (ENH-3407 — it targets `writers.py` source, not
  `schema.py`).

## Impact

- **Priority**: P1 — inherited from parent; this is the foundation the anti-p-hacking gate
  depends on.
- **Effort**: Small — additive schema migration only, no behavior change.
- **Risk**: Low — additive columns/table, no existing code path reads or writes them yet.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-08 | Priority: P1


## Session Log
- `/ll:issue-size-review` - 2026-09-08T05:34:24 - `5401886d-ebfd-404a-b6ba-9a7d5e921ddb.jsonl`
