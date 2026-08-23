---
id: FEAT-3300
title: Advisor consult telemetry - schema, writer, reader
type: FEAT
parent: EPIC-3041
priority: P4
status: open
testable: true
discovered_date: 2026-08-23
depends_on:
- FEAT-3044
labels:
- planning-hub
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
relates_to:
- FEAT-3040
---

# FEAT-3300: Advisor consult telemetry - schema, writer, reader

> **Recovery note (2026-08-23):** originally drafted as FEAT-3117/FEAT-3118 in the epic-3041 sub-loop worktree (abandoned ref b972a9c7c), whose stale .issues tree allocated IDs colliding with the existing wire-trigger issues FEAT-3117/FEAT-3118 on main. Renumbered to FEAT-3300/FEAT-3301 on recovery.


## Summary

Persistence half of FEAT-3040 (Slice 4 of the host-agnostic advisor,
FEAT-3037): add the `advisor_consults` table to `.ll/history.db`, a fail-soft
writer, and a typed reader/query layer. This is the standalone,
independently-testable core — it does not require `ll-ctx-stats` reporting
(FEAT-3301) to be useful, matching the existing precedent of
`harness_events`/`verdict_events`/`review_events`, all of which shipped with a
reader and no report section.

## Parent Issue

Decomposed from FEAT-3040: Advisor consult telemetry in history.db.

## Current Behavior

- Consults leave no durable trace. `.ll/history.db` already records
  `loop_events`, `issue_events`, `cli_events`, `usage_events`,
  `orchestration_runs`, and more via `session_store/schema.py` +
  `writers.py`, and `history_reader.py` is the typed read surface — but
  nothing records escalation decisions.

## Expected Behavior

- Each consult writes one `advisor_consults` row: timestamp, session, task
  key, signal, advisor host + model, main model, capability-floor status,
  latency, token usage where the host reports it, verdict confidence, and
  whether it was skipped (budget/floor/failure) rather than issued.
- `history_reader.py` gains `query_advisor_consults` (filters by `since`) and
  `consult_stats` (aggregates counts/tokens by signal).
- The verdict *body* is not stored by default (it can quote private code);
  storage is opt-in, consistent with how other private content is handled.
- A DB write failure logs and is dropped — never on the caller's critical
  path.

## Proposed Solution

1. `CREATE TABLE IF NOT EXISTS advisor_consults` — append a new DDL entry to
   `_MIGRATIONS` in `session_store/schema.py` (the append *is* the version
   bump, `SCHEMA_VERSION` 38 -> 39; the top-of-file constant is
   documentation-only). Register the table in `VALID_KINDS` (`:23-47`) and
   `_KIND_TABLE` (`:49-73`); exclude it from `_REBUILD_TABLES`/
   `_REBUILD_SEARCH_KINDS` (it's live-write-only, no JSONL source — document
   the exclusion per the `hook_events` comment pattern at `:668-673`).
2. `write_advisor_consult` in `session_store/writers.py`. Resolve the writer
   signature against sibling convention before implementing: every existing
   `record_*` writer takes `db_path: Path | str` and self-manages its own
   connection — the parent issue's originally-stated
   `(conn: sqlite3.Connection, row: AdvisorConsultRow) -> None` shape doesn't
   match that. Pick a fail-soft idiom: either (a) writer raises and the
   caller wraps in `contextlib.suppress(Exception)` (`record_verdict_event`
   pattern), or (b) writer itself catches `sqlite3.Error`, logs via
   `logger.warning(..., exc_info=True)`, and returns falsy
   (`record_context_pressure_event` pattern, `writers.py:1692-1750`) — no
   shared decorator enforces either, so document the choice in the PR.
3. `query_advisor_consults(db_path, *, since=None)` and
   `consult_stats(db_path, *, days=30)` in `history_reader.py`, following the
   `_row_to_dataclass` + `_<NAME>_COLUMNS` convention (e.g.
   `_VERDICT_EVENT_COLUMNS` at `:2980-2983`).
