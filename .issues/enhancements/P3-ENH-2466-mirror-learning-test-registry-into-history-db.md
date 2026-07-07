---
id: ENH-2466
title: Mirror Learning Test Registry records into history.db / search_index
type: ENH
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
decision_needed: true
labels:
  - enhancement
  - history-db
  - learning-tests
  - captured
---

# ENH-2466: Mirror Learning Test Registry records into history.db / search_index

## Summary

The Learning Test Registry (`.ll/learning-tests/*.md`, owned by `ll-learning-tests`, exposed via `/ll:explore-api` and `ll-learning-tests prove`) lives entirely as markdown files outside the DB. There's no entry in `skill_events`, `loop_events`, `message_events`, or any other table that says "this registry record was created at timestamp T by session S, asserting behavior X for module M." `ll-session search` cannot find them — they're invisible to FTS and to all read APIs. Add a `learning_test_events` table mirroring each record's `id, target, status, assertions, captured_at, last_proved_at` and index into `search_index` so registry content is discoverable alongside everything else. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #9: *"mirror registry records into a `learning_test_events` table (or at least index them into `search_index`) so they're discoverable via `ll-session search` alongside everything else."*

## Motivation

Currently the registry is a useful but isolated knowledge base:

- **No cross-correlation with sessions/issues** — "what was proved about module X during session Y?" is unanswerable.
- **No FTS discoverability** — `ll-session search --fts "<API behavior>"` returns nothing for the registry.
- **No regen or staleness signal in the DB** — `STALE` flagged records are not surfaced to history-aware consumers like `ll-history-context`.
- **Active rules** about an API (e.g., "the `usage` block in `on_usage_detailed` returns these fields") are dead text outside the agent context layer that EPIC-1707 wired up.

EPIC-1707's consumer success metric depends on agents querying the DB; the registry is a missed first-class candidate.

## Current Behavior

- `.ll/learning-tests/<id>.md` files hold each record with frontmatter `id`, `target`, `status`, `captured_at`, `last_proved_at` and body `## Assertions` etc.
- `ll-learning-tests list/show/mark-stale/orphans/check` operate over the filesystem.
- `ll-session search --fts` excludes registry content (no DB rows).
- `ll-history-context` does not surface registry records.

## Expected Behavior

- `learning_test_events` table exists with columns: `id`, `ts`, `record_id TEXT UNIQUE`, `target`, `status`, `assertions_json TEXT`, `captured_at`, `last_proved_at`.
- A mirror writer (in `ll-learning-tests` or hook-side) writes a row on each `prove` invocation, on staleness flagging, and on registry creation/edit (filesystem-watch or mtime sweep).
- A `_backfill_learning_test_events()` populates rows from existing `.ll/learning-tests/*.md` files (idempotent via `record_id UNIQUE`).
- Records index into `search_index` via the established `_index()` helper with `kind="learning_test"`; FTS search discovers them.
- `ll-session search --fts "<API name or assertion>" --kind learning_test` returns matching records.
- `history_reader.find_learning_tests(target=None, status=None)` returns `list[LearningTestRecord]`.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS learning_test_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    record_id TEXT NOT NULL UNIQUE,        -- matches .ll/learning-tests/<id>.md stem
    target TEXT,                           -- API/function being tested
    status TEXT,                           -- proven | stale | orphaned | pending
    assertions_json TEXT,                  -- JSON array of assertion strings
    captured_at TEXT,
    last_proved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_learning_tests_target ON learning_test_events(target);
