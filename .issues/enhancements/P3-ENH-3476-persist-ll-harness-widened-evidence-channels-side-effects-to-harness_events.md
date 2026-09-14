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
blocked_by: []
reconcile_attempted: true
confidence_score: 80
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3476: Persist ll-harness widened evidence (channels + side effects) to harness_events

## Summary

ENH-3462 widens `ll-harness`'s verdict to a `HarnessEvalOutcome.channels: list[ChannelRecord]` record (stdout/stderr/declared-artifact/git-clean evidence, examined-vs-not-examined) plus per-side-effect pass/fail, but keeps that record in memory only (D4 of ENH-3462's Design → Decisions). Nothing about the widened evidence survives past the single CLI report/`--json` payload — `harness_events` gains no new column, so `ll-session`/`history_reader`/baseline-matching/doctor never see it. This issue is the deferred persistence follow-up ENH-3462's AC13 requires and its Session Log must link.

## Current Behavior

`_record_harness_event()` (`scripts/little_loops/cli/harness.py:214-261`) is the harness CLI's assembly point for `record_attempt()`/`record_harness_event()` writes; `record_attempt()` (`session_store/writers.py:1367-1452`) is the actual write path for 6 of its 7 call sites, `record_harness_event()` for the 7th. `_insert_harness_event()` (`session_store/writers.py:1109-1207`) has a fixed column list (:1156-1164) with no channel-provenance or side-effect-result columns. `HarnessEvent` (`history_reader/harness.py:53-98`) and `_HARNESS_EVENT_COLUMNS` (:101-108) are the read-side counterpart. `HarnessEventVariant` (`observability/schema.py:731-734`) is a third, independent enumeration of the row shape for the DES audit. Once ENH-3462 ships, `outcome.channels` and the side-effect check results exist for every run but are discarded when the process exits — never queryable via `ll-session recent/search --kind harness`, never available to `baseline_for()` (`history_reader/harness.py:315-392`) for cross-run comparison, and absent from `ll-doctor`'s schema-drift check.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- ENH-3462 has landed (status: Completed, confirmed 2026-09-14). `ChannelRecord` (`cli/harness.py:832`) and `HarnessEvalOutcome.channels: list[ChannelRecord]` (`cli/harness.py:872`) exist in the tree today and are fully wired: `_grade()` (`:1224`) composes the channel list every invocation (stdout/stderr at `:1269-1276`, side-effect channels at `:1277-1280`), and `_evaluate_and_report()` (`:1948`) is the sole current consumer, rendering `outcome.channels` into the `--output json` payload's `"channels"` key and the text `Channels:` block. This issue's `blocked_by: ENH-3462` is now satisfied — the persistence gap below is confirmed directly against landed code, not inferred from a not-yet-shipped dependency.
- Confirmed precisely: `outcome.channels` is never forwarded into any of the five `_record_harness_event()`/`_record()` call sites (`cmd_skill::_record` :2139, `cmd_cmd::_record` :2273, `cmd_mcp::_record` :2393, `cmd_prompt::_record` :2512, `cmd_dsl` :2676/:2772) — each extracts only `.verdict`/`.abstained`/`.passed` from `outcome`. `_record_harness_event()` itself has no `channels`/`side_effects` parameter in its signature.
- `_insert_harness_event()` (`session_store/writers.py:1109`) has a CLOSED keyword-only parameter list, not a `**kwargs` sink — `record_attempt()` forwards its `**event_fields` unvalidated (needs no code change for new kwargs), but `_insert_harness_event()` and `record_harness_event()` both require explicit new named parameters for `channels_json`/`side_effects_json`, or passing either today raises `TypeError: unexpected keyword argument`.
- `_row_to_dataclass()` (`history_reader/_base.py:87-91`) does zero NULL-coercion, but it maps only columns present in `row.keys()` — the columns actually named in the SQL SELECT that produced the row. A new `harness_events` column is invisible to `HarnessEvent` construction unless added to BOTH the dataclass fields (`history_reader/harness.py:54-98`) AND the `_HARNESS_EVENT_COLUMNS` string (`:101-108`, spliced into 5 separate SELECT statements at lines 125, 160, 185, 211, 339).

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
- `scripts/little_loops/cli/harness.py` — `_record_harness_event()` (:214-261), the assembly point on the dominant `record_attempt()` write path, fed by 5 nested `_record()` call sites that currently extract only `.verdict`/`.abstained`/`.passed` from `outcome` (`cmd_skill::_record` :2139, `cmd_cmd::_record` :2273, `cmd_mcp::_record` :2393, `cmd_prompt::_record` :2512, `cmd_dsl` :2676/:2772; `record_harness_event()` used only at one of these).
- `scripts/little_loops/history_reader/harness.py` — `HarnessEvent` dataclass (:53-98) and `_HARNESS_EVENT_COLUMNS` (:101-108).
- `scripts/little_loops/session_store/schema_manifest.json` (`harness_events` entry, `:1089`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/doctor.py` — `_schema_manifest`/`_reference_manifest_at` (~:537-540), a second consumer of manifest correctness beyond the test gate.
- `scripts/little_loops/session_store/__init__.py` and `scripts/little_loops/history_reader/__init__.py` — package-level re-export points; no code change expected, confirm the public surface stays in sync.

### Similar Patterns
- `semantic_evidence: str | None` (`session_store/writers.py:1180`) — the closest precedent for `channels_json`/`side_effects_json`: a free-text/JSON `harness_events` column that passes through with zero NULL-coercion code on either the write (`writers.py`) or read (`history_reader/_base.py:87-91`) side.
- v49/v50 plain `ALTER TABLE ADD COLUMN` (`session_store/schema.py`) — the applicable migration-mechanism precedent, since no `CHECK` constraint is contemplated on the new columns; the v44 full-table-rebuild pattern does not apply here.

### Tests
- `scripts/tests/test_session_store_schema.py` — `TestHarnessEventsTable`, `TestSchemaV49HarnessRunModel` (:1691), `TestSchemaV39HarnessContentPin` (:2182), `TestSchemaV50BaselineConditions` (:3331); the schema-manifest gate classes `test_schema_manifest_matches_checked_in_file` (:3152) and `test_manifest_schema_version_matches_live_schema_version` (:3169); a backfill test modeled on `test_v43_db_upgrades_preserving_existing_rows` (:2753-2787).
- `scripts/tests/test_cli_harness.py` — the CLI-integration layer where the v50 baseline-condition columns' write-path round-trip tests actually live (e.g. `:2958-2964`, asserting `row["conditions_fp"]`/`row["subject_model"]` after a CLI-level `measure` invocation); add the `channels_json`/`side_effects_json` round-trip assertion here, following that precedent — not `test_session_store_writers.py::TestRecordAttemptAndAdmitRetry`, which tests retry-admission mechanics only and carries no free-text/JSON column round-tripping today.
- `scripts/tests/test_cli_doctor_install_checks.py::TestSchemaDrift` (:333-533) — extend alongside the schema-manifest gate.
- `scripts/tests/test_history_reader_harness.py` — read-side counterpart to `history_reader/harness.py`.
- `scripts/tests/test_ll_session.py` (`test_recent_kind_harness_outputs_row` / `test_search_kind_harness_matches_indexed_rows`, :1380-1409) — `ll-session recent/search --kind harness` CLI-surface consumer.

### Documentation
- `docs/ARCHITECTURE.md` — schema-migration table (rows through v49/v50, e.g. :670/:682); add the new version row.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — an independent copy of the same migration table (:57-99); already stale ("Current schema version: 45" at :57 vs. code's 50 — fix this drift while touching the table, not just adding a row).
- `docs/reference/EVENT-SCHEMA.md` § "CLI exit-code conventions" (:1795) — states *"Only `RunnerResult.timed_out` is persisted to `harness_events`; `RunnerResult.error` has no column."* — update once new fields are persisted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `_insert_harness_event()`'s INSERT column order (`writers.py:1156-1164`) is 29 columns; the free-text `semantic_evidence: str | None` column — the closest existing precedent for `channels_json`/`side_effects_json` — passes through with zero NULL-coercion code (`writers.py:1180`); only the 3 bool-typed kwargs (`semantic_passed`, `timed_out`, `dirty`) get explicit `None if x is None else int(x)` handling. The new JSON columns need no special-case coercion.
- `record_attempt()` (`writers.py:1367-1452`) forwards an unvalidated `**event_fields` dict straight through to `_insert_harness_event()` — confirmed directly. A new kwarg `_record_harness_event()` passes (e.g. `channels_json`) flows through `record_attempt()` with **no code change required inside `record_attempt()`'s own body**.
- Read side: `_row_to_dataclass()` (`history_reader/_base.py:87-91`) does a plain `row[k] for k in field_names if k in row.keys()` mapping; sqlite3's default adapter maps SQL `NULL` to Python `None` automatically for any column type. The `semantic_evidence` precedent carries no custom NULL-handling code on either the write or read side — the same zero-special-casing applies to the new columns.
- `ll-doctor`'s schema-drift check (`cli/doctor.py` ~:520-591) replays `_MIGRATIONS` to the DB's recorded version and diffs against the live PRAGMA schema — a new `_MIGRATIONS` entry alone is sufficient for drift detection to pick up the new columns; no separate registration step in `doctor.py` is needed. `schema_manifest.json`'s `"harness_events"` entry (:1089-1273, 29 column objects today) still needs a manual two-entry append, or `test_schema_manifest_matches_checked_in_file` (`test_session_store_schema.py:3152`) fails.
- Confirmed by direct code read (not just issue frontmatter): ENH-3462 has **not landed**. `ChannelRecord` and `HarnessEvalOutcome.channels` do not exist anywhere in `scripts/` (repo-wide grep, zero hits); `HarnessEvalOutcome` (`cli/harness.py:796-804`) is unchanged from its pre-ENH-3462 shape (`passed`, `verdict`, `eval_result`, `abstained`, `sample_pass_rate`, `samples` only). This confirms the `blocked_by: ENH-3462` edge is accurate and current, not stale.

## Program Design

### Types

- `HarnessEvalOutcome.channels: list[ChannelRecord]` — already added in-memory by ENH-3462 (`cli/harness.py`); this issue does not change its shape, only serializes it.
- `channels_json: str | None` — new `harness_events` column, JSON-serialized `list[ChannelRecord]` (mirrors the existing `semantic_evidence: str | None` free-text-JSON column precedent).
- `side_effects_json: str | None` — new `harness_events` column, JSON-serialized per-side-effect pass/fail results.

### Signatures

- `_insert_harness_event(conn: sqlite3.Connection, *, ..., channels_json: str | None = None, side_effects_json: str | None = None) -> int` (`session_store/writers.py:1109`)
- `record_harness_event(db_path: Path | str, *, ..., channels_json: str | None = None, side_effects_json: str | None = None) -> int` (`session_store/writers.py:1210`)
- `_record_harness_event(*, ..., channels_json: str | None = None, side_effects_json: str | None = None) -> int | None` (`cli/harness.py:214`)
- `HarnessEvent` (`history_reader/harness.py:53`) gains trailing-default fields `channels_json: str | None = None` and `side_effects_json: str | None = None`; `_HARNESS_EVENT_COLUMNS` (`:101`) appends both names.

### Call Path

`_record_harness_event` (`cli/harness.py:214`, sourcing `outcome.channels` from `HarnessEvalOutcome`) → `record_attempt` (`session_store/writers.py:1367`, the dominant 6-of-7 write path) → `_insert_harness_event` (`session_store/writers.py:1109`) → read back via `HarnessEvent` / `_HARNESS_EVENT_COLUMNS` (`history_reader/harness.py:53-108`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Migration-pattern precision: v49's `attempt_kind` column (`session_store/schema.py`) adds a `CHECK` constraint inline on a **new** column via `ALTER TABLE harness_events ADD COLUMN attempt_kind TEXT CHECK (...)` — SQLite permits a `CHECK` on a column added via `ADD COLUMN`; the v44 full-table-rebuild is only required to add a `CHECK` to an **already-existing** column. Since `channels_json`/`side_effects_json` are plain nullable TEXT with no constraint contemplated, the v49/v50 plain-`ALTER TABLE`-per-column pattern applies outright — even a future `CHECK` on these new columns themselves would still not require the v44 rebuild pattern.
- `HarnessEventVariant` (`observability/schema.py:731-734`) and its base `DESVariant` (:21-30) carry no column-level fields for *any* existing `harness_events` column, including the v49/v50 columns already shipped — the class is a one-field (`type: Literal["harness_event"]`) audit-registry entry confirming a write call site is covered, not a per-column schema declaration. Adding `channels_json`/`side_effects_json` does not require touching this file. See `⚠ Superseded` marker under Implementation Steps.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `SCHEMA_VERSION` (`session_store/schema.py:25`) is a hand-maintained int, independently asserted equal to `len(_MIGRATIONS)` by `test_schema_version_matches_migrations_length` (`test_session_store_schema.py:2345-2350`, guarding against the two silently desyncing per a prior BUG-3241 finding) — must be bumped to 51 by hand alongside the new migration entry.
- `schema_manifest.json` is auto-generated, not hand-typed: `TestSchemaManifest`'s class docstring (`test_session_store_schema.py:3132-3147`) documents a `python -c "..."` one-liner that builds a fresh DB via `ensure_db()`, calls `_schema_manifest(conn)` (`schema.py:1612`), and writes the JSON — regenerate and commit via that script rather than hand-editing the checked-in file.
- Confirmed migration-pattern choice is correct: SQLite's `ALTER TABLE` cannot add a `CHECK` to an already-existing column (v44's full-table-rebuild for `verdict_events.verdict`/`abstention_reason` exists only for that reason), but a `CHECK` on a brand-new column uses plain `ALTER TABLE ADD COLUMN` with no rebuild (v49's `attempt_kind TEXT CHECK (...)`, `schema.py:1373-1374`, is the precedent). Since `channels_json`/`side_effects_json` need no `CHECK` at all, the plain v49/v50 `ALTER TABLE` pattern applies outright.
- Correction: the exact test class names cited in this issue's Integration Map/Tests sections do not match current code — `TestHarnessEventsRunModelColumns`, `TestHarnessEventsContentPinColumns`, and `TestHarnessEventsBaselineConditionColumns` do not exist. The actual classes are `TestSchemaV49HarnessRunModel` (`test_session_store_schema.py:1691`), `TestSchemaV39HarnessContentPin` (`:2182`), and `TestSchemaV50BaselineConditions` (`:3331`) — use these names when extending the fresh-DB/upgrade-DB/round-trip triad.
- `TestRecordAttemptAndAdmitRetry` (`test_session_store_writers.py:2492`) tests repetition-allocation and retry-admission mechanics only — it carries no free-text/JSON column round-tripping today. The v50 baseline-condition columns' actual write-path round-trip tests instead live in `test_cli_harness.py` at the CLI-integration layer (e.g. `:2958-2964`, asserting `row["conditions_fp"]`/`row["subject_model"]` after a CLI-level `measure` invocation) — a `channels_json`/`side_effects_json` round-trip test likely belongs at that same CLI-integration layer, not inside `TestRecordAttemptAndAdmitRetry`.

## Implementation Steps

1. Add `channels_json: str | None` and `side_effects_json: str | None` as plain nullable `TEXT` columns via the v49/v50 `ALTER TABLE ADD COLUMN` pattern — no `CHECK` constraint is needed, so the v44 full-table-rebuild path does not apply.
2. Add the `SCHEMA_VERSION` bump and migration entry in `session_store/schema.py`; update `schema_manifest.json`.
3. Thread the new field(s) through `_insert_harness_event()` → `record_harness_event()`/`record_attempt()` → `_record_harness_event()` in `cli/harness.py`, sourcing from `HarnessEvalOutcome.channels`. No NULL-coercion handling is needed, mirroring `semantic_evidence`.
4. Add the trailing-default fields to `HarnessEvent` and extend `_HARNESS_EVENT_COLUMNS`.
5. Update `docs/ARCHITECTURE.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/EVENT-SCHEMA.md`.
6. Tests per Integration Map; full suite passes.

## Impact

- **Priority**: P3 — matches ENH-3462; internal-tooling durability follow-up, not a user-facing defect.
- **Effort**: Medium — one schema migration plus threading through ~5 files and their read-side counterparts, following an established migration precedent (v44/v49/v50).
- **Risk**: Low — additive, nullable column(s), fix-forward migration; the only sharper edge is choosing plain `ALTER TABLE` vs. full-table-rebuild if a `CHECK` constraint is wanted on the new field.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: persisting `outcome.channels` and side-effect check results to `harness_events`, plus the schema/manifest/DES/doctor/docs surfaces that follow from a new column.
- **Out of scope**: any change to grading logic, CLI flags, or the in-memory `ChannelRecord`/`HarnessEvalOutcome` shape — those are ENH-3462's scope, already shipped by the time this issue starts. This issue makes existing computed evidence durable; it does not compute new evidence.
- **Out of scope**: `FSMExecutor._evaluate()`'s identical single-channel gap (`fsm/executor.py`) — a separate issue, not persisted through `harness_events` at all.
- **Blocked by**: none — ENH-3462 has landed; `ChannelRecord`/`HarnessEvalOutcome.channels` exist and are fully wired in `cli/harness.py` today (confirmed 2026-09-14), so the evidence this issue persists is already available.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-14 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-14_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 97/100 → HIGH CONFIDENCE

### Gaps to Address
- `blocked_by: ENH-3462` is unresolved (status: open). `ChannelRecord`/`HarnessEvalOutcome.channels` do not exist in `scripts/` yet, so this issue cannot begin implementation until ENH-3462 ships. Otherwise-well-specified (Criteria 1-4 all scored 20/20); this is the sole blocker.


## Session Log
- `/ll:reconcile-issue` - 2026-09-14T21:32:26 - `f4a1cb05-beaf-4c89-a67b-0a34555443d6.jsonl`
- `/ll:refine-issue` - 2026-09-14T21:18:34 - `b80e42ca-40bb-4d8a-b6d8-3b9dab6f1bf1.jsonl`
- `/ll:confidence-check` - 2026-09-14T18:58:05 - `cef18a0e-5855-4ab1-ba23-37a7d36518ff.jsonl`
- `/ll:reconcile-issue` - 2026-09-14T18:55:40 - `6c2e05b8-05cf-4d8d-b2b6-1b2ad05e6c8f.jsonl`
- `/ll:refine-issue` - 2026-09-14T18:53:00 - `20027762-fa98-4cf8-8ef8-31f8f3facf83.jsonl`
- `/ll:format-issue` - 2026-09-14T18:46:16 - `6d894000-c098-410e-9d4d-4df5e3c75319.jsonl`