4. Verdict-body opt-in (AC 6): design and land the config surface. No
   existing precedent gates a single column while writing the rest of the
   row — every current `analytics.capture.*` toggle is whole-row/whole-table.
   Add a new `AdvisorConfig` field (`config/orchestration.py:107-137`, flat
   dataclass with an explicit `from_dict` mapping — add both the field and
   the `data.get(...)` line) plus a matching property in the `advisor` block
   of `config-schema.json` (`:1647-1684`, `additionalProperties: false`, so a
   new key must be declared or validation rejects it).

## Program Design

### Types

- `AdvisorConsultRow: {id: int, ts: str, session_id: str, task_key: str, signal: str, advisor_host: str, advisor_model: str, main_model: str, floor_status: str, outcome: Literal["issued", "skipped_budget", "skipped_floor", "failed", "timeout"], latency_ms: int | None, input_tokens: int | None, output_tokens: int | None, confidence: float | None}`
- `ConsultStats: {by_signal: dict[str, int], total: int, total_tokens: int, skipped: int}`

### Signatures

- `write_advisor_consult(db_path: Path | str, row: AdvisorConsultRow) -> bool` (or `None`, per the fail-soft idiom chosen in step 2 above — resolve, don't inherit the parent issue's stated `conn`-based signature verbatim)
- `query_advisor_consults(db_path: Path, *, since: str | None = None) -> list[AdvisorConsultRow]`
- `consult_stats(db_path: Path, *, days: int = 30) -> ConsultStats`

### Call Path

Future (post FEAT-3044): `little_loops.advisor.consult` -> `write_advisor_consult` -> `.ll/history.db`

This issue's actual, testable-now call path: test code -> `write_advisor_consult`
-> `.ll/history.db`, following the same fail-soft insert shape as the existing
`record_context_pressure_event` (`writers.py:1692-1753`) — `conn = None` before
`try`, `except sqlite3.Error: logger.warning(..., exc_info=True); return False`,
`finally: conn.close()`.

**Note**: `little_loops.advisor.consult()` is prospective — FEAT-3044 hasn't
landed `advisor.py` yet. Wiring the actual call site (and the FEAT-3116
budget/floor skip-recording call site) is explicitly **out of scope for this
issue** and deferred until FEAT-3044/FEAT-3116 land; this issue delivers a
standalone, directly-testable table/writer/reader that those issues call into
once they exist. AC1 below is scoped accordingly: exercised via direct writer
calls in tests, not end-to-end through a live `consult()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- `AdvisorConfig` (`config/orchestration.py:106-137`): fields at `:120-125`
  (`enabled: bool = False`, `host: str | None = None`, `model: str = "opus"`,
  `min_tier: str | None = None`, `timeout_seconds: int = 180`,
  `triggers: list[str] = field(default_factory=list)`), `from_dict` at
  `:127-137` with one `data.get(key, default)` line per field. A verdict-body
  opt-in slots in as a 7th scalar field + matching `data.get(...)` line — no
  nested-dataclass or enum wiring needed.
- Fail-soft idiom resolved: `record_context_pressure_event`
  (`writers.py:1692-1753`) and every other writer in the file (confirmed at
  `record_session_lifecycle_event`, `writers.py:1643-1689`, and
  `record_verdict_event`) use the **catch-and-return-falsy** idiom
  uniformly — `conn = None` before `try`, `except sqlite3.Error:
  logger.warning(..., exc_info=True); return False`, `finally: conn.close()
  if conn`, `return True` on success. This is the file-wide convention, not
  a per-writer choice — `write_advisor_consult` should follow it rather than
  raise-and-suppress.
- `config-schema.json` `advisor` block (`:1647-1684`) has `additionalProperties:
  false` (confirmed present at `:1683`) mirroring `AdvisorConfig`'s 6 fields
  1:1. A new opt-in property must be declared under `"properties"` (insert
  before the `}` closing `"properties"`, after the `triggers` entry) or
  config validation rejects it.
- `history_reader.py` reader pattern (verified against `_row_to_dataclass`,
  `:437-441`, reused by every reader incl. `recent_verdict_events`,
  `:2963-3022`): connection via `_connect_readonly`, `sqlite3.Error` caught
  with `logger.warning(..., exc_info=True)` + empty-list return, `finally:
  conn.close()`, rows mapped via `_row_to_dataclass(row, DataclassType)`.
  Naming correction: the existing verdict-events reader is
  `recent_verdict_events` (`:2986`), not `query_verdict_events` as the
  naming might suggest by analogy — and there is no `verdict_stats`/`_stats`
  function anywhere in the file for any kind. `consult_stats` therefore has
  no direct reader-side sibling precedent to copy; only the table/writer/
  `recent_*`-query precedent applies. Aggregation logic (counts/tokens by
  signal) will need to be authored from the SQL/dataclass conventions above,
  not adapted from an existing `*_stats` function.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/session_store/__init__.py` — add
  `write_advisor_consult` to the `writers.py` import block and to `__all__`.
