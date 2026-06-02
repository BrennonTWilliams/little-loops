---
id: ENH-1621
type: ENH
priority: P4
status: done
discovered_date: 2026-05-22
completed_at: 2026-05-22T23:55:33Z
discovered_by: manage-issue
relates_to:
- FEAT-1112
labels:
- enhancement
- carved-out
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1621: Migrate analyze-* skills to query the session DB

## Summary

Route `ll-history` (`main_history()`) and `ll-workflows` (`analyze_workflows()`)
to read from the unified session store (`.ll/session.db`, FEAT-1112) instead of
re-parsing scattered JSON/markdown source files on every invocation.

## Motivation

This is **Step 6 / Acceptance Criterion 3 of FEAT-1112**, carved out during
implementation (2026-05-22). FEAT-1112 shipped the session store, the
`SQLiteTransport` sink, the `ll-session` query CLI, and the `backfill()`
routine — but the two skill migrations were deferred because the schema as
specified does not carry enough fields to reconstruct what the two entry points
consume:

- `main_history()` → `scan_completed_issues()` returns rich `IssueInfo`
  objects (completed_date, type, priority, score_* fields, body excerpts).
  `issue_events` stores only (issue_id, transition, discovered_by, ts).
- `analyze_workflows()` consumes user **message text** + a pattern YAML;
  `tool_events` stores tool names/hashes, not message bodies.

Migrating without first widening the schema would mean rewriting the analysis
logic on SQL rows — a regression risk for two working CLIs.

## Current Behavior

- `ll-history` (`main_history()`) scans completed-issue files on every run via
  `scan_completed_issues()`, rebuilding rich `IssueInfo` objects from disk each
  invocation.
- `ll-workflows` (`analyze_workflows()`) re-parses extracted user messages and a
  pattern YAML on every invocation.
- The unified session store (`.ll/session.db`, FEAT-1112) exists but neither
  entry point reads from it.

## Expected Behavior

- Decide per target: widen the schema (new migration) to carry the needed
  columns, or store a JSON/body blob the query path can rehydrate.
- `main_history()` and `analyze_workflows()` query the DB when populated,
  falling back to source-file parsing when the DB is empty/absent (no
  regression for un-backfilled projects).
- `ll-session backfill` (or session-start ingestion) keeps the DB current.

## Proposed Solution

_Added by `/ll:refine-issue` — based on codebase analysis:_

The two targets need different schema work, so handle them independently within
one schema v2 migration.

**`main_history()` — widen `issue_events`.** `scan_completed_issues()`
(`scripts/little_loops/issue_history/parsing.py:289`) returns `CompletedIssue`
dataclasses whose fields are `path, issue_type, priority, issue_id,
discovered_by, discovered_date, completed_date, captured_at, completed_at`
(`scripts/little_loops/issue_history/models.py:16`). Note: the issue Motivation
above refers to `IssueInfo` with `score_*` fields and body excerpts — the actual
`CompletedIssue` model carries none of those. Score/hotspot data is computed by
`calculate_analysis()` from git + file contents at run time, and body excerpts
are loaded separately by `_load_issue_contents()` only in the `export` path.
This makes the `summary` subcommand fully DB-serviceable: add columns
`issue_type`, `priority`, `completed_date`, `captured_at`, `completed_at` to
`issue_events` (currently only `ts, issue_id, transition, discovered_by` —
`session_store.py:94`). The `analyze` and `export` subcommands still need file
bodies and git history, so they remain on the file-parsing path; only `summary`
swaps to the DB. Scope the DB-backed migration to `summary` accordingly.

**`analyze_workflows()` — add a `message_events` table.** It consumes user
**message text** from a JSONL file (`_load_messages()`,
`scripts/little_loops/workflow_sequence/io.py:13`) plus a Step-1 pattern YAML.
No existing table stores message bodies (`tool_events` holds tool names/hashes;
`user_corrections.content` is for correction text only). Add a
`message_events(id, ts, session_id, content)` table in the v2 migration and a
`_backfill_messages()` routine that reads user blocks from session JSONLs (the
same files `_backfill_tool_events()` already iterates). The pattern YAML stays a
file input — it is a generated analysis artifact, not session state.

