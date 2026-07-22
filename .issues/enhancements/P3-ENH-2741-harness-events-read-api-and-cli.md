---
id: ENH-2741
title: harness_events read API, ll-session CLI wiring, and docs
type: ENH
priority: P3
status: done
discovered_date: 2026-07-22
completed_at: '2026-07-22T21:33:08Z'
discovered_by: issue-size-review
parent: EPIC-2457
blocked_by:
- ENH-2739
labels:
- enhancement
- history-db
- eval
relates_to:
- ENH-2493
confidence_score: 100
outcome_confidence: 87
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 22
---

# ENH-2741: harness_events read API, ll-session CLI wiring, and docs

## Summary

Child 3 of 3 decomposed from ENH-2493 ("Persist ll-harness / eval outcomes
into history.db"). This child adds the read side: `history_reader` query
functions, the `ll-session recent/search --kind harness` CLI surface, and the
remaining docs. Depends on ENH-2739 for the schema to exist; round-trip tests
can use direct-INSERT fixtures so this child does not strictly need ENH-2740
merged first, but full manual verification (`ll-harness run ... && ll-session
recent --kind harness`) requires ENH-2740's producer to be wired.

## Parent Issue

Decomposed from ENH-2493. See ENH-2493 for full motivation and codebase
research trail — re-verify every line-number anchor against live `main`
before implementing; the parent issue documents repeated anchor drift across
several refine passes.

## Scope

- **`HarnessEvent` dataclass** in `history_reader.py`, mirroring `RunEvent`'s
  field shape.
- **`recent_harness_events(runner=None, target=None, since=None, limit=50,
  db=DEFAULT_DB_PATH)`** — model after `recent_test_runs()` (parameterized
  `WHERE`, `ORDER BY ts DESC, id DESC LIMIT ?`, `_connect_readonly` swallow
  pattern; returns `[]` on missing DB).
- **`harness_eval_pass_rate(target, since=None, db=DEFAULT_DB_PATH)`** — note
  the name: ENH-2493's "Scope Boundary" notes flag that the originally
  proposed name `harness_pass_rate` collides with
  `ab_writer.py:ABResults.harness_pass_rate` (a distinct float-fraction
  concept from the A/B comparator, consumed by `cli/loop/_helpers.py`). Use
  `harness_eval_pass_rate` to remove the ambiguity at the source rather than
  relying on import-path disambiguation. Model the rollup logic after
  `summarize_skills()`'s `SUM(CASE WHEN ... THEN 1 ELSE 0 END) / COUNT(...)`
  pattern, ignoring NULL `semantic_passed` rows; return `None` when there are
  zero semantic-scored rows (division-by-zero guard).
- **CLI**: `ll-session recent --kind harness` and `ll-session search --fts
  "<target>" --kind harness` should work automatically once `VALID_KINDS`
  (landed by ENH-2739) includes `"harness"` — both `cli/session.py`
  subparsers derive `choices=list(VALID_KINDS)` from the single source of
  truth, so no duplicate `choices=[...]` edit is needed. Update the
  `cli/session.py` module docstring's kind-list prose (rendered in
  `--help`) to mention `"harness"`.
- **Docs**: `docs/reference/API.md` — append `HarnessEvent`,
  `recent_harness_events`, `harness_eval_pass_rate` to the `history_reader`
  import snippet (each tagged `# ENH-2741`), plus per-symbol `###` prose
  sections. **`docs/reference/CLI.md` is already updated** (landed with
  ENH-2739) — both `--kind` choice tables, the `export --tables` list, and
  an example already include `harness`; no CLI.md edit is needed for this
  child. See Codebase Research Findings below for exact line references.

## Acceptance Criteria

- `recent_harness_events()` filters by `runner`, `target`, `since`
  independently and combined; returns `[]` on missing/unreadable DB.
- `harness_eval_pass_rate(target, since)` returns `None` when all matching
  rows have `semantic_passed IS NULL`; otherwise returns the correct
  fraction.
- `ll-session recent --kind harness` returns rows (using fixture data
  inserted directly via `record_harness_event()` from ENH-2739, or real rows
  if ENH-2740 has landed).
- `ll-session search --fts "<target>" --kind harness` matches indexed rows.
- Docs updated: `docs/reference/API.md` import snippet + per-symbol prose
  sections. (`docs/reference/CLI.md` already carries the `--kind` tables +
  example from ENH-2739 — no change needed there.)

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis of `main` (2026-07-22, post ENH-2739 merge):_

### `harness_events` schema (already landed, session_store.py:955-977)