- Update `scripts/little_loops/session_store/queries.py` — add an
  `"advisor_consult_event": ("advisor_consults", "ts")` entry to
  `_EXPORT_TABLE_MAP` and `"advisor_consult_event"` to
  `_EXPORT_DEFAULT_TABLES`, following the `verdict_event`/
  `context_pressure_event`/`review_event` precedent.
- Update `scripts/little_loops/config/core.py` — add the new opt-in field to
  `BRConfig.to_dict()`'s hand-enumerated `"advisor"` dict (`:808-814`), or it
  silently never appears in `to_dict()` output or `resolve_variable("advisor.*")`.
- Update `scripts/tests/test_session_store_writers.py` (`:470-471,1153,1455,1653`)
  and `scripts/tests/test_assistant_messages.py` (`:88`) — bump the 5
  additional hardcoded `SCHEMA_VERSION == 38` (and one `int(row[0]) == 38`)
  literals to 39, alongside the 16 already flagged in
  `test_session_store_schema.py`.
- Add `test_recent_kind_advisor_consult_accepted`-style test to
  `scripts/tests/test_ll_session.py`.
- Add an `advisor_consult_event` export-participation test to
  `scripts/tests/test_session_store_queries.py`, tied to the
  `_EXPORT_TABLE_MAP` update above.
- Add field-level schema/dataclass parity assertions for the new opt-in field
  to `scripts/tests/test_config_schema.py` and
  `scripts/tests/test_config.py` (`TestAdvisorConfig`,
  `test_to_dict_advisor`), tied to the `config/core.py` `to_dict()` update
  above.

## Acceptance Criteria

1. `write_advisor_consult` produces exactly one `advisor_consults` row per
   call, including an `outcome` value distinguishing issued from
   budget/floor/failure skips. (Exercised directly in tests — wiring the real
   `consult()` call site is FEAT-3044/FEAT-3116's job, not this issue's.)
2. The table is created on a fresh DB and added cleanly to a pre-existing DB
   without data loss.
3. A DB write failure logs and is dropped — it does not raise into the
   caller.
4. `query_advisor_consults` filters by `since`; `consult_stats` aggregates
   counts and token totals by signal.
5. The verdict body is absent from the DB unless the opt-in is set.
6. No automatic pruning or compaction of these rows is added; deletion
   remains a manually-run CLI action (no code required — verify none exists).
7. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/schema.py` — `advisor_consults`
  migration, `VALID_KINDS`/`_KIND_TABLE` registration, rebuild exclusion.
- `scripts/little_loops/session_store/writers.py` — `write_advisor_consult`.
- `scripts/little_loops/history_reader.py` — `query_advisor_consults`,
  `consult_stats`.
- `scripts/little_loops/config/orchestration.py` — `AdvisorConfig`
  verdict-body opt-in field.
- `scripts/little_loops/config-schema.json` — matching `advisor.*` property.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/__init__.py:104-149,151-239` —
  re-exports every `writers.py` writer individually, both in the
  `from little_loops.session_store.writers import (...)` block (e.g.
  `write_file_event` at `:148`) and in `__all__` (e.g. `"write_file_event"`
  at `:190`). `write_advisor_consult` must be added to both or it stays
  unimportable via `little_loops.session_store`. No test catches an
  omission here — `test_session_store_schema.py:1975`
  (`TestPackageReexportSurface.test_all_and_required_private_names_resolve`)
  only checks that names *already in* `__all__` resolve, not that every
  `writers.py` function is present in `__all__`.
