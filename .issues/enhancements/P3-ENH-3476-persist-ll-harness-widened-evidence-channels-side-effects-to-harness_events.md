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
confidence_score: 100
verify_verdict: VALID
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3476: Persist ll-harness widened evidence (channels + side effects) to harness_events

## Summary

ENH-3462 widens `ll-harness`'s verdict to a `HarnessEvalOutcome.channels: list[ChannelRecord]` record (stdout/stderr/declared-artifact/git-clean evidence, examined-vs-not-examined) plus per-side-effect pass/fail, but keeps that record in memory only (D4 of ENH-3462's Design → Decisions). Nothing about the widened evidence survives past the single CLI report/`--json` payload — `harness_events` gains no new column (this issue adds exactly one, `channels_json`; the side-effect results ride along as `passed` on each channel entry, so no second column), so `ll-session`/`history_reader`/baseline-matching/doctor never see it. This issue is the deferred persistence follow-up ENH-3462's AC13 requires and its Session Log must link.

## Current Behavior

`_record_harness_event()` (`scripts/little_loops/cli/harness.py:216-309`) is the harness CLI's assembly point for `record_attempt()`/`record_harness_event()` writes; `record_attempt()` (`session_store/writers.py:1398-1483`) is the actual write path for 6 of its 7 call sites, `record_harness_event()` (`:1227`) for the 7th. `_insert_harness_event()` (`session_store/writers.py:1109-1224`) has a fixed column list (:1166-1174) with no channel-provenance or side-effect-result columns. `HarnessEvent` (`history_reader/harness.py:54-109`) and `_HARNESS_EVENT_COLUMNS` (:110-118) are the read-side counterpart. `HarnessEventVariant` (`observability/schema.py:731-734`) is a third, independent enumeration of the row shape for the DES audit. Once ENH-3462 ships, `outcome.channels` and the side-effect check results exist for every run but are discarded when the process exits — never queryable via `ll-session recent/search --kind harness`, never available to `baseline_for()` (`history_reader/harness.py:325-404`) for cross-run comparison, and absent from `ll-doctor`'s schema-drift check.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- ENH-3462 has landed (status: Completed, confirmed 2026-09-14). `ChannelRecord` (`cli/harness.py:832`) and `HarnessEvalOutcome.channels: list[ChannelRecord]` (`cli/harness.py:882`) exist in the tree today and are fully wired: `_grade()` (`:1243`) composes the channel list every invocation (stdout/stderr at `:1297-1304`, side-effect channels at `:1305-1308`), and `_evaluate_and_report()` (`:2018`) is the sole current consumer, rendering `outcome.channels` into the `--output json` payload's `"channels"` key and the text `Channels:` block. This issue's `blocked_by: ENH-3462` is now satisfied — the persistence gap below is confirmed directly against landed code, not inferred from a not-yet-shipped dependency.
- Confirmed precisely: `outcome.channels` is never forwarded into any of the five `_record_harness_event()`/`_record()` call sites (`cmd_skill::_record` :2225, `cmd_cmd::_record` :2366, `cmd_mcp::_record` :2493, `cmd_prompt::_record` :2619, `cmd_dsl` :2793/:2890) — each extracts only `.verdict`/`.abstained`/`.passed` from `outcome`. `_record_harness_event()` itself has no `channels`/`side_effects` parameter in its signature.
- `_insert_harness_event()` (`session_store/writers.py:1109`) has a CLOSED keyword-only parameter list, not a `**kwargs` sink — `record_attempt()` forwards its `**event_fields` unvalidated (needs no code change for new kwargs), but `_insert_harness_event()` and `record_harness_event()` both require an explicit new named parameter for `channels_json`, or passing it today raises `TypeError: unexpected keyword argument`.
- `_row_to_dataclass()` (`history_reader/_base.py:87-91`) does zero NULL-coercion, but it maps only columns present in `row.keys()` — the columns actually named in the SQL SELECT that produced the row. A new `harness_events` column is invisible to `HarnessEvent` construction unless added to BOTH the dataclass fields (`history_reader/harness.py:54-109`) AND the `_HARNESS_EVENT_COLUMNS` string (`:110-118`, spliced into 5 separate SELECT statements at lines 135, 170, 195, 221, 349).

## Expected Behavior

`outcome.channels` — which already contains the side-effect check results as `ChannelRecord`s with `passed` set (see D1 below) — is persisted as a single JSON column `channels_json` on every graded `harness_events` row via a new `SCHEMA_VERSION` migration (v52), readable back through `HarnessEvent`, visible in `ll-session recent --kind harness` / `--json` and via `history_reader`, and validated by `ll-doctor`'s schema-drift check against `schema_manifest.json`. This issue does not change grading logic, baseline matching, or add new CLI flags — it only makes the evidence ENH-3462 already computes durable.

