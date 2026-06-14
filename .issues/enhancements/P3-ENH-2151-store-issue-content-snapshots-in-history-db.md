---
id: ENH-2151
type: ENH
priority: P3
status: open
title: Store issue content snapshots in history.db at lifecycle transitions
captured_at: '2026-06-14T19:15:05Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
decision_needed: false
confidence_score: 92
outcome_confidence: 76
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 18
---

# ENH-2151: Store issue content snapshots in history.db at lifecycle transitions

## Summary

`history.db` tracks issue lifecycle events (status transitions, timestamps, type, priority) but stores no issue content — title, description, acceptance criteria, implementation plan, etc. all live exclusively in `.issues/` markdown files. This creates a gap: completed issue context is inaccessible once files are moved or deleted, and there is no way to run SQL/FTS queries across issue descriptions.

Add an `issue_snapshots` table that captures a snapshot of issue content at key lifecycle transitions, at minimum `captured` and `done`.

## Current Behavior

`history.db` tracks issue lifecycle events (status transitions, timestamps, type, and priority) but stores no issue content. Title, description, acceptance criteria, and implementation plans live exclusively in `.issues/` markdown files. Once a file is moved, archived, or the project is cloned fresh, that context is permanently inaccessible. `ll-history-context` must hit the filesystem for every lookup, and full-text search across issue bodies is not possible.

## Expected Behavior

`history.db` includes an `issue_snapshots` table that stores a full content snapshot at key lifecycle transitions (`captured`, `done`, `cancelled`). An FTS5 virtual table (`issue_snapshots_fts`) enables full-text search across all issue titles and bodies. `ll-history-context` falls back to the snapshot when the source `.md` file is absent. `ll-session backfill --snapshots` hydrates the table from existing `.issues/` files without creating duplicate rows.

## Motivation

The system is fundamentally issue-driven, but `history.db` cannot answer basic questions like:
- "What did ENH-1234 describe?" (file may be gone)
- "Find completed issues that mentioned caching" (FTS impossible today)
- "What was the acceptance criteria for this bug?" (no DB record)

`ll-history-context` must hit the filesystem for every lookup; once an issue file is archived or the project is cloned fresh, that context is lost permanently. Storing snapshots at transition points gives the DB a durable, queryable record without making it the source of truth for live issues.

## Proposed Schema

```sql
CREATE TABLE issue_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,                  -- ISO 8601 UTC
    issue_id    TEXT NOT NULL,                  -- e.g. "ENH-2151"
    transition  TEXT NOT NULL,                  -- "captured" | "done" | "cancelled" | etc.
    title       TEXT,
    priority    TEXT,
    issue_type  TEXT,
    body        TEXT,                           -- full markdown body (frontmatter stripped)
    frontmatter TEXT                            -- raw YAML frontmatter as JSON or TEXT
);

CREATE INDEX idx_issue_snapshots_issue_id ON issue_snapshots(issue_id);
CREATE INDEX idx_issue_snapshots_transition ON issue_snapshots(transition);

-- FTS5 virtual table over title + body
CREATE VIRTUAL TABLE issue_snapshots_fts USING fts5(
    issue_id UNINDEXED,
    title,
    body,
    content='issue_snapshots',
    content_rowid='id'
);
```

## Implementation Steps