- `scripts/little_loops/session_store/queries.py:89-109,111-129` —
  `_EXPORT_TABLE_MAP` and `_EXPORT_DEFAULT_TABLES`, consumed by
  `export_history()`. All three of the issue's own cited sibling patterns
  (`verdict_event`, `context_pressure_event`, `review_event`) are present in
  *both* dicts (`:106-108`, `:126-128`). A matching `"advisor_consult_event":
  ("advisor_consults", "ts")`-shaped entry belongs in both, following that
  precedent exactly — this file was absent from the issue's file list.
- `scripts/little_loops/config/core.py:808-814` — `BRConfig.to_dict()`
  hand-enumerates the `advisor` block field-by-field (`"enabled":
  self._advisor.enabled, ...`) rather than via `dataclasses.asdict()`. The
  new opt-in field must get a matching 7th line here or it silently never
  appears in `to_dict()["advisor"]` — and since `resolve_variable()`
  (`config/core.py:979-999`) walks `to_dict()` by dotted path, the field
  would also be unreachable via `resolve_variable("advisor.<field>")` even
  though `AdvisorConfig.from_dict` parses it correctly.

### Dependent Files (Callers/Importers)

- FEAT-3301 (`ll-ctx-stats` reporting) calls `consult_stats` /
  `query_advisor_consults` once this issue lands — sequenced after this
  issue, not blocking it.