CREATE INDEX IF NOT EXISTS idx_learning_tests_status ON learning_test_events(status);
```

Bump `SCHEMA_VERSION`. Add `"learning_test"` to `_VALID_KINDS` and `"learning_test": "learning_test_events"` to `_KIND_TABLE`.

### Producer wiring

- **Approach A (per-CLI event)**: `ll-learning-tests prove` invokes a new `record_learning_test_event(...)` after each prove.
- **Approach B (filesystem watch)**: A periodic background scan walks `.ll/learning-tests/*.md` and reconciles (similar to `_backfill_*` family). Use mtime + content-hash dedupe.
- **Approach C (event-bus emit)**: Add an `EventBus.emit({"kind": "learning_test", ...})` call to `ll-learning-tests` writes; subscribe a small transport that writes to the table.

Recommend **B + C combined**: filesystem reconcile for cold-start, event-bus emit for live updates. Both best-effort (`contextlib.suppress(Exception)`).

### FTS5 indexing

Call the existing `_index(conn, content=<target + assertions>, kind="learning_test", ref=<record_id>, anchor=<target>, ts=<ts>)` helper per insert — consistent with `issue_snapshots` approach per ENH-2151.

### Read API

Add to `history_reader.py`:
- `find_learning_tests(target=None, status=None, since=None)` — list of records.
- `find_learning_test_by_record_id(record_id)` — single record.

### CLI surface

- `ll-session search --fts "<query>" --kind learning_test` — FTS discoverability.
- `ll-session recent --kind learning_test` — list recent records.
- `ll-learning-tests list --db` — opt-in flag to consult DB rather than filesystem (faster, eventually-consistent).

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store.py` — primary target.
  - Module-level: append v19 SQL block to `_MIGRATIONS` list (currently ends with v18 / `test_run_events` at lines 524–544) and bump `SCHEMA_VERSION` from `18` to `19` (line 102).
  - Add `"learning_test"` to `_VALID_KINDS` (frozenset at line 104) and `"learning_test": "learning_test_events"` to `_KIND_TABLE` (dict at line 130).
  - Add new top-level functions: `record_learning_test_event(db, target, file_path, config=None)` and `_backfill_learning_test_events(conn, registry_dir) -> int`.
  - Register `record_learning_test_event` in `__all__` (currently 28 entries).
  - Extend `backfill()` (line 2441) `counts` dict with `"learning_tests": 0` and dispatch under a `if registry_dir and registry_dir.is_dir()` guard.

- `scripts/little_loops/history_reader.py` — add reader surface.
  - Define new `@dataclass LearningTestEvent` next to other dataclasses (lines 67–189); mirror columns `ts, record_id, target, status, assertions_json, captured_at, last_proved_at`.
  - Add `recent_learning_tests(*, status=None, limit=20, db=DEFAULT_DB_PATH) -> list[LearningTestEvent]` (mirror `recent_commit_events` at line 524).
  - Add `find_learning_test(target, *, db=DEFAULT_DB_PATH) -> LearningTestEvent | None`.
  - Add `"learning_test"` and the two new function names to the `Public API:` docstring block (lines 1–42).

- `scripts/little_loops/cli/learning_tests.py` — producer wiring.
  - In `cmd_prove()` (line 48): after `check_learning_test(args.target)` returns a record, call `record_learning_test_event(DEFAULT_DB_PATH, args.target, str(_slug_path(slug, base)))` wrapped in `try/except: pass` (per `set_status.py:60-66` precedent).
  - In `cmd_mark_stale()` (line 84): after `mark_stale(slugify(args.target))`, re-call `record_learning_test_event(...)` (the record now reflects `status="stale"`).
  - In `cmd_orphans()` (line 96): when `--mark-stale` is passed, mirror the same write.
  - `main_learning_tests()` already wraps everything in `cli_event_context` (line 145); the new writes sit alongside that context, not inside it.

- `scripts/little_loops/cli/session.py` — `--kind` literal extension.
  - `search_parser` `add_argument("--kind", choices=[...])` literal list at lines 92–103 — append `"learning_test"`.
  - `recent_parser` `add_argument("--kind", choices=[...])` literal list at lines 113–127 — append `"learning_test"`.

- `scripts/tests/test_session_store.py` — new test classes.
  - Add `TestSchemaV19LearningTestEvents` (mirror `TestSchemaV14` at line 2872): pin `SCHEMA_VERSION == 19`, table presence, dedup index presence, v18→v19 migration using `_bootstrap_schema_at()` (line 3075).
  - Add `TestRecordLearningTestEvent` (mirror `TestRecordIssueSnapshot` at line 2942): roundtrip, fts-indexed, idempotent, missing-file-is-noop.
  - Add `TestBackfillLearningTests` (mirror `TestBackfillSnapshots` at line 3015): hydrates-table, idempotent, stores-body.
  - Update `TestEnsureDb.test_all_tables_created` table tuple (line 60) to include `"learning_test_events"`.
  - Update the legacy `assert SCHEMA_VERSION == 18` assertion in `TestSchemaV14.test_schema_version_is_fourteen` (and any other `SCHEMA_VERSION == 18` literals) to `19`.

- `scripts/tests/test_history_reader.py` — add reader tests (mirror `test_recent_commit_events_*` patterns).

- `scripts/tests/test_cli_learning_tests.py` — confirm `cmd_prove` / `cmd_mark_stale` tests still pass with the new write calls; the calls are best-effort and may be no-op in fixture DBs.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/history.py` (`ll-history`) — could surface learning tests as an `--issue` / `--kind` filter.
- `scripts/little_loops/cli/history_context.py` (`ll-history-context`) — consumers that read `search_index` benefit from new `kind="learning_test"` rows automatically (no code change required there).
- `scripts/little_loops/hooks/session_start.py` (line 122) — the existing `ensure_db()` call already creates the new table on session start; no change needed but verifies the migration is applied.
- `scripts/little_loops/issue_history/evolution.py` — history-db consumer; may consume `find_learning_tests()` in future work.

### Similar Patterns

- `scripts/little_loops/session_store.py:816-866` `record_issue_snapshot()` — **closest precedent**: reads markdown file → parses frontmatter → `INSERT OR IGNORE` → `_index()` → commit. Silent no-op on `OSError`. Mirror its shape.
- `scripts/little_loops/session_store.py:1041-1091` `record_commit_event()` — **closest precedent for "proves idempotency via UNIQUE column"**; returns `bool` based on `cursor.rowcount`; only writes FTS row when underlying insert landed.
- `scripts/little_loops/session_store.py:1538-1583` `_backfill_snapshots()` — **closest backfill precedent**: iterates `*.md` files, parses frontmatter, INSERT OR IGNORE on `(issue_id, transition)` UNIQUE.
- `scripts/little_loops/history_reader.py:524-559` `recent_commit_events()` — **closest reader precedent**: read-only connection, graceful degradation, `_row_to_dataclass()` mapping.
- `scripts/little_loops/cli/learning_tests.py:48-72` `cmd_prove()` — write site for `record_learning_test_event()` (after `check_learning_test()` returns).
- `scripts/little_loops/cli/issues/set_status.py:60-66` — **direct-call write precedent**: `try: record_issue_snapshot(...); except: pass`.
- `scripts/little_loops/hooks/user_prompt_submit.py:82-94` — alternative `contextlib.suppress(Exception)` precedent for recorders.
- `.issues/enhancements/P3-ENH-2151-store-issue-content-snapshots-in-history-db.md` (lines 73–90, 280–286) — full pipeline + Resolution block format to mirror.
- `.issues/enhancements/P2-ENH-2458-capture-git-commit-metadata-into-history-db.md` (lines 108–119, 138–154) — **most recent schema-bump Resolution block** to mirror.

### Tests

- `scripts/tests/test_session_store.py:2872-2939` (`TestSchemaV14`) — mirror for schema-version assertion.
- `scripts/tests/test_session_store.py:2942-3012` (`TestRecordIssueSnapshot`) — mirror for producer round-trip tests.
- `scripts/tests/test_session_store.py:3015-3072` (`TestBackfillSnapshots`) — mirror for backfill tests.
- `scripts/tests/test_session_store.py:3075-3095` (`_bootstrap_schema_at`) — reusable helper for v18→v19 upgrade test.
- `scripts/tests/test_history_reader.py` — mirror for reader tests.
- `scripts/tests/test_cli_learning_tests.py` — existing CLI tests must continue to pass.

### Documentation

- `docs/ARCHITECTURE.md` — add a `learning_test_events` row to the schema-version table (find the v18 row added by ENH-2459; append v19).
- `docs/reference/API.md` — add `session_store.record_learning_test_event`, `_backfill_learning_test_events`, `history_reader.recent_learning_tests`, `find_learning_test` entries.
- `docs/reference/CLI.md` — document `ll-session search --fts ... --kind learning_test` and `ll-session recent --kind learning_test`.
- `docs/guides/LEARNING_TESTS_GUIDE.md` — note that records are mirrored into history.db and discoverable via `ll-session search --fts`.
- `thoughts/history-db-expand-wiring.md` — already names this work in §3 ranked recommendation #9 (line 70 of EPIC-2457 confirms); close-out the reference once shipped.

### Configuration

- No new config keys required. Existing `analytics.capture` keys gate other recorders; per ENH-2458/2459 precedent, `learning_test_events` is permissive by default (no gate).
- `LL_HISTORY_DB` env var (resolved via `resolve_history_db()`) already provides override plumbing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Canonical SQL block to append (mirror `commit_events` at session_store.py:505-520)** — UNIQUE on `record_id`, no inline composite; auxiliary indexes on `target` and `status`. Confirmed against `_backfill_commit_events` precedent (returns `int` rowcount, gates FTS write on `cursor.rowcount`).
- **`recent()` is auto-discoverable** — once `"learning_test"` is in `_KIND_TABLE`, `recent(db, kind="learning_test")` works at session_store.py:1268 with no other code change (uses `SELECT * FROM {table} ORDER BY id DESC LIMIT ?`).
- **`history_reader.search()` is auto-discoverable** — `kind="learning_test"` filter passes through to FTS5 `WHERE kind = ?` clause at history_reader.search; no reader-side changes required for `--fts`.
- **`_index()` signature is keyword-only** — must pass `kind`, `ref`, `anchor`, `ts` as keyword args (session_store.py:705). Use `ref=slug`, `anchor=file_path`, `content=f"{target} {claims} {body[:512]}"`.
- **Learning-test frontmatter uses `yaml.safe_load` directly** — `learning_tests/__init__.py:_read_frontmatter_yaml` at line 82 deliberately bypasses the project's `parse_frontmatter` because `assertions` is a nested list of `{claim, result}` dicts. Reuse this parser in both producer and backfill; don't substitute the project's parser.
- **Idempotency key choice** — `(record_id)` UNIQUE (not composite) is sufficient because `record_id` is the slug stem; re-proves overwrite `last_proved_at` via UPDATE-on-conflict, or use composite `(record_id, status_date)` if you want history of transitions. Recommend simple `(record_id)` UNIQUE + UPDATE semantics matching `record_commit_event`'s `_infer_issue_id`-style first-write-wins.
- **CLI `--kind` lists are duplicated** — both `search_parser` (cli/session.py:92-103) and `recent_parser` (cli/session.py:113-127) hardcode the same `choices=[...]` literal. Must update **both**; missing one creates silent argparse error.
- **`cli_event_context` already wraps `main_learning_tests`** (cli/learning_tests.py:145) — gives proof the `DEFAULT_DB_PATH` import works; new write calls sit alongside it, not inside.
- **Tests use `tmp_path / "history.db"`** — no shared fixtures; each test gets a fresh DB. This isolates the v18→v19 migration test from concurrent state.
- **EPIC-1707 graceful-degradation contract is non-negotiable** — writes are best-effort (`contextlib.suppress(Exception)` or `try/except: pass`); reads return `[]`/`None` on missing DB. New code must conform.
- **No external dependencies detected** — only stdlib (`sqlite3`, `json`, `yaml` via PyYAML which is already a project dep), SQLite FTS5 (built-in), and internal modules. `learning_tests_required` field intentionally omitted.

## Acceptance Criteria

- Schema migration lands; `learning_test_events` table exists.
- A `ll-learning-tests prove <id>` invocation updates the matching row's `last_proved_at` and `status` columns.
- A `ll-learning-tests mark-stale <id>` reflects in the DB row.
- `ll-session search --fts "<target or assertion fragment>" --kind learning_test` returns matching registry records.
- `history_reader.find_learning_tests(target="X")` returns records.
- `_backfill_learning_test_events()` populates from existing filesystem records without duplicating.
- Indexes (`idx_learning_tests_target`, `idx_learning_tests_status`) exist; `EXPLAIN QUERY PLAN` shows use.
- Tests cover: prove path, mark-stale path, backfill, read API, FTS.

## Implementation Steps

1. Schema migration for `learning_test_events`; bump `SCHEMA_VERSION`.
2. Add `"learning_test"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_learning_test_event()` and `_backfill_learning_test_events()` in `session_store.py`.
4. Wire `ll-learning-tests prove` to call `record_learning_test_event()`.
5. Wire `ll-learning-tests mark-stale` to call `record_learning_test_event()`.
6. Periodic reconcile (filesystem mtime-based, in-session lazy) — runs at `session_start` to pick up edits made outside the CLI.
7. Extend `history_reader.find_learning_tests()` and `find_learning_test_by_record_id()`.
8. Tests: `TestRecordLearningTest`, `TestSchemaV15` (or higher), `TestBackfillLearningTest`, `TestLearningTestFtsSearch`.
9. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md` updates, `docs/reference/CLI.md` for new `--kind learning_test`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete anchor references for each step:_

1. `session_store.py:_MIGRATIONS` list (append at end), `SCHEMA_VERSION = 19` (was 18). Mirror v18 / `test_run_events` block at lines 524–544.
2. `_VALID_KINDS` (line 104 frozenset) + `_KIND_TABLE` (line 130 dict) — add `"learning_test"` and `"learning_test": "learning_test_events"` in lockstep.
3. `record_learning_test_event()` body mirrors `record_issue_snapshot()` at lines 816–866 (read markdown → parse YAML via `learning_tests._read_frontmatter_yaml` → INSERT OR IGNORE → `_index()` → commit). `_backfill_learning_test_events()` mirrors `_backfill_snapshots()` at lines 1538–1583 (iterate `*.md`, parse, insert). Add both names to `__all__`.
4. `cli/learning_tests.py:cmd_prove()` (line 48) — after `check_learning_test(args.target)`, wrap the new write call in `try: ... except: pass`. Mirror `cli/issues/set_status.py:60-66` pattern.
5. `cli/learning_tests.py:cmd_mark_stale()` (line 84) — after `mark_stale(slugify(args.target))`, re-call `record_learning_test_event(...)`. `cmd_orphans` line 134 may also write via `--mark-stale`.
6. Add an opt-in `registry_dir` parameter to `backfill()` at session_store.py:2441; gate on `registry_dir.is_dir()`; add `"learning_tests": 0` to `counts` init at line 2462. Wire into `cli/session.py:backfill_cmd` so `ll-session backfill --learning-tests` (or `ll-session backfill` with default registry_dir) populates rows.
7. `history_reader.py` — add `LearningTestEvent` dataclass next to `CommitEvent`/`RunEvent` (lines 67–189); add `recent_learning_tests()` mirroring `recent_commit_events()` at lines 524–559; add `find_learning_test(target, ...)` returning `LearningTestEvent | None`. Update `Public API:` block at lines 1–42.
8. `cli/session.py:search_parser` (`choices=[...]` at lines 92–103) and `recent_parser` (`choices=[...]` at lines 113–127) — add `"learning_test"` to both literal lists.
9. `test_session_store.py` — add `TestSchemaV19LearningTestEvents` (mirror `TestSchemaV14` at line 2872), `TestRecordLearningTestEvent` (mirror `TestRecordIssueSnapshot` at line 2942), `TestBackfillLearningTests` (mirror `TestBackfillSnapshots` at line 3015). Update legacy `assert SCHEMA_VERSION == 18` literals to `19` (search for `SCHEMA_VERSION == 18` across the file). Update `test_all_tables_created` table tuple (line 60).
10. `test_history_reader.py` — add `test_recent_learning_tests_*` mirroring `test_recent_commit_events_*`. `test_cli_learning_tests.py` — confirm `cmd_prove` / `cmd_mark_stale` tests still pass.
11. Docs: `docs/ARCHITECTURE.md` schema-version table — append v19 row. `docs/reference/API.md` — add 4 new entries. `docs/reference/CLI.md` — add `--kind learning_test` documentation.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 8 ("Learning Test Registry"), §3 ranked recommendation #9
- `.claude/CLAUDE.md` § CLI Tools `ll-learning-tests` entry — registry CLI surface
- `scripts/little_loops/learning_tests/__init__.py` — registry module (reference for record schema)
- `scripts/little_loops/session_store.py:_index()` — shared FTS5 writer

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` module references |
| `docs/reference/CLI.md` | `ll-session --kind learning_test`, `ll-learning-tests` flags |
| `docs/guides/LEARNING_TESTS_GUIDE.md` | Registry semantics |

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-07-07T00:35:03 - `984dde16-4d04-4519-aaa2-e9d51aefdda9.jsonl`
- audit - 2026-07-06 - Confirmed `docs/guides/LEARNING_TESTS_GUIDE.md` exists (removed "(if exists)" hedge) and `.ll/learning-tests/*.md` registry files are present.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