## Design

### Decisions

- **D1 — One column, not two.** Side effects are already `ChannelRecord`s: `_check_side_effects()` (`cli/harness.py:1187`) returns `list[ChannelRecord]` and `_grade()` extends `channels` with them (`:1306`). There is no separate side-effect result structure to serialize, so a `side_effects_json` column would duplicate a subset of `channels_json`. Persist `channels_json` only.
- **D2 — Persisted shape is `{name, examined, chars, note, passed}`; raw `content` is never persisted.** `ChannelRecord.to_dict()` (`:862`) deliberately omits `passed` ("internal fold state, not part of the D2 JSON shape") and `content`. Per-side-effect pass/fail requires `passed`, so add a second serializer `ChannelRecord.to_row_dict()` rather than widening `to_dict()`, which would change ENH-3462's public `--json` shape and its tests. Storing stdout/stderr bodies per repetition row would bloat `history.db` and create a secrets-at-rest surface that ENH-3470's credential scan does not cover — `chars` is the only trace of content.
- **D3 — `NULL` when there is no graded channel evidence; never `"[]"`.** Three write paths carry no channel evidence: the timeout/runner-error early returns in `_evaluate_and_report()` (`:2029-2038`, `channels=[]`), the DSL aggregate row (`:2770`, no outcome), and the DSL malformed-task row (`:2793`). The serializer helper returns `None` for an empty list, so `NULL` uniformly means "no graded channel evidence" for pre-v52 rows and ungraded rows alike.
- **D4 — Serializer lives in `cli/harness.py`, next to `ChannelRecord`.** `session_store/writers.py` takes an opaque `channels_json: str | None` and stays ignorant of the harness type, matching how `semantic_evidence` is handled.
- **D5 — Not FTS-indexed.** `_insert_harness_event()` indexes `summary[:512]` into `search_index`; channel data is not added to that summary. `ll-session search --fts --kind harness` therefore does not match on channel names/notes; the column is surfaced through `recent`, `--json`, and `HarnessEvent` only. Indexing can be a follow-up if a search use case appears.
- **D6 — `baseline_for()` matching is unchanged.** Channels are read-only evidence on the row; they do not enter the `(runner, target, input_hash, target_content_hash, conditions_fp)` match key.

### Observation for EPIC-3475 (out of scope here)

`_baseline_conditions()` (`cli/harness.py:~1630-1650`) does not fold `--evidence` / `--require-artifact` / `--forbid-path` / `--expect-no-git-changes` into `conditions_fp`, so a baseline and a candidate graded under different evidence declarations still share a fingerprint and match. Persisting `channels_json` makes such a mismatch visible after the fact (`examined` differs across matched rows) but does not prevent it. Worth a sibling issue under the epic.

## Motivation

Every downstream consumer of a harness verdict — candidate selection, regression detection, improvement loops — currently sees only the in-run report. Without persistence, a baseline comparison, a post-hoc audit, or `ll-session search` cannot distinguish "stderr was never examined" from "stderr was examined and empty" once the run is gone, reproducing ENH-3462's original blind spot one layer downstream.

## Proposed Solution

