---
id: ENH-2741
title: harness_events read API, ll-session CLI wiring, and docs
type: ENH
priority: P3
status: open
discovered_date: 2026-07-22
discovered_by: issue-size-review
parent: ENH-2493
blocked_by:
- ENH-2739
labels:
- enhancement
- history-db
- eval
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
  import snippet. `docs/reference/CLI.md` — append `,harness` to both
  `--kind` choice tables (`search` and `recent`) and add a `--kind harness`
  example snippet.

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
- Docs updated: `docs/reference/API.md` import snippets,
  `docs/reference/CLI.md` `--kind` tables + example.

## Explicitly Out of Scope

- `harness_events` schema/migration, kind registration, `record_harness_event()`
  — ENH-2739.
- `main_harness()` / `cmd_*` producer wiring, the `_evaluate_and_report()`
  signature refactor, DSL per-task rows — ENH-2740.

## Session Log
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `5a7a2fd0-cba1-488a-89c7-36283dba4691.jsonl`