1. **Schema migration** — append a new entry to `_MIGRATIONS` list in `scripts/little_loops/session_store.py` (currently 13 entries, index 13 = v14) and increment `SCHEMA_VERSION` from `13` to `14`. SQL to add: `issue_snapshots` table with `(id, ts, issue_id, transition, title, priority, issue_type, body, frontmatter)`, unique dedup index `idx_issue_snapshots_dedup ON issue_snapshots(issue_id, transition)`, and FTS5 index `issue_snapshots_fts`.
2. **Snapshot writer** — add `record_issue_snapshot(db_path, issue_id, transition, file_path)` to `session_store.py`: reads the file, calls `parse_frontmatter(text)` for metadata and `strip_frontmatter(text)` for body (both from `scripts/little_loops/frontmatter.py`), `INSERT OR IGNORE` into `issue_snapshots`, then writes to `issue_snapshots_fts` explicitly (content tables do not auto-sync). Export via `__all__`.
3. **Event-driven wiring** — in `SQLiteTransport.send()` (line 854 of `session_store.py`), after the existing `INSERT OR IGNORE INTO issue_events(...)`, call `record_issue_snapshot()` when `event.get("file_path")` is present and `transition in ("done", "open", "cancelled")`; the event dict already carries `"file_path"` from all six `issue_lifecycle.py` emit sites.
4. **Backfill utility** — add `_backfill_snapshots(conn, issues_dir)` in `session_store.py` following the `_backfill_issues()` pattern (line 938); in `backfill()` (line 1755) add `"snapshots": 0` to `counts` and call it. In `cli/session.py`, add `--snapshots` flag to the `backfill_parser` (line 123) and branch on `args.snapshots` in the `backfill` command handler (line 312) to call `_backfill_snapshots()` separately. Note: `backfill --snapshots` is essential because `cmd_set_status()` in `cli/issues/set_status.py` does NOT emit EventBus events, so event-driven writes miss all `set_status`-driven transitions.
5. **Query surface** — in `cli/session.py:main_session()`, extend the `search --fts` branch (line 220) to also query `issue_snapshots_fts`. In `cli/history_context.py:main_history_context()` (line 185), add a fallback query `SELECT title, body FROM issue_snapshots WHERE issue_id = ? ORDER BY ts DESC LIMIT 1` that runs when the source `.md` file is absent and no rows were found via existing corrections/search paths.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `record_issue_snapshot` to `session_store.py:__all__` — it is listed in step 2 as "Export via `__all__`" but the list already has `record_correction`, `record_skill_event`, `record_retirement`; this is a mandatory parity step [Agent 2 finding]
7. Extend `main_session()` full-backfill success format string in `cli/session.py` to include `snapshots={counts.get('snapshots', 0)}` — currently the 7-key format string will silently drop the new key from operator output [Agent 2 finding]
8. Update all `SCHEMA_VERSION == 13` and `int(row[0]) == 13` assertions to `== 14` across 7 test locations: 6 in `test_session_store.py` and 1 in `test_assistant_messages.py` [Agent 2/3 finding]
9. Update `TestBackfill.test_backfill_missing_sources_is_noop` (add `"snapshots": 0`) and `TestEnsureDb.test_all_tables_created` (add `"issue_snapshots"`) in `test_session_store.py` [Agent 3 finding]
10. Update `docs/guides/HISTORY_SESSION_GUIDE.md` schema version reference to 14 and add `--snapshots` to `docs/reference/CLI.md` backfill flag list [Agent 2 finding]

## Scope Boundaries