A JSON-blob alternative (store a serialized row blob the query path rehydrates)
was considered but rejected: typed columns are needed so `summary` can filter by
`completed_date`/`issue_type` in SQL, and the column count is small and bounded.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — append a schema v2 entry to
  `_MIGRATIONS` (`session_store.py:72`) adding the new `issue_events` columns and
  the `message_events` table; bump `SCHEMA_VERSION = 1` → `2`
  (`session_store.py:38`); update `_backfill_issues()` (`session_store.py:345`)
  to populate the new columns; add `_backfill_messages()` and call it from
  `backfill()` (`session_store.py:458`); add `message` to `_VALID_KINDS` /
  `_KIND_TABLE` (`session_store.py:40-47`) so `recent(kind="message")` works.
- `scripts/little_loops/cli/history.py` — in `main_history()` the `summary`
  branch (`history.py:200-210`) gains a DB-backed path: query `issue_events`,
  fall back to `scan_completed_issues()` when the query returns 0 rows.
- `scripts/little_loops/issue_history/parsing.py` — add a DB-reader helper
  alongside `scan_completed_issues()` that rebuilds `CompletedIssue` rows from
  `issue_events`.
- `scripts/little_loops/workflow_sequence/analysis.py` — `analyze_workflows()`
  reads messages via `_load_messages()`; add a DB-source branch (query
  `message_events`) with fallback to the JSONL file.
- `scripts/little_loops/workflow_sequence/io.py` — add a `_load_messages_from_db()`
  helper mirroring `_load_messages()` (`io.py:13`).

### Dependent / Reference Files
- `scripts/little_loops/cli/session.py` — `ll-session backfill`
  (`session.py:113`) calls `backfill()`; once `_backfill_messages()` is added it
  will report a `messages=` count — update the success line (`session.py:116`).
- `scripts/little_loops/hooks/session_start.py` — bootstraps the DB; confirm it
  still calls `ensure_db()` (migrations apply automatically on connect).
- `scripts/little_loops/transport.py` — `SQLiteTransport` / `wire_transports()`
  are unaffected (v2 migration is additive).

### Similar Patterns
- Schema migration: the single existing `_MIGRATIONS[0]` entry
  (`session_store.py:72-125`) and `_apply_migrations()` (`session_store.py:142`)
  — append a new SQL string; `ALTER TABLE issue_events ADD COLUMN ...` plus
  `CREATE TABLE message_events ...`.
- Backfill routine: `_backfill_tool_events()` (`session_store.py:411`) already
  iterates session JSONLs and parses message blocks — `_backfill_messages()`
  follows the same shape but reads `type == "user"` records.
- Empty-DB fallback: `recent()` (`session_store.py:230`) returns `[]` on an
  empty table — a zero-length result is the fallback trigger; `connect()` always
  creates the file, so "DB absent" reduces to "DB empty".

### Tests
- `scripts/tests/test_session_store.py` — add v2 migration + `_backfill_messages`
  coverage (model: existing migration/backfill tests).
- `scripts/tests/test_issue_history_cli.py` — add DB-backed vs fallback cases for
  `ll-history summary`.
- `scripts/tests/test_workflow_sequence_analyzer.py` — add DB-backed vs fallback
  cases for `analyze_workflows()`.
- `scripts/tests/test_ll_session.py` — extend `backfill` assertions for the new
  `messages` count.

### Documentation
- `docs/reference/CLI.md` — `ll-history` (lines ~978) and `ll-workflows`
  (lines ~1036) sections: note the DB-backed source + fallback behavior.
- `docs/reference/API.md` — `little_loops.session_store` and
  `little_loops.issue_history` sections: document the schema v2 columns.

## Implementation Steps

1. Add the schema v2 migration: append a SQL string to `_MIGRATIONS` in
   `session_store.py` with `ALTER TABLE issue_events ADD COLUMN` for
   `issue_type`, `priority`, `completed_date`, `captured_at`, `completed_at`,
   plus `CREATE TABLE message_events(...)`; bump `SCHEMA_VERSION` to `2`.
2. Update `_backfill_issues()` to write the new `issue_events` columns from
   frontmatter; add `_backfill_messages()` modeled on `_backfill_tool_events()`
   and wire it into `backfill()` and the `counts` dict.
3. Register `message` in `_VALID_KINDS` / `_KIND_TABLE` and update
   `ll-session backfill`'s success message in `cli/session.py`.
4. Add a `CompletedIssue`-from-DB reader in `issue_history/parsing.py`; in
   `main_history()`'s `summary` branch, query it and fall back to
   `scan_completed_issues()` on an empty result.