- FEAT-3038's budget counter — consider deriving the per-task count from this
  table once it exists, collapsing two counters into one source of truth
  (not required by this issue's ACs).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/lifecycle.py:35-52,898-910` — imports
  `writers.py` helpers and separately owns `_REBUILD_TABLES`/
  `_REBUILD_SEARCH_KINDS`. Confirms (does not contradict) the issue's own
  research: `advisor_consults` is correctly excluded by omission from both
  tuples — no edit needed here, only the DDL-comment in `schema.py`.
- `scripts/little_loops/cli/session.py:47,108,120` — `VALID_KINDS` import
  feeds `choices=list(VALID_KINDS)` for `ll-session search --kind` /
  `ll-session recent --kind`. No code edit needed (choices derive
  automatically once `schema.py`'s `VALID_KINDS` gains `"advisor_consult"`),
  noted here only because it's the CLI surface that starts accepting
  `--kind advisor_consult` as a side effect of the schema.py change.
- No central re-export point exists for `history_reader.py` functions
  analogous to `session_store/__init__.py`'s writer re-export — confirmed by
  grep: every consumer (`cli/session.py`, `cli/history.py`,
  `cli/history_context.py`, `cli/ctx_stats.py`, `cli/logs.py`,
  `user_messages.py`, `issue_history/*.py`) imports directly `from
  little_loops.history_reader import <name>`. `query_advisor_consults`/
  `consult_stats` need no registration beyond being defined in
  `history_reader.py` itself.

### Similar Patterns

- `verdict_events` (schema v33, `schema.py:758-775`; writer
  `record_verdict_event` `writers.py:1126-1181`; reader
  `history_reader.py:2963-3022`)
- `review_events` (v35, `schema.py:805-822`; `record_review_event`
  `writers.py:1184-1242`; `history_reader.py:3083-3142`)
- `context_pressure_events` (v34, `schema.py:783-797`;
  `record_context_pressure_event` `writers.py:1692-1750`)

All three ship with a reader and no `ll-ctx-stats` section — the closest
in-tree precedent for this issue's scope boundary with FEAT-3301.

### Tests

- `scripts/tests/test_session_store_schema.py` — new
  `TestSchemaV39AdvisorConsults` class following `TestSchemaV33VerdictEvents`
  (`:1708`) / `TestSchemaV34ContextPressureEvents` (`:1776`):
  `test_advisor_consults_columns`, `test_advisor_consults_indexes_exist`,
  `test_v38_db_upgrade_gains_advisor_consults`, `test_kind_registration`,
  `test_excluded_from_rebuild`, `test_not_kindless`. Bump `SCHEMA_VERSION`
  38 -> 39 and all 16 `assert SCHEMA_VERSION == 38` literals in this file
  (lines 650, 664, 716, 812, 1034, 1075, 1413, 1453, 1497, 1547, 1619, 1679,
  1747, 1812, 1880, 1925) — mechanical but file-wide.
- `scripts/tests/test_session_store_writers.py` — new
  `TestRecordAdvisorConsult` class. If idiom (b) is chosen, follow
  `TestRecordContextPressureEvent.test_graceful_when_store_unwritable`
  (`:2467-2478`) for the falsy-return contract.
- `scripts/tests/test_history_reader.py` (not `test_session_store_queries.py`
  — that file only covers `export_history()` kind participation) — new tests
  for `query_advisor_consults`/`consult_stats`, following the
  aggregation-by-key shape of `test_recent_verdict_events_and_pass_rate`
  (`:1921-1960`).
- `scripts/tests/test_verify_kinds.py` — existing gate that fails if
  `advisor_consults` isn't correctly registered in
  `_KIND_TABLE`/`VALID_KINDS` (or `_KINDLESS_TABLES` if intentionally
  excluded).
- A new test asserting the verdict body column is absent unless the opt-in
  config flag is set — no existing pattern to copy (searched, no hits);
  author from scratch alongside the config field.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_writers.py:470-471,1153,1455,1653` — 4
  more hardcoded `assert SCHEMA_VERSION == 38` literals (plus a non-symbolic
  `assert int(row[0]) == 38` at `:471`) outside the 16 already flagged in
  `test_session_store_schema.py`; bump all to 39 alongside those.
- `scripts/tests/test_assistant_messages.py:88` — one more `assert
  SCHEMA_VERSION == 38` literal (`test_schema_version_is_12`, a stale test
  name from an older schema era) to bump to 39.
- `scripts/tests/test_ll_session.py` — existing per-`VALID_KINDS`-entry
  acceptance-test pattern (`test_recent_kind_learning_test_accepted:340`,
  `test_recent_kind_subagent_run_accepted:361`,
  `test_recent_subcommand_orchestration_run_accepted:166`): new
  `test_recent_kind_advisor_consult_accepted`-style test needed for
  `ll-session recent --kind advisor_consult`, none exists yet.
- `scripts/tests/test_session_store_queries.py:149-164` — existing
  `_EXPORT_TABLE_MAP` participation-test pattern
  (`test_context_pressure_event_participates_in_export_history`-style, using
  `record_context_pressure_event` + `export_history(db,
  tables=["context_pressure_event"])`); a matching
  `advisor_consult_event`-participation test is needed, tied to the
  `queries.py` `_EXPORT_TABLE_MAP`/`_EXPORT_DEFAULT_TABLES` finding above.
- `scripts/tests/test_config_schema.py` — no test walks `config-schema.json`
  `advisor.properties` keys against `dataclasses.fields(AdvisorConfig)` (the
  `test_fsm_schema.py:258,272` pattern used for `EvaluateConfig` has no
  `AdvisorConfig` analogue); `test_advisor_host_enum_matches_orchestration_host_cli`
  (`:825`) is scoped only to the `host` enum. Add an explicit assertion for
  the new field's declared type/default — nothing generic catches an
  addition here.
- `scripts/tests/test_config.py:3592-3654` (`TestAdvisorConfig`) and
  `:1051-1094` (`test_to_dict_advisor`/`test_to_dict_advisor_defaults_when_unset`)
  — hand-assert each `AdvisorConfig` field individually; need a new case for
  the opt-in field, tied to the `config/core.py:808-814` `to_dict()`
  omission risk above.

### Documentation

- `docs/reference/API.md` — new reader functions
  (`query_advisor_consults`, `consult_stats`), following the
  `OrchestrationRun`/`recent_orchestration_runs` entry at `:7909`.
- `docs/reference/API.md:152` — config-reference table's `advisor` row, note
  on the new opt-in field.
- `docs/reference/CONFIGURATION.md:1274-1289` — `### advisor` config section,
  new table row for the verdict-body opt-in.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:661-701` — the `history.db` schema-version table
  (one markdown row per version, currently ending `| v38 |
  orchestration_runs.base_sha/base_dirty | ... |` at `:701`) needs a new
  `| v39 | advisor_consults | ... |` row.
- `docs/reference/API.md:8562,8566` — a second, distinct schema-version site
  from the reader-fn/config-table edits already planned: "Current schema
  version: **38**" prose (`:8562`) and an inline `SCHEMA_VERSION, # 38` code
  comment inside a sample import block (`:8566`) that also lists every
  public writer by name — bump the version and add `write_advisor_consult`
  to that listed set.
- `docs/reference/CLI.md:3212,3220,3287` — literal `VALID_KINDS`
  choice-set enumerations in `--kind`/`--tables` flag descriptions for
  `ll-session search`/`recent`/`export`. Already stale (missing `review`,
  pre-existing drift unrelated to this issue) — optional to fix here, noted
  so `advisor_consult` doesn't compound the existing drift if touched.
- `docs/guides/HISTORY_SESSION_GUIDE.md:56-91,99-124` — a second
  independently-maintained schema-version table and a "What Gets Recorded"
  per-table description list, both already several versions behind current
  `SCHEMA_VERSION`. Same pre-existing-drift caveat as CLI.md — optional.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- `VALID_KINDS` tuple: `schema.py:23-47`, `"context_pressure"` entry at
  `:45` (sibling to `"verdict"` `:44`, `"review"` `:46`) — `"advisor_consult"`
  slots in alongside these.
- `_KIND_TABLE` dict: `schema.py:49-73`, `"context_pressure":
  "context_pressure_events"` entry at `:71` (sibling to `"verdict":
  "verdict_events"` `:70`, `"review": "review_events"` `:72`).
- `_REBUILD_TABLES`/`_REBUILD_SEARCH_KINDS` are defined in
  `session_store/lifecycle.py:898-910`, not `schema.py` — the exclusion
  itself is enforced by *omission* from those two tuples in `lifecycle.py`,
  not by an entry in `schema.py`. What lives in `schema.py` is a doc-only
  comment at each excluded table's DDL block explaining why (the pattern the
  issue cites at `:668-673` for `hook_events`, and the same shape repeated
  at `:776-782` for `context_pressure_events`: "Live-write-only ... excluded
  from _REBUILD_TABLES/_REBUILD_SEARCH_KINDS like
  hook_events/harness_events/prompt_opt_events"). `advisor_consults`'
  migration DDL should carry the same comment shape; no edit to
  `lifecycle.py`'s tuples is needed or correct.
- `SCHEMA_VERSION = 38` confirmed at `schema.py:21`; `_MIGRATIONS` list
  (`:107`) currently closes at `:935` after the v38 `orchestration_runs`
  ALTER — the new `advisor_consults` CREATE TABLE entry appends there to
  become v39.

## Impact

- **Priority**: P4 — pure observability. Nothing depends on it, but it makes
  the advisor's cost/benefit answerable rather than assumed.
- **Effort**: Small — the table/writer/reader pattern is well-established;
  the only judgment call is the privacy posture on verdict bodies and the
  writer signature.
- **Risk**: Low — additive schema, fail-soft writes, off the critical path.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/reference/API.md#little_loopshistory_reader`

## Status

**Open** | Created: 2026-08-23 | Priority: P4


## Session Log
- `/ll:confidence-check` - 2026-08-23T18:13:52 - `e0525866-2b9f-414b-a9af-4d4eaed8dd5c.jsonl`
- `/ll:verify-issues` - 2026-08-23T18:12:26 - `8d2ef6d7-3cb8-4361-a1f1-13b1e34ddf40.jsonl`
- `/ll:refine-issue` - 2026-08-23T18:07:46 - `566c27e8-dca1-40cd-b847-431a80e3f740.jsonl`
- `/ll:verify-issues` - 2026-08-23T18:06:34 - `e39740a0-6efa-4ef9-b607-8cd5352abef4.jsonl`
- `/ll:wire-issue` - 2026-08-23T18:00:57 - `61d3969e-65c1-4562-933d-0cb7369a728a.jsonl`
- `/ll:refine-issue` - 2026-08-23T17:52:18 - `24d2b5af-f646-4f4b-80bd-7a71c9c7a092.jsonl`
- `/ll:issue-size-review` - 2026-08-23T17:46:16 - `797c9631-7573-4a96-864e-cad371610ef8.jsonl`