Follow the v49/v50 `_MIGRATIONS` precedent (`session_store/schema.py:1390-1415`, nullable `ALTER TABLE ADD COLUMN`, no `DEFAULT`, fix-forward only); no `CHECK` constraint is contemplated, so the v44 full-table-rebuild precedent (`session_store/schema.py:1178-1237`) does not apply. Thread the single new column `channels_json` (see Design → Decisions D1–D6) through `_insert_harness_event()`'s column list/parameter tuple, `record_harness_event()`/`record_attempt()` kwargs, `_record_harness_event()` in `cli/harness.py`, `HarnessEvent`'s trailing-default fields, and `_HARNESS_EVENT_COLUMNS`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — bump `SCHEMA_VERSION` (currently 51, after ENH-3464's same-day v51 efficiency-vector columns; this issue's migration lands as v52) and add the migration entry.
- `scripts/little_loops/session_store/writers.py` — `_insert_harness_event()` (:1109-1224) and `record_harness_event()` (:1227-1336).
- `scripts/little_loops/cli/harness.py` — `_record_harness_event()` (:216-306), the assembly point on the dominant `record_attempt()` write path, fed by 5 nested `_record()` call sites that currently extract only `.verdict`/`.abstained`/`.passed` from `outcome` (`cmd_skill::_record` :2225, `cmd_cmd::_record` :2366, `cmd_mcp::_record` :2493, `cmd_prompt::_record` :2619, `cmd_dsl` :2793/:2890; `record_harness_event()` used only at one of these).
- `scripts/little_loops/history_reader/harness.py` — `HarnessEvent` dataclass (:54-109) and `_HARNESS_EVENT_COLUMNS` (:110-118).
- `scripts/little_loops/session_store/schema_manifest.json` (`harness_events` entry, `:1089`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/doctor.py` — `_schema_manifest`/`_reference_manifest_at` (~:537-540), a second consumer of manifest correctness beyond the test gate.
- `scripts/little_loops/session_store/__init__.py` and `scripts/little_loops/history_reader/__init__.py` — package-level re-export points; no code change expected, confirm the public surface stays in sync.

### Similar Patterns
- `semantic_evidence: str | None` (`session_store/writers.py:1180`) — the closest precedent for `channels_json`: a free-text/JSON `harness_events` column that passes through with zero NULL-coercion code on either the write (`writers.py`) or read (`history_reader/_base.py:87-91`) side.
- v49/v50 plain `ALTER TABLE ADD COLUMN` (`session_store/schema.py`) — the applicable migration-mechanism precedent, since no `CHECK` constraint is contemplated on the new columns; the v44 full-table-rebuild pattern does not apply here.

### Tests
- `scripts/tests/test_session_store_schema.py` — `TestHarnessEventsTable`, `TestSchemaV49HarnessRunModel` (:1691), `TestSchemaV39HarnessContentPin` (:2182), `TestSchemaV50BaselineConditions` (:3331); the schema-manifest gate classes `test_schema_manifest_matches_checked_in_file` (:3152) and `test_manifest_schema_version_matches_live_schema_version` (:3169); a backfill test modeled on `test_v43_db_upgrades_preserving_existing_rows` (:2753-2787).
- `scripts/tests/test_cli_harness.py` — the CLI-integration layer where the v50 baseline-condition columns' write-path round-trip tests actually live (e.g. `:2958-2964`, asserting `row["conditions_fp"]`/`row["subject_model"]` after a CLI-level `measure` invocation); add the `channels_json` round-trip assertion here (AC6–AC8), following that precedent — not `test_session_store_writers.py::TestRecordAttemptAndAdmitRetry`, which tests retry-admission mechanics only and carries no free-text/JSON column round-tripping today.
- `scripts/tests/test_cli_doctor_install_checks.py::TestSchemaDrift` (:333-533) — extend alongside the schema-manifest gate.
- `scripts/tests/test_history_reader_harness.py` — read-side counterpart to `history_reader/harness.py`.
- `scripts/tests/test_ll_session.py` (`test_recent_kind_harness_outputs_row` / `test_search_kind_harness_matches_indexed_rows`, :1433/:1447) — `ll-session recent/search --kind harness` CLI-surface consumer.

### Documentation
- `docs/ARCHITECTURE.md` — schema-migration table (rows through v49/v50/v51 at :682/:683/:684); add the new v52 row.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — an independent copy of the same migration table (:57-99); already stale ("Current schema version: 45" at :57 vs. code's 51 — fix this drift while touching the table, not just adding a row).
- `docs/reference/EVENT-SCHEMA.md` § "CLI exit-code conventions" (:1795) — states *"Only `RunnerResult.timed_out` is persisted to `harness_events`; `RunnerResult.error` has no column."* — update once new fields are persisted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `_insert_harness_event()`'s INSERT column order (`writers.py:1166-1174`) is 34 columns (35 with the implicit `id` PK — matches `schema_manifest.json`'s `harness_events` entry, :1089-1303); the free-text `semantic_evidence: str | None` column — the closest existing precedent for `channels_json` — passes through with zero NULL-coercion code (`writers.py:1190`); only the 3 bool-typed kwargs (`semantic_passed`, `timed_out`, `dirty`) get explicit `None if x is None else int(x)` handling. The new JSON column needs no special-case coercion.
- `record_attempt()` (`writers.py:1398-1483`) forwards an unvalidated `**event_fields` dict straight through to `_insert_harness_event()` — confirmed directly. A new kwarg `_record_harness_event()` passes (e.g. `channels_json`) flows through `record_attempt()` with **no code change required inside `record_attempt()`'s own body**.
- Read side: `_row_to_dataclass()` (`history_reader/_base.py:87-91`) does a plain `row[k] for k in field_names if k in row.keys()` mapping; sqlite3's default adapter maps SQL `NULL` to Python `None` automatically for any column type. The `semantic_evidence` precedent carries no custom NULL-handling code on either the write or read side — the same zero-special-casing applies to the new columns.
- `ll-doctor`'s schema-drift check (`cli/doctor.py` ~:520-591) replays `_MIGRATIONS` to the DB's recorded version and diffs against the live PRAGMA schema — a new `_MIGRATIONS` entry alone is sufficient for drift detection to pick up the new columns; no separate registration step in `doctor.py` is needed. `schema_manifest.json`'s `"harness_events"` entry (:1089-1303, 35 column objects today, up from 29 at this issue's capture — ENH-3464's same-day v51 landed in between) still needs to be regenerated (one new column object; use the `TestSchemaManifest` docstring one-liner, not a hand edit), or `test_schema_manifest_matches_checked_in_file` (`test_session_store_schema.py:3152`) fails.
- **Superseded (verified 2026-09-14 by `/ll:verify-issues`)**: an earlier pass of this same research recorded "ENH-3462 has not landed" here. That was true when written but is no longer — ENH-3462 has since landed (status: Completed) and `ChannelRecord`/`HarnessEvalOutcome.channels` are confirmed present and wired in `cli/harness.py` (see the Current Behavior section's Codebase Research Findings, which supersedes this bullet). `blocked_by: []` in frontmatter is correct and current; do not re-add an ENH-3462 blocker.

## Program Design

### Types

- `HarnessEvalOutcome.channels: list[ChannelRecord]` — already added in-memory by ENH-3462 (`cli/harness.py`); this issue does not change its shape, only serializes it.
- `channels_json: str | None` — the single new `harness_events` column: a JSON array of `ChannelRecord.to_row_dict()` objects `{name, examined, chars, note, passed}` (D1/D2), `NULL` when the row has no graded channel evidence (D3). Mirrors the existing `semantic_evidence: str | None` free-text-JSON column precedent. Side-effect results are carried by the `passed` field of their channel entries — no second column.

### Signatures

- `ChannelRecord.to_row_dict(self) -> dict[str, Any]` (`cli/harness.py:842`) — persisted shape `{name, examined, chars, note, passed}`; `to_dict()` (the D2 `--json` shape) is unchanged.
- `_channels_json(channels: list[ChannelRecord]) -> str | None` (`cli/harness.py`, module-level next to `ChannelRecord`) — `json.dumps([c.to_row_dict() for c in channels])`, or `None` for an empty list (D3/D4).
- `_insert_harness_event(conn: sqlite3.Connection, *, ..., channels_json: str | None = None) -> int` (`session_store/writers.py:1109`)
- `record_harness_event(db_path: Path | str, *, ..., channels_json: str | None = None) -> int` (`session_store/writers.py:1227`)
- `_record_harness_event(*, ..., channels_json: str | None = None) -> int | None` (`cli/harness.py:216`)
- `HarnessEvent` (`history_reader/harness.py:54`) gains trailing-default field `channels_json: str | None = None`; `_HARNESS_EVENT_COLUMNS` (`:110`) appends the name.

### Call Path

`_grade` (`cli/harness.py:1243`, composes `outcome.channels`) → each `cmd_*::_record` closure (`:2225`, `:2366`, `:2493`, `:2619`, plus `cmd_dsl` `:2890`) adds `channels_json=_channels_json(outcome.channels)` → `_record_harness_event` (`cli/harness.py:216`) → `record_attempt` (`session_store/writers.py:1398`, the dominant 6-of-7 write path, `**event_fields` passthrough) → `_insert_harness_event` (`session_store/writers.py:1109`) → read back via `HarnessEvent` / `_HARNESS_EVENT_COLUMNS` (`history_reader/harness.py:54-118`). The DSL aggregate row (`record_harness_event` at `:2770`) and the DSL malformed-task row (`:2793`) pass nothing and land `NULL` (D3).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Migration-pattern precision: v49's `attempt_kind` column (`session_store/schema.py`) adds a `CHECK` constraint inline on a **new** column via `ALTER TABLE harness_events ADD COLUMN attempt_kind TEXT CHECK (...)` — SQLite permits a `CHECK` on a column added via `ADD COLUMN`; the v44 full-table-rebuild is only required to add a `CHECK` to an **already-existing** column. Since `channels_json` is plain nullable TEXT with no constraint contemplated, the v49/v50 plain-`ALTER TABLE`-per-column pattern applies outright — even a future `CHECK` on these new columns themselves would still not require the v44 rebuild pattern.
- `HarnessEventVariant` (`observability/schema.py:731-734`) and its base `DESVariant` (:21-30) carry no column-level fields for *any* existing `harness_events` column, including the v49/v50 columns already shipped — the class is a one-field (`type: Literal["harness_event"]`) audit-registry entry confirming a write call site is covered, not a per-column schema declaration. Adding `channels_json` does not require touching this file. See `⚠ Superseded` marker under Implementation Steps.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `SCHEMA_VERSION` (`session_store/schema.py:25`) is a hand-maintained int, independently asserted equal to `len(_MIGRATIONS)` by `test_schema_version_matches_migrations_length` (`test_session_store_schema.py:2345-2350`, guarding against the two silently desyncing per a prior BUG-3241 finding) — currently 51 (ENH-3464's same-day v51 landed after this issue's capture); must be bumped to **52** by hand alongside the new migration entry.
- `schema_manifest.json` is auto-generated, not hand-typed: `TestSchemaManifest`'s class docstring (`test_session_store_schema.py:3132-3147`) documents a `python -c "..."` one-liner that builds a fresh DB via `ensure_db()`, calls `_schema_manifest(conn)` (`schema.py:1625`), and writes the JSON — regenerate and commit via that script rather than hand-editing the checked-in file.
- Confirmed migration-pattern choice is correct: SQLite's `ALTER TABLE` cannot add a `CHECK` to an already-existing column (v44's full-table-rebuild for `verdict_events.verdict`/`abstention_reason` exists only for that reason), but a `CHECK` on a brand-new column uses plain `ALTER TABLE ADD COLUMN` with no rebuild (v49's `attempt_kind TEXT CHECK (...)`, `schema.py:1373-1374`, is the precedent). Since `channels_json` needs no `CHECK` at all, the plain v49/v50 `ALTER TABLE` pattern applies outright.
- Correction: the exact test class names cited in this issue's Integration Map/Tests sections do not match current code — `TestHarnessEventsRunModelColumns`, `TestHarnessEventsContentPinColumns`, and `TestHarnessEventsBaselineConditionColumns` do not exist. The actual classes are `TestSchemaV49HarnessRunModel` (`test_session_store_schema.py:1691`), `TestSchemaV39HarnessContentPin` (`:2182`), and `TestSchemaV50BaselineConditions` (`:3331`) — use these names when extending the fresh-DB/upgrade-DB/round-trip triad.
- `TestRecordAttemptAndAdmitRetry` (`test_session_store_writers.py:2492`) tests repetition-allocation and retry-admission mechanics only — it carries no free-text/JSON column round-tripping today. The v50 baseline-condition columns' actual write-path round-trip tests instead live in `test_cli_harness.py` at the CLI-integration layer (e.g. `:2958-2964`, asserting `row["conditions_fp"]`/`row["subject_model"]` after a CLI-level `measure` invocation) — a `channels_json` round-trip test belongs at that same CLI-integration layer, not inside `TestRecordAttemptAndAdmitRetry`.

## Implementation Steps

1. Add `channels_json: str | None` as a plain nullable `TEXT` column via the v49/v50 `ALTER TABLE ADD COLUMN` pattern (v52) — no `CHECK` constraint is needed, so the v44 full-table-rebuild path does not apply. Bump `SCHEMA_VERSION` to 52 by hand; regenerate `schema_manifest.json` via the `TestSchemaManifest` docstring one-liner.
2. Add `ChannelRecord.to_row_dict()` and the module-level `_channels_json()` helper in `cli/harness.py` (D2/D3/D4). Leave `to_dict()` untouched.
3. Thread `channels_json` through `_insert_harness_event()` → `record_harness_event()` (explicit new kwarg; `record_attempt()` needs no body change) → `_record_harness_event()` in `cli/harness.py`, and add `channels_json=_channels_json(outcome.channels)` to each of the five `_record` closures / the `cmd_dsl` graded-task call. No NULL-coercion handling is needed, mirroring `semantic_evidence`.
4. Add the trailing-default field to `HarnessEvent` and extend `_HARNESS_EVENT_COLUMNS`.
5. Update `docs/ARCHITECTURE.md` (v52 row), `docs/guides/HISTORY_SESSION_GUIDE.md` (v52 row **and** fix "Current schema version: 45" → 52), `docs/reference/EVENT-SCHEMA.md:1795` (note `channels_json` beside the ENH-3464 efficiency-field sentence).
6. Tests per Integration Map; full suite passes.

## Acceptance Criteria

- [ ] AC1 — `SCHEMA_VERSION == 52`, `len(_MIGRATIONS) == 52`, and the v52 entry is a single nullable `ALTER TABLE harness_events ADD COLUMN channels_json TEXT` with no `DEFAULT` and no `CHECK`.
- [ ] AC2 — A v51 DB with existing `harness_events` rows upgrades to v52 preserving every row, with `channels_json IS NULL` on all pre-existing rows (backfill test modeled on `test_v43_db_upgrades_preserving_existing_rows`).
- [ ] AC3 — `schema_manifest.json` is regenerated and `test_schema_manifest_matches_checked_in_file` / `test_manifest_schema_version_matches_live_schema_version` pass; `TestSchemaDrift` covers the new column.
- [ ] AC4 — `ChannelRecord.to_row_dict()` returns exactly `{name, examined, chars, note, passed}` and never includes `content`; `ChannelRecord.to_dict()` is byte-for-byte unchanged (existing ENH-3462 `--json` tests still pass unmodified).
- [ ] AC5 — `_channels_json([])` returns `None`; a non-empty list returns a JSON array whose elements round-trip through `json.loads` to the `to_row_dict()` shape.
- [ ] AC6 — CLI round-trip (in `test_cli_harness.py`, following the v50 `conditions_fp`/`subject_model` precedent): after a graded `cmd` run with `--require-artifact` on a present path and `--forbid-path` on a present path, the written row's `channels_json` decodes to entries for `stdout` (`examined=True`), `stderr` (`examined=False`, `chars=None` when `--evidence stderr` is not given), the artifact channel (`passed=True`), the forbidden-path channel (`passed=False`), and `git`.
- [ ] AC7 — A timed-out or runner-errored run, the DSL aggregate row, and the DSL malformed-task row all write `channels_json IS NULL` (D3).
- [ ] AC8 — Every `cmd_*` runner (`skill`, `cmd`, `mcp`, `prompt`, `dsl` per-task) writes a non-NULL `channels_json` on a graded run; no runner is missed (test parametrized over the five `_record` sites or asserted per runner).
- [ ] AC9 — `HarnessEvent.channels_json` is populated by `recent_harness_events()` / `baseline_for()` reads and is `None` for pre-v52 rows; `_HARNESS_EVENT_COLUMNS` includes it in all five SELECTs.
- [ ] AC10 — `ll-session recent --kind harness --json` output includes `channels_json`; `ll-session search --fts --kind harness` behavior is unchanged (D5 — not indexed; existing `test_search_kind_harness_matches_indexed_rows` passes unmodified).
- [ ] AC11 — `baseline_for()` match semantics are unchanged: a candidate row with a different `channels_json` but identical `(runner, target, input_hash, target_content_hash, conditions_fp)` still matches its baseline (D6).
- [ ] AC12 — `record_attempt()` body is unchanged; `record_harness_event()` and `_insert_harness_event()` each gain exactly one new kwarg; passing `channels_json` to either no longer raises `TypeError`.
- [ ] AC13 — Docs updated per step 5, including the HISTORY_SESSION_GUIDE "Current schema version" drift fix.
- [ ] AC14 — `python -m pytest scripts/tests/`, `ruff check scripts/`, and `python -m mypy scripts/little_loops/` all pass.

## Impact

- **Priority**: P3 — matches ENH-3462; internal-tooling durability follow-up, not a user-facing defect.
- **Effort**: Medium — one schema migration plus threading one kwarg through ~5 files and their read-side counterparts, following the v49/v50 migration precedent.
- **Risk**: Low — one additive, nullable column, fix-forward migration, plain `ALTER TABLE` (no `CHECK`, so no rebuild). The sharper edges are already decided: shape (D2, no raw content), NULL semantics (D3), and leaving `to_dict()`/the `--json` payload untouched.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: persisting `outcome.channels` (which already carries the side-effect check results as `passed` on each channel) to a single `harness_events.channels_json` column, plus the schema/manifest/doctor/docs surfaces that follow from a new column, and the `to_row_dict()`/`_channels_json()` serializer in `cli/harness.py`.
- **Out of scope**: persisting raw channel `content` (stdout/stderr bodies) — D2; FTS-indexing channel data for `ll-session search` — D5; changing `baseline_for()` matching or `_baseline_conditions()`/`conditions_fp` — D6 and the EPIC-3475 observation above.
- **Out of scope**: any change to grading logic, CLI flags, or the in-memory `ChannelRecord`/`HarnessEvalOutcome` shape — those are ENH-3462's scope, already shipped by the time this issue starts. This issue makes existing computed evidence durable; it does not compute new evidence.
- **Out of scope**: `FSMExecutor._evaluate()`'s identical single-channel gap (`fsm/executor.py`) — a separate issue, not persisted through `harness_events` at all.
- **Blocked by**: none — ENH-3462 has landed; `ChannelRecord`/`HarnessEvalOutcome.channels` exist and are fully wired in `cli/harness.py` today (confirmed 2026-09-14), so the evidence this issue persists is already available.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-14 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-14_

**Readiness Score**: 80/100 (recorded 2026-09-14, before ENH-3462 landed; frontmatter `confidence_score: 100` reflects the later 2026-09-15 re-run after the blocker cleared) → the sole blocker below is resolved; treat as clear to proceed
**Outcome Confidence**: 97/100 → HIGH CONFIDENCE

### Gaps to Address
- ~~`blocked_by: ENH-3462` is unresolved (status: open). `ChannelRecord`/`HarnessEvalOutcome.channels` do not exist in `scripts/` yet, so this issue cannot begin implementation until ENH-3462 ships.~~ **Resolved** (verified 2026-09-14 by `/ll:verify-issues`): ENH-3462 has since shipped (status: Completed); `ChannelRecord`/`HarnessEvalOutcome.channels` are confirmed present and wired in `cli/harness.py`. Frontmatter `blocked_by: []` is accurate. Criteria 1-4 all scored 20/20 and no other gap was identified — this issue is clear to proceed.


## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-14:_

Verdict at time of check: **OUTDATED** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item).

- **Graph**: provider=`codegraph` freshness=`fresh` (indexed_at
  2026-09-15T01:45:58Z, dirty_files=0) — `ll-code defines
  scripts/little_loops/cli/harness.py` corroborated relocations but every
  correction below was confirmed by direct `Read`/`grep` against the working
  tree, not the graph result alone.
- **Line-number drift found in `cli/harness.py`, despite the prior
  2026-09-15T01:51:08 verify pass's claim that "all citations in the sections
  above were re-verified"** — that pass evidently checked the writers.py/
  schema.py/test-class citations it enumerated but not these `cli/harness.py`
  anchors, which had already drifted at that time (the file's last touching
  commit, `80d2d38d0`, predates that verify session). Corrected in place:
  - `_grade()` def: cited `:1224` → actual `:1243` (Current Behavior findings
    bullet and Program Design → Call Path, both fixed).
  - stdout/stderr channel composition inside `_grade()`: cited `:1269-1276`
    → actual `:1297-1304`.
  - side-effect channel composition inside `_grade()`: cited `:1277-1280` →
    actual `:1305-1308`. (D1's separate citation of the `channels.extend(
    side_effects)` line, `:1306`, was already correct — no change.)
  - `_evaluate_and_report()` def: cited `:1948` → actual `:2018` (a 70-line
    drift — the largest found).
  - `_record_harness_event()` span: cited `:216-306` → actual `:216-309`
    (function body ends at the `except Exception: return None` block before
    the next top-level `@dataclass`).
  - `baseline_for()` (`history_reader/harness.py`): cited `:315-392` →
    actual `:325-404`.
  - `HarnessEvalOutcome.channels` field: cited `:872` → actual `:882`
    (Current Behavior findings bullet, fixed).
  - Checked and confirmed unchanged (no drift): `ChannelRecord` class
    (`:842`), `_check_side_effects()` (`:1187`), all five
    `cmd_*::_record`/`cmd_dsl` call sites (`:2225`,
    `:2366`, `:2493`, `:2619`, `:2770`, `:2793`, `:2890`), `_insert_harness_event()`
    (`writers.py:1109-1224`, actual end `1226` — 2-line rounding, not
    flagged), `record_harness_event()` (`writers.py:1227-1336`, exact),
    `record_attempt()` (`writers.py:1398-1483`, exact), `HarnessEvent`
    class (`history_reader/harness.py:54`, exact), `_HARNESS_EVENT_COLUMNS`
    block (`:110-118`, exact), and all five `_HARNESS_EVENT_COLUMNS` SELECT
    citations (`:135`, `:170`, `:195`, `:221`, `:349`, all exact).
- **Evidence check**: `ll-verify-evidence --json` returned `"ok": true`, 0
  findings — no fabricated evidence quotes.
- **Decisions log**: no active required rules — no conflict possible.
- **Dependencies**: `blocked_by: []`, `parent: EPIC-3475` (exists,
  `.issues/epics/P3-EPIC-3475-harden-ll-harness-verdicts.md`) — no broken
  refs, no missing backlinks, no cycle.
- **Proposal-vs-code consequence check (B6)**: re-checked against the
  corrected line numbers above; no exception-handler or test-fixture
  invalidation found. No `PROPOSAL_UNSOUND` finding.
- Design content, scope, decisions (D1-D6), Program Design types/signatures,
  and Acceptance Criteria were not affected by the line-number drift — they
  describe shapes and behavior, not anchors, and remain accurate.

- **Graph**: provider=`codegraph` freshness=`stale` (dirty_files=15) — not used to
  originate any verdict; every line-number/existence claim below was confirmed by
  direct `Read`/`grep` against the working tree, not the graph index.
- **Internal contradiction found and resolved**: the issue carried two
  "Codebase Research Findings" blocks that directly disagreed — one (Current
  Behavior) correctly stated ENH-3462 had landed, the other (Integration Map)
  stated it had not. Confirmed directly: ENH-3462 is `status: Completed`,
  `ChannelRecord`/`HarnessEvalOutcome.channels` exist and are fully wired in
  `cli/harness.py`. The stale bullet is now marked superseded in place rather
  than silently deleted.
- **Confidence Check Notes gap resolved**: the recorded "STOP — ADDRESS GAPS"
  verdict was keyed on the same now-resolved `blocked_by: ENH-3462` condition.
  Struck through and annotated; frontmatter `blocked_by: []` was already
  correct and needed no change.
- **Line-number drift corrected throughout** (Current Behavior, Integration Map,
  Program Design, Tests): caused by ENH-3464 landing the same day this issue was
  captured, which added 5 new columns/fields ahead of most of this issue's cited
  anchors in `cli/harness.py`, `session_store/writers.py`, and
  `history_reader/harness.py`. Notably `_insert_harness_event()`'s INSERT list is
  now 34 columns (35 with `id`), not 29, and `SCHEMA_VERSION` is now 51, not 50 —
  this issue's migration lands as **v52**. All citations in the sections above
  were re-verified against the current tree and updated; `docs/reference/EVENT-SCHEMA.md:1795`,
  `cli/doctor.py` (~:537-540), and the `test_session_store_schema.py` class names/lines
  (`TestSchemaV49HarnessRunModel` :1691, `TestSchemaV39HarnessContentPin` :2182,
  `TestSchemaV50BaselineConditions` :3331, `test_schema_manifest_matches_checked_in_file`
  :3152, `test_manifest_schema_version_matches_live_schema_version` :3169,
  `test_v43_db_upgrades_preserving_existing_rows` :2753,
  `test_schema_version_matches_migrations_length` :2345,
  `TestRecordAttemptAndAdmitRetry` :2492) were checked and are unchanged. The
  v44 (`schema.py:1178-1237`) and v50 (`:1390-1415`) migration-block citations
  and the v49 `attempt_kind` CHECK (`:1373-1374`) were also checked and are
  unchanged — they predate the v51 insertion point in the file, so only
  citations for code *after* it drifted. `_schema_manifest()` moved from
  `:1612` to `:1625` (fixed).
- **Evidence check**: `ll-verify-evidence --json` returned `"ok": true`, 0
  findings — no fabricated evidence quotes.
- **Decisions log**: no active required rules (`ll-issues decisions list
  --type rule --enforcement required --active-only` returned empty); no
  conflict possible.
- **Dependencies**: `blocked_by: []`, `parent: EPIC-3475` (exists,
  `.issues/epics/P3-EPIC-3475-harden-ll-harness-verdicts.md`) — no broken refs,
  no missing backlinks, no cycle.
- **Proposal-vs-code consequence check (B6)**: no exception-handler or
  test-fixture invalidation found; the proposed nullable `ALTER TABLE ADD
  COLUMN` change threads through code paths (`record_attempt`'s `**event_fields`
  passthrough, `_row_to_dataclass`'s NULL-tolerant mapping) that already handle
  an added free-text column with zero special-casing, mirroring
  `semantic_evidence`. No `PROPOSAL_UNSOUND` finding.

## Session Log
- `/ll:verify-issues` - 2026-09-15T04:00:27 - `0f83c176-40fa-4a35-a08d-d5149dc5394e.jsonl`
- `/ll:confidence-check` - 2026-09-15T03:47:32 - `88716449-4fa1-4681-9160-79d70fab2d25.jsonl`
- `/ll:verify-issues` - 2026-09-15T01:51:08 - `d4c1049e-2c84-4263-aafc-1dbf7f3be2c3.jsonl`
- `/ll:reconcile-issue` - 2026-09-14T21:32:26 - `f4a1cb05-beaf-4c89-a67b-0a34555443d6.jsonl`
- `/ll:refine-issue` - 2026-09-14T21:18:34 - `b80e42ca-40bb-4d8a-b6d8-3b9dab6f1bf1.jsonl`
- `/ll:confidence-check` - 2026-09-14T18:58:05 - `cef18a0e-5855-4ab1-ba23-37a7d36518ff.jsonl`
- `/ll:reconcile-issue` - 2026-09-14T18:55:40 - `6c2e05b8-05cf-4d8d-b2b6-1b2ad05e6c8f.jsonl`
- `/ll:refine-issue` - 2026-09-14T18:53:00 - `20027762-fa98-4cf8-8ef8-31f8f3facf83.jsonl`
- `/ll:format-issue` - 2026-09-14T18:46:16 - `6d894000-c098-410e-9d4d-4df5e3c75319.jsonl`