```
id INTEGER PRIMARY KEY AUTOINCREMENT
ts TEXT NOT NULL
runner TEXT
target TEXT
exit_code INTEGER
semantic_verdict TEXT
semantic_passed INTEGER   -- nullable tri-state 0/1/NULL, NOT a bool
timed_out INTEGER         -- nullable tri-state 0/1/NULL
duration_ms INTEGER
head_sha TEXT
branch TEXT
parent_id INTEGER         -- links DSL per-task rows to parent run (ENH-2740)
semantic_prompt TEXT
semantic_confidence REAL
semantic_reason TEXT
semantic_evidence TEXT
semantic_model TEXT
```
Indexes: `idx_harness_runner`, `idx_harness_target`, `idx_harness_exit`, `idx_harness_parent`.
`record_harness_event()` (session_store.py:1826-1892) writes `semantic_passed`/`timed_out` as `None if x is None else int(x)` — `HarnessEvent` fields for these should type as `int | None`, matching `_row_to_dataclass()`'s no-coercion, direct row-to-field copy (history_reader.py:384-388).

### Model functions to copy the shape of

- **Dataclass**: `RunEvent` (history_reader.py:163-181) — plain field list mirroring table column order + one-line docstring citing the issue. `LifecycleEvent` (history_reader.py:240-253) is a second example of the same convention.
- **Query fn**: `recent_test_runs()` (history_reader.py:1350-1386, full body) — `_connect_readonly()` → `None` returns `[]`; explicit column SELECT; `clauses: list[str]`/`params: list[Any]` accumulation, `WHERE " AND ".join(clauses)` only if non-empty; always `ORDER BY ts DESC, id DESC LIMIT ?`; `try/except sqlite3.Error: logger.warning(...); return []` / `finally: conn.close()`; return `[_row_to_dataclass(row, RunEvent) for row in rows]`. `recent_lifecycle_events()` (history_reader.py:1134-1175) is the closest 3-filter analog to the requested `runner`/`target`/`since` signature.
- **Rollup fn**: `summarize_skills()` (history_reader.py:608-657, full body) — `SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes` + `COUNT(success) AS completions` (COUNT ignores NULL rows); Python-side guard `(successes / completions) if completions else None` — no SQL-side division. For `harness_eval_pass_rate(target, since)`, decide whether "pass" means `exit_code = 0` or `semantic_passed = 1` (schema carries both an exit-code path and a `check_semantic` verdict path) — issue AC implies the semantic-verdict rollup (`semantic_passed IS NULL` → `None`), so substitute `semantic_passed` for `success` in the CASE/COUNT.

### Test patterns to model after

- `test_recent_test_runs_and_pass_rate` (test_history_reader.py:1606-1629) — writes fixture rows via the module's own recorder (`record_test_run_event`), then asserts on `recent_test_runs()` output. Direct analog: use `record_harness_event()` (session_store.py:1826-1879; kwargs: `db_path, *, ts, runner=None, target=None, exit_code=None, semantic_verdict=None, semantic_passed=None, timed_out=None, duration_ms=None, head_sha=None, branch=None, parent_id=None, semantic_prompt=None, semantic_confidence=None, semantic_reason=None, semantic_evidence=None, semantic_model=None`) as the fixture writer.
- `test_recent_kind_hook_event_outputs_row` (test_ll_session.py:1187-1205) — writes one row via the session_store recorder, invokes `main_session()` under `patch("sys.argv", [...])` with `recent --kind <kind>`, asserts exit 0 + a distinguishing substring in captured stdout. **Confirmed no existing `test_recent_kind_harness_...` or `test_search_kind_harness_...` test in `test_ll_session.py`** (grep returned zero hits) — this is genuinely new test surface, not already covered.

### Scope correction: `docs/reference/CLI.md` is already updated

The issue's Scope section says `docs/reference/CLI.md` needs `,harness` appended to both `--kind` choice tables plus an example. **This is already landed** (confirmed on `main`, likely part of the ENH-2739 commit `564a1205`):
- `--kind {...,hook_event,harness}` appears in both the `search` (CLI.md:2485) and `recent` (CLI.md:2493) tables.
- `--tables` for `export` already includes `harness_event` (CLI.md:2560).
- An example `ll-session recent --kind harness  # Recent ll-harness / eval outcomes (ENH-2739)` already exists (CLI.md:2577).
- `cli/session.py`'s module docstring `recent` kind list already includes `harness` (session.py:11).

**Remaining doc gap is API.md only**: `docs/reference/API.md`'s `little_loops.history_reader` import snippet (API.md:6939-6973) has zero hits for `HarnessEvent`/`recent_harness_events`/`harness_eval_pass_rate` (confirmed via grep) — append these three as new lines in the existing `from little_loops.history_reader import (...)` block, each tagged `# ENH-2741` per the file's established per-symbol-comment convention, plus new `###`-level prose sections modeled after `### summarize_skills` (API.md:7186-7196) and `### recent_test_runs` (API.md:7287-7299).