- **In scope**: `issue_snapshots` table and `issue_snapshots_fts` FTS5 index; snapshot writes at `captured`, `done`, and `cancelled` transitions; `ll-session backfill --snapshots` sub-command; `ll-history-context` fallback to snapshot body when source file is absent; `ll-session search --fts` hitting the new FTS table
- **Out of scope**: Real-time sync on every file edit (snapshots only at transition points); replacing `.issues/` markdown as the source of truth for live issues; snapshot diffs or version history beyond per-transition snapshots; storing embedded images or binary attachments

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — add schema migration for `issue_snapshots` and `issue_snapshots_fts`; add `record_issue_snapshot()` function
- `scripts/little_loops/hooks/` — call `record_issue_snapshot` from the `issue_events` recorder at `captured` and `done` transitions
- `scripts/little_loops/cli/ll_session.py` — add `backfill --snapshots` sub-command; extend `search --fts` to include `issue_snapshots_fts`
- `scripts/little_loops/cli/ll_history_context.py` — add fallback to `issue_snapshots` when source `.md` file is missing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:1095-1096` — creates `EventBus` + `SQLiteTransport(db_path)`; is the wiring point where a snapshot observer would be registered alongside the existing transport
- `scripts/little_loops/issue_lifecycle.py:521,618,689,781,873,931` — six `event_bus.emit({...})` call sites for `issue.failure_captured`, `issue.closed`, `issue.completed`, `issue.deferred`, `issue.skipped`, `issue.started`; each event dict includes `issue_id` and `file_path`/`captured_at` fields that `record_issue_snapshot()` needs
- `scripts/little_loops/session_store.py:854-884` — `SQLiteTransport.send()` currently handles `event_type.startswith("issue.")` to insert into `issue_events`; snapshot write would be a side-effect here, right after the existing `issue_events` insert
- `scripts/little_loops/cli/session.py:312-356` — existing `backfill` subcommand handler; adding `--snapshots` flag here dispatches to `_backfill_snapshots()`
- `scripts/little_loops/cli/history_context.py:185-220` — `main_history_context()` currently queries `user_corrections` + `search_index`; snapshot fallback would add a third query path when source `.md` file is absent

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — exports `SQLiteTransport` in public API; must also export `record_issue_snapshot` once it is a public function [Agent 1 finding]
- `scripts/little_loops/cli/backfill_worker.py` — calls `backfill_incremental()` (not `backfill()`); unaffected by the `snapshots` key addition to `backfill()` return dict, but the two `main_session()` success-message format strings will become structurally inconsistent unless the full-backfill one is extended [Agent 2 finding]

### Similar Patterns
- `session_store.py` migration pattern — follow existing `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX` approach
- `ll-session backfill` — follow existing backfill sub-command structure for `--snapshots` variant

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected file paths (original Integration Map had stale names):**
- `scripts/little_loops/cli/ll_session.py` → actual path is `scripts/little_loops/cli/session.py`
- `scripts/little_loops/cli/ll_history_context.py` → actual path is `scripts/little_loops/cli/history_context.py`
- `scripts/little_loops/hooks/` → snapshot hook wiring lives in `scripts/little_loops/session_store.py:SQLiteTransport.send()` (line 854) — not a standalone hooks file; issue events arrive there already, so adding snapshot writes is an in-place side-effect of the existing `elif event_type.startswith("issue.")` branch

**Key anchors for implementation:**
- `session_store.py:SCHEMA_VERSION` — currently `13`; v14 migration appended to `_MIGRATIONS` list at index 13
- `session_store.py:_MIGRATIONS[0]` — shows FTS5 pattern: `CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(content, kind UNINDEXED, ref UNINDEXED, anchor UNINDEXED, ts UNINDEXED)` — the existing FTS5 is an autonomous (not content-table) FTS5; `issue_snapshots_fts` using `content='issue_snapshots'` is valid but different; verify trigger requirement for content-table syncing
- `session_store.py:_index()` — shared helper for all FTS writes; call it (or write directly to `issue_snapshots_fts`) after each snapshot insert
- `session_store.py:_backfill_issues()` (line 938) — template for `_backfill_snapshots()`: iterates `issues_dir.rglob("*.md")`, calls `parse_frontmatter(text)`, uses `INSERT OR IGNORE`; the new function additionally calls `strip_frontmatter(text)` to get body
- `frontmatter.py:strip_frontmatter()` (line 167) — extracts the markdown body (everything after the closing `---`); use alongside `parse_frontmatter()` in `record_issue_snapshot()`
- `session_store.py:SQLiteTransport.send()` (line 854) — event dict for `issue.*` events includes `"file_path"` and `"issue_id"`; use these to read the file and write the snapshot; the transition to snapshot at is `_derive_transition(event_type)` which maps `issue.completed`/`issue.closed` → `"done"`, `issue.created` → `"open"` (use as the `"captured"` transition)
- `session_store.py:backfill()` (line 1755) — returns `dict[str, int]` of counts; add `"snapshots": 0` key and dispatch to `_backfill_snapshots(conn, issues_dir)` in the same try block
- `cli/session.py:main_session()` (line 312) — `backfill` subparser parsed at this block; add `--snapshots` flag to `backfill_parser` and branch on `args.snapshots`
- `cli/history_context.py:main_history_context()` (line 185) — after `fresh_search` is collected, add a third query: `SELECT body FROM issue_snapshots WHERE issue_id = ?` (when source `.md` file doesn't exist and no DB rows found); append as last-resort fallback before `rows = rows[:_MAX_ROWS]`

**Idempotency — dedup index pattern:**
- v3 migration shows the correct pattern: `CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_events_dedup ON issue_events(issue_id, transition)` + `INSERT OR IGNORE`; apply same pattern to `issue_snapshots(issue_id, transition)` for backfill safety

**FTS5 content-table sync requirement:**
- If using `content='issue_snapshots'`, the FTS5 content table does NOT auto-sync; rows must be inserted explicitly into `issue_snapshots_fts` after every insert to `issue_snapshots` (no triggers in SQLite without manual trigger DDL)
- Simpler alternative consistent with existing `search_index` approach: skip the content-table approach and write issue title + body directly to the autonomous `search_index` table (kind=`"snapshot"`) — avoids trigger complexity

**Critical gap — `set_status` is NOT wired to EventBus:**
- `scripts/little_loops/cli/issues/set_status.py` — `cmd_set_status()` writes status transitions (including `done`) directly to frontmatter without emitting any EventBus event; `SQLiteTransport.send()` will never be called for these transitions
- This means event-driven snapshot writes (step 3 in Implementation Steps) will NOT fire when users transition issues via `ll-issues set-status`
- The `backfill --snapshots` sub-command is therefore essential for correctness (not just convenience); without it, most production `done` transitions will miss snapshot capture
- Option A: add EventBus emit call to `cmd_set_status()` alongside the frontmatter write; Option B: accept event-driven gaps and rely on backfill for completeness; Option C: add a post-write hook in `set_status` that calls `record_issue_snapshot()` directly (bypassing event bus)

### Tests
- `scripts/tests/` — snapshot insert on `captured`, on `done`, FTS search, backfill idempotency, missing-file fallback in `ll-history-context`

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will BREAK (must update before or alongside implementation):**
- `scripts/tests/test_session_store.py` — `TestSchemaV6.test_schema_version_is_seven`, `TestCliEventContext.test_schema_v8_cli_events_table_exists`, `TestSchemaV9.test_schema_version_is_nine`, `TestSchemaV10.test_schema_version_is_ten`, `TestSchemaV12.test_schema_version_is_twelve`, `TestSchemaV13.test_schema_version_is_thirteen` — all assert `SCHEMA_VERSION == 13` and `int(row[0]) == 13`; update to `== 14` [Agent 2/3 finding]
- `scripts/tests/test_assistant_messages.py` — `TestAssistantMessagesMigration.test_schema_version_is_12` — asserts `SCHEMA_VERSION == 13`; update to `== 14` [Agent 2 finding]
- `scripts/tests/test_session_store.py` — `TestBackfill.test_backfill_missing_sources_is_noop` — exact-dict equality breaks when `"snapshots": 0` is added to `backfill()` return dict; add the key to the expected dict [Agent 2/3 finding]
- `scripts/tests/test_session_store.py` — `TestEnsureDb.test_all_tables_created` — `issue_snapshots` not in expected tables set; add it [Agent 3 finding]
- `scripts/tests/test_ll_session.py` — `TestMainSession.test_backfill_reports_messages_count` — mock dict missing `snapshots` key and the `"Backfilled 12"` sum assertion may break if format string is extended; add `"snapshots": 0` to the mock return value [Agent 2/3 finding]

**New tests to write:**
- `scripts/tests/test_session_store.py` — `TestSchemaV14` class: `test_schema_version_is_fourteen`, `test_issue_snapshots_table_exists`, `test_issue_snapshots_fts_virtual_table_exists`, `test_v13_to_v14_migration`; follow `TestSchemaV13` pattern at line 2736 [Agent 3 finding]
- `scripts/tests/test_session_store.py` — `TestRecordIssueSnapshot` class: DB round-trip, FTS-indexed, idempotency (`INSERT OR IGNORE`); follow `TestRecordCorrection` pattern at line 1449 [Agent 3 finding]
- `scripts/tests/test_session_store.py` — `TestBackfillSnapshots` class: hydrate from `.issues/` files, idempotency (double-run produces no duplicates); follow `TestBackfillDedup` pattern at line 1147 [Agent 3 finding]
- `scripts/tests/test_ll_session.py` — `TestBackfillSnapshotsFlag`: `--snapshots` flag parsed from argv, CLI output includes `snapshots=N`, mock `backfill()` returns correct dict shape; follow `TestBackfillSinceFlag` pattern at line 469 [Agent 3 finding]
- `scripts/tests/test_history_context_cli.py` — snapshot body used when source `.md` missing, fallback NOT triggered when `.md` exists; follow `TestHistoryContextWithMatches` pattern at line 38 [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — update `session_store` module reference with `record_issue_snapshot()` function

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md` — states `Current schema version: 12` (already stale at v13; will become more stale at v14); update schema version to 14 [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-session backfill` subcommand section; add `--snapshots` flag to the documented flag list [Agent 2 finding]
- `docs/development/USER_GUIDE_AUDIT_REPORT.md` — audit table row states `History DB schema version: 12`; low-priority but will become stale again (update if the doc is maintained) [Agent 2 finding]

### Configuration
- N/A

## Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-14.

### Decision 1: FTS5 Approach

> **Selected:** Option B — Autonomous `search_index` with `kind="snapshot"` (12/12)

**Reasoning**: The codebase has exactly one FTS5 table (`search_index`, autonomous), used by every existing event kind via the shared `_index()` helper (`session_store.py:563–576`). A content-table FTS5 (`content='issue_snapshots'`) is a zero-precedent pattern requiring explicit sync after every insert — no existing code does this. Writing `kind="snapshot"` rows via `_index()` directly reuses the established pattern; `_backfill_issues()` at `session_store.py:989–996` is the exact template for `_backfill_snapshots()`. The `search --fts` unfiltered path already surfaces all kinds automatically; only `--kind` choices list and `_VALID_KINDS` need extending with `"snapshot"`.

**Schema impact**: The `issue_snapshots_fts` content-table from the Proposed Schema is **dropped**. The migration adds only `issue_snapshots` (for `ll-history-context` fallback queries by `issue_id`) plus `_index()` calls with `kind="snapshot"` for FTS. Implementation Step 2 should write to `search_index` via `_index()` instead of `issue_snapshots_fts`.

#### Scoring

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A: content-table FTS5 (`issue_snapshots_fts`) | 0/3 | 0/3 | 1/3 | 1/3 | 2/12 |
| **B: autonomous `search_index` `kind="snapshot"`** | **3/3** | **3/3** | **3/3** | **3/3** | **12/12** |

**Key evidence**:
- Option A: Zero `content=` FTS5 precedent; manual sync required; no test fixture pattern matches
- Option B: `_index()` called 10+ times across all existing kinds (`session_store.py:563–576`); `search --fts` unfiltered already surfaces all kinds (`cli/session.py:243–252`); four identical test fixtures use autonomous FTS5

---

### Decision 2: `set_status` Wiring

> **Selected:** Option C — Call `record_issue_snapshot()` directly in `set_status.py` (10/12)

**Reasoning**: Direct precedent exists in `hooks/user_prompt_submit.py:76–86`, which calls `record_correction()` and `record_skill_event()` directly without any EventBus. `record_issue_snapshot()` will have the same `(db_path, ...)` signature and is importable from `session_store`. Since `ll-issues set-status` is the canonical closure path in the `manage-issue` skill (`SKILL.md:454–457`) and automation loops (`rn-implement.yaml:686`) — with 48+ usage sites — real-time capture at this path is a functional requirement. `backfill --snapshots` remains essential for historical hydration of existing issues but is no longer the sole capture path for `set-status` transitions.

#### Scoring

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A: EventBus emit in `cmd_set_status()` | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |
| B: accept gap, rely on backfill | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| **C: direct `record_issue_snapshot()` call** | **2/3** | **2/3** | **3/3** | **3/3** | **10/12** |

**Tiebreaker (B vs C)**: Option B scores higher on Consistency/Simplicity, but Option C is selected because `set-status` is the canonical production closure path — a gap there means most real `done` snapshots would never be captured in real-time. The direct-call pattern has established precedent from `user_prompt_submit.py`.

**Key evidence**:
- Option A: No EventBus construction precedent inside thin CLI command handlers; would require inline `EventBus + SQLiteTransport` construction not matching any existing pattern
- Option B: `_backfill_issues()` well-established (`session_store.py:938`); but `set-status` is used in 48+ locations including the primary `manage-issue` skill — real-time gap is significant
- Option C: `record_correction()` called directly from `user_prompt_submit.py:76–86` without EventBus; same `(db_path, ...)` signature; `DEFAULT_DB_PATH` importable from `session_store`

## Acceptance Criteria

- [ ] `issue_snapshots` table exists in `history.db` after migration.
- [ ] A `captured` snapshot row is written when a new issue file is created via `capture-issue` (or any path that fires `issue_events`).
- [ ] A `done` snapshot row is written when an issue transitions to `done`.
- [ ] `ll-session search --fts "<keywords>"` returns results from `issue_snapshots_fts`.
- [ ] `ll-session backfill --snapshots` hydrates the table from existing `.issues/` files without duplicating rows.
- [ ] `ll-history-context` falls back to the snapshot body when the source `.md` file is missing.
- [ ] Tests cover: snapshot insert on `captured`, snapshot insert on `done`, FTS search, backfill idempotency, missing-file fallback.

## Impact

- **Priority**: P3 — Quality-of-life improvement; completed issue context is currently inaccessible but no active feature depends on it
- **Effort**: Medium — New DB table + FTS5 index + schema migration + hook wiring + backfill sub-command + fallback path in `ll-history-context`
- **Risk**: Low — Additive change; no existing tables modified; snapshot writes are side-effects that do not block the primary event flow
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | Session store design and DB migration patterns |
| `docs/reference/API.md` | `session_store` module reference |

## Labels

`enhancement`, `history-db`, `database`, `captured`

## Status

**Open** | Created: 2026-06-14 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-14_

**Readiness Score**: 92/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- ✅ **RESOLVED — FTS5 approach**: Autonomous `search_index` with `kind="snapshot"` selected (drop `issue_snapshots_fts`). See `## Decision Rationale`.
- ✅ **RESOLVED — `set_status` wiring**: Option C selected — call `record_issue_snapshot()` directly in `set_status.py` (same pattern as `user_prompt_submit.py:76–86`). See `## Decision Rationale`.
- **Test breakage front-loading required**: 8 `SCHEMA_VERSION == 13` / `int(row[0]) == 13` assertions across `test_session_store.py` (7 sites) and `test_assistant_messages.py` (1 site) will fail immediately on the schema bump — update these before the first green test run.

## Session Log
- `/ll:ready-issue` - 2026-06-14T23:02:52 - `ed58008d-84ad-4a79-8c91-d971b51097f4.jsonl`
- `/ll:confidence-check` - 2026-06-14T23:30:00Z - `42cd4ffb-169a-417a-b11f-e72e5261bc89.jsonl`
- `/ll:decide-issue` - 2026-06-14T22:55:19 - `34bb1a05-8a1f-4d94-8066-40252f7a0d05.jsonl`
- `/ll:confidence-check` - 2026-06-14T22:00:00Z - `457f1681-c7b3-4167-b30a-45436796c5cc.jsonl`
- `/ll:confidence-check` - 2026-06-14T21:45:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:decide-issue` - 2026-06-14T20:37:36 - `21049312-887c-4a50-8fa1-fe882f234969.jsonl`
- `/ll:confidence-check` - 2026-06-14T21:00:00Z - `c4d1e658-2782-47c6-a392-7a42920ff10b.jsonl`
- `/ll:confidence-check` - 2026-06-14T20:30:00Z - `7bb6a49b-1be9-40e2-9f6c-41ac04f4c30c.jsonl`
- `/ll:wire-issue` - 2026-06-14T20:10:12 - `f76a9942-cc29-47cd-b1cd-b20e4d22d86a.jsonl`
- `/ll:refine-issue` - 2026-06-14T19:55:18 - `d461489e-ec50-4afd-a938-695c20bdfd23.jsonl`
- `/ll:format-issue` - 2026-06-14T19:28:19 - `29e3c939-ad27-4578-a8f3-14603212cd41.jsonl`
- `/ll:capture-issue` - 2026-06-14T19:15:05Z - (conversation context)