5. Add `_load_messages_from_db()` in `workflow_sequence/io.py`; in
   `analyze_workflows()`, prefer the DB source and fall back to `_load_messages()`.
6. Add DB-backed + fallback tests in `test_session_store.py`,
   `test_issue_history_cli.py`, `test_workflow_sequence_analyzer.py`, and
   `test_ll_session.py`.
7. Run `python -m pytest scripts/tests/test_session_store.py
   scripts/tests/test_issue_history_cli.py
   scripts/tests/test_workflow_sequence_analyzer.py scripts/tests/test_ll_session.py -v`.

## Acceptance Criteria

- Both entry points query `.ll/session.db` when it is populated.
- Behavior is unchanged for projects with no/empty DB (fallback path).
- A schema migration (version 2+) is added if new columns are required.
- Tests cover the DB-backed path and the fallback path for both CLIs.

## Scope Boundaries

- Only `main_history()` and `analyze_workflows()` are migrated; other `ll-*`
  CLIs that do not analyze history/workflows are out of scope.
- Schema changes are limited to columns the two entry points require — no
  speculative widening for future consumers.
- The source-file parsing path is retained as a fallback, not removed.

## Impact

- **Priority**: P4 — completes FEAT-1112's analyze-migration criterion.
- **Effort**: Medium — schema extension + two CLI data-source swaps + tests.
- **Risk**: Medium — touches two shipped CLIs; fallback path mitigates.
- **Breaking Change**: No

## References

- Parent: FEAT-1112 (Unified Session Store) — see its plan at
  `thoughts/shared/plans/2026-05-22-FEAT-1112-management.md` (§Scope decision).

## Status

**Done** | Created: 2026-05-22 | Completed: 2026-05-22 | Priority: P4

## Resolution

Schema v2 migration adds widened `issue_events` columns (`issue_type`,
`priority`, `completed_date`, `captured_at`, `completed_at`) and a new
`message_events` table; bumped `SCHEMA_VERSION` to `2`.

`_backfill_issues()` now populates the v2 columns from issue frontmatter, with
filename-based fallbacks for `issue_type` / `priority` when frontmatter is
absent. New `_backfill_messages()` mirrors `_backfill_tool_events()` but reads
`type=="user"` records and supports both plain-string and block-list message
content. `backfill()` returns a new `messages` count and `ll-session backfill`
reports it. `recent(kind="message")` is wired through `_VALID_KINDS` and the
`ll-session recent --kind message` CLI option.

`ll-history summary` now prefers `scan_completed_issues_from_db()` (new
DB-backed reader in `issue_history/parsing.py`) and transparently falls back
to `scan_completed_issues()` on an empty/absent DB. The `analyze` and `export`
subcommands continue to read files because they need bodies and git history.

`analyze_workflows()` gained an optional `db_path` parameter; when provided
and the DB has rows it loads via `_load_messages_from_db()` (new helper in
`workflow_sequence/io.py`), otherwise falls back to the JSONL path.

Tests cover both DB-backed and fallback paths plus the v1→v2 schema upgrade.
Full pytest run: 7327 pass (1 pre-existing unrelated CLAUDE.md skill-count
failure, no regressions). Ruff + mypy clean on touched files.


## Session Log
- `/ll:manage-issue` - 2026-05-22T23:55:33 - implement (Closes ENH-1621)
- `/ll:ready-issue` - 2026-05-22T23:40:54 - `2d98bd8d-bc02-44ca-9aa5-a004a05cb375.jsonl`
- `/ll:ready-issue` - 2026-05-22T22:57:56 - `faa9dab7-6876-4951-b2f8-9267c4b0e418.jsonl`
- `/ll:confidence-check` - 2026-05-22T22:30:00 - `98972a97-ec58-4e0e-ae5f-61ff1633250e.jsonl`
- `/ll:refine-issue` - 2026-05-22T22:18:20 - `3766e10f-e0ce-4f0a-afd6-a5771f735963.jsonl`
- `/ll:refine-issue` - 2026-05-22T22:13:08 - `da2cdb66-57d9-4b9e-ad13-a2228c32b4d3.jsonl`
- `/ll:format-issue` - 2026-05-22T22:06:12 - `01b1eb09-75fc-443b-88ad-6641283eca0a.jsonl`