### Scope correction: `cli/session.py` docstring already mentions "harness"

_Wiring pass added by `/ll:wire-issue`:_ The Scope section's CLI bullet says
to "Update the `cli/session.py` module docstring's kind-list prose to mention
`'harness'`." **This is already done** — confirmed live on `main`
(`scripts/little_loops/cli/session.py:9-11`, module docstring): `recent   most
recent rows for an event kind (tool, file, issue, loop, correction, message,
skill, cli, snapshot, commit, test_run, usage, orchestration_run, hook_event,
harness)`. No edit needed anywhere in `cli/session.py` for this child —
`VALID_KINDS`-derived `choices=` wiring and the docstring prose are both
already correct. Confirmed via direct grep: zero remaining doc/code
references to "harness" are missing from this file.

### Tests

_Wiring pass added by `/ll:wire-issue`:_ Beyond the `history_reader.py`
round-trip test already called out under "Test patterns to model after",
`--kind harness` has **zero CLI-layer test coverage today** despite already
being fully wired (confirmed via grep — no `harness` hits anywhere in
`scripts/tests/test_ll_session.py`). Add:
- `scripts/tests/test_history_reader.py` — a `TestHarnessEventReaders`-style
  class (model after `TestHookEvents`/`test_recent_orchestration_runs_filters`
  at `test_history_reader.py:1677-1710` for the filter-combination shape, and
  `test_hook_failure_rate`/`test_hook_failure_rate_none_when_no_fires` at
  `test_history_reader.py:1975-1998` for `harness_eval_pass_rate`'s
  none-when-no-rows edge case) covering `recent_harness_events()` (recency
  order; `runner`/`target`/`since` filters independently and combined) and
  `harness_eval_pass_rate()` (mixed pass/fail fraction; `None` when all
  `semantic_passed IS NULL`).
- `scripts/tests/test_ll_session.py` — `TestArgumentParsing`:
  `test_recent_subcommand_harness_accepted` and
  `test_search_subcommand_harness_accepted` (model after
  `test_recent_subcommand_hook_event_accepted` /
  `test_search_subcommand_hook_event_accepted` at
  `test_ll_session.py:108-120`) asserting `--kind harness` is an accepted
  argparse choice for both subcommands — this is currently untested even
  though `VALID_KINDS` already includes it.
- `scripts/tests/test_ll_session.py` — `TestMainSession`:
  `test_recent_kind_harness_outputs_row` (model after
  `test_recent_kind_hook_event_outputs_row` at
  `test_ll_session.py:1187-1205`) — write a fixture row via
  `record_harness_event()`, invoke `main_session()` with
  `recent --kind harness`, assert exit 0 + a distinguishing substring in
  stdout. Add an analogous `search --fts ... --kind harness` case for the
  FTS acceptance criterion.

### Unrelated naming-collision confirmed

`ABResults.harness_pass_rate` (ab_writer.py:131-153, computed at line 194 as `harness_passes / n`) is a plain in-memory dataclass field aggregating one A/B comparison run's per-item pass fraction — entirely unrelated to SQLite/`session_store`/`history_reader`. Confirms the issue's naming rationale for `harness_eval_pass_rate` is sound (same-name-different-module collision, not a refactor target).

### No FTS5 indexing work needed

`record_harness_event()` (session_store.py:1882-1889) already calls the shared `_index()` helper with `kind="harness"` inside the same transaction as the row insert — harness rows are already searchable via `ll-session search --fts` today. No `search_index`-side change is required for the `search --fts ... --kind harness` acceptance criterion; it should already pass against fixture data.

## Explicitly Out of Scope

- `harness_events` schema/migration, kind registration, `record_harness_event()`
  — ENH-2739.
- `main_harness()` / `cmd_*` producer wiring, the `_evaluate_and_report()`
  signature refactor, DSL per-task rows — ENH-2740.

## Session Log
- `/ll:manage-issue` - 2026-07-22T21:32:48Z - `f008fe60-53f8-4a66-8f9c-338af4e1468e.jsonl`
- `/ll:ready-issue` - 2026-07-22T21:23:17 - `690f36cc-8893-4faf-9370-b61644d39d35.jsonl`
- `/ll:confidence-check` - 2026-07-22T21:21:00 - `e5ba1809-836e-4c60-ad3b-521c641ace00.jsonl`
- `/ll:wire-issue` - 2026-07-22T21:18:40 - `b432019a-2a60-4895-a3ed-d13adff248b7.jsonl`
- `/ll:refine-issue` - 2026-07-22T21:11:35 - `7d7777ca-d56b-4a23-a58e-da9efac22cbb.jsonl`
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `5a7a2fd0-cba1-488a-89c7-36283dba4691.jsonl`
