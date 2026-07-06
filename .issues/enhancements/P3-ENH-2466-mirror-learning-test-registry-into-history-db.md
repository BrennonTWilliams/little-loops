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
- audit - 2026-07-06 - Confirmed `docs/guides/LEARNING_TESTS_GUIDE.md` exists (removed "(if exists)" hedge) and `.ll/learning-tests/*.md` registry files are present.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
