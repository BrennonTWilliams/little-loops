---
id: ENH-1710
title: Map session IDs to JSONL file paths in history.db
type: ENH
priority: P3
status: done
captured_at: '2026-05-26T01:31:23Z'
completed_at: '2026-06-01T03:29:10Z'
discovered_date: '2026-05-26'
discovered_by: capture-issue
parent: EPIC-1707
decision_needed: false
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1710: Map session IDs to JSONL file paths in history.db

## Summary

Add a `sessions` table (or view) to `.ll/history.db` that maps `session_id` values to their corresponding JSONL file paths on disk, enabling direct navigation from any DB event to its source log.

## Current Behavior

`history.db` event tables (`tool_events`, `message_events`, `file_events`, `user_corrections`) carry a `session_id` column with no corresponding mapping table. The session-ID-to-JSONL-path mapping is built at query time by `ll-logs discover` scanning `~/.claude/projects/`, but the result is not persisted, leaving no way to navigate from a DB event back to its source log file.

## Expected Behavior

- A `sessions` table in `history.db` maps each `session_id` to its JSONL file path and metadata.
- `ll-session path <session_id>` resolves and prints the JSONL path directly from the DB, exiting non-zero if unknown.
- After `ll-session backfill`, all session IDs present in `tool_events` or `message_events` have a corresponding `sessions` row with a non-null `jsonl_path`.
- `ll-session recent` output includes the JSONL path alongside session metadata.

## Motivation

Every event table in `history.db` (`tool_events`, `message_events`, `file_events`, `user_corrections`) carries a `session_id` column, but the DB has no way to resolve that ID back to the JSONL file it came from. `ll-logs discover` builds this mapping at query time by scanning `~/.claude/projects/`, but the result is not persisted. This creates a broken link in what should be a navigable chain: issue → session → log.

Closing this gap is the cheapest step toward drill-down from a high-level issue to full session detail, and is a prerequisite for the issue-to-session cross-reference (ENH-1711) and any future LCM-style history navigation.

## Implementation Steps

1. Add a `sessions` table in a new schema migration:
   ```sql
   CREATE TABLE sessions (
       session_id TEXT PRIMARY KEY,
       jsonl_path TEXT NOT NULL,
       started_at TEXT,
       project_path TEXT
   );
   ```
2. Populate it during `backfill()` by correlating session IDs found in JSONL files with their file paths (already parsed in `_backfill_tool_events` and `_backfill_messages`).
3. Populate it live in `SQLiteTransport.send()` on the first event of each `session_id` by resolving the path from `ll-logs discover` output or a direct glob of the logs dir.
4. Add `ll-session path <session_id>` subcommand that prints the resolved JSONL path.
5. Update `ll-session recent` output to include the JSONL path alongside session metadata.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — Migration details:**
- `SCHEMA_VERSION` in `session_store.py` is currently `3`; bump to `4` and append the `CREATE TABLE sessions` SQL as `_MIGRATIONS[3]` (the list is positional — index 3 upgrades v3→v4)
- Test pattern: add `class TestSchemaV4` with three tests following the `TestSchemaV3` shape in `test_session_store.py`: (a) table exists after clean `ensure_db()`, (b) v3 DB upgrades to v4, (c) `INSERT OR IGNORE` dedup is idempotent

**Step 2 — Backfill insertion point:**
- In `_backfill_tool_events(conn, jsonl_files)` and `_backfill_messages(conn, jsonl_files)`, both `session_id = record.get("sessionId")` and `jsonl_file: Path` (the loop variable) are in scope simultaneously — use `INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)` at this point
- The `backfill()` function should add `"sessions"` to the `counts` dict
- **Gap**: `cli/session.py` `backfill` subcommand calls `backfill(args.db)` with no `jsonl_files` argument. The acceptance criterion requires all session IDs in `tool_events`/`message_events` to be populated after backfill. Either `backfill()` must auto-discover JSONL files when `jsonl_files=None` (via `get_project_folder()`), or the CLI must be updated to pass them. This needs resolution.

**Step 3 — Live population options (decision required):**

`SQLiteTransport.send()` currently receives no `session_id` field in the event dict — the "first event of each session_id" approach cannot work as written without one of the following choices:

**Option A — Backfill-only (no live population):** Skip live population in `send()` entirely. The two acceptance criteria are fully met by backfill alone. Live population can be deferred to a follow-up or addressed when session events carry session_id.

> **Selected:** Option A — Backfill-only — both `_backfill_tool_events()` and `_backfill_messages()` already hold `session_id` and `jsonl_file` simultaneously in scope; one `INSERT OR IGNORE` each is the lowest-friction implementation with no new infrastructure.

**Option B — Inject path at `SQLiteTransport.__init__`:** At construction time in `wire_transports()` (`transport.py`), call `get_current_session_jsonl()` from `session_log.py` to resolve the current JSONL path. Cache it on the instance. Still requires a `session_id` to store — would need the session start hook to emit an event with `session_id`, OR the JSONL filename stem can be used directly as the session_id (since non-agent JSONL files are named `<session_id>.jsonl`).

**Option C — New `session.start` event from hook:** Emit a `session.start` event from `hooks/session_start.py` carrying `session_id` and `jsonl_path`, handle it in `send()` with a new branch (alongside the existing `_LOOP_EVENT_TYPES` and `issue.*` branches).

**Step 4 — CLI `path` subcommand pattern:**
- Follows the `related` subcommand shape in `cli/session.py:_build_parser()` and `main_session()`: `subparsers.add_parser("path")` with `add_argument("session_id", metavar="SESSION_ID")`, print the path to stdout or exit non-zero if not found
- Test follows `TestMainSession` pattern in `test_ll_session.py`: `ensure_db(db)`, inject a row, patch `sys.argv`, assert output via `capsys`

**Step 5 — `recent` output:**
- The existing plain-text output in `main_session()` iterates `{k}={v}` for non-null columns — a `jsonl_path` column in the query result surfaces automatically; no extra code needed for plain-text output

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `main_session()` backfill branch — include `sessions=N` in the output line and include `sessions` count in the total sum (mirrors `messages=N` pattern)
7. Update docs with new `path` subcommand: `.claude/CLAUDE.md`, `commands/help.md`, `docs/reference/CLI.md` (Subcommands table + Examples), `docs/reference/API.md` (`main_session` bullet list), `docs/ARCHITECTURE.md` (directory tree comment)
8. Fix `test_backfill_missing_sources_is_noop` in `test_session_store.py` — add `"sessions": 0` to the exact-equality expected dict before this test is run
9. Fix `test_backfill_reports_messages_count` in `test_ll_session.py` — add `"sessions"` key to mock return dict and update `"Backfilled 10"` assertion to the new correct total
10. If Option B is chosen: update `AutoManager.__init__()` in `scripts/little_loops/issue_manager.py` to pass `jsonl_path` to `SQLiteTransport()`; update `wire_transports()` in `transport.py` accordingly; audit all `wire_transports()` call sites (`cli/loop/lifecycle.py`, `cli/loop/run.py`, `cli/parallel.py`, `cli/sprint/run.py`)

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-31.

**Selected**: Option A — Backfill-only (no live population)

**Reasoning**: Both `_backfill_tool_events()` and `_backfill_messages()` already hold `session_id` and `jsonl_file` simultaneously in scope, making the insertion a single `INSERT OR IGNORE` per function with no new utilities or abstractions. Backfill is the established mechanism for seeding all tables from on-disk sources, the `INSERT OR IGNORE` + `PRIMARY KEY` dedup pattern is identical to the `issue_events` table, and every test template needed (`TestSchemaV3`, `related` subcommand) is directly present. Options B and C require either heuristic path resolution (unreliable under `ll-parallel` concurrent sessions) or novel EventBus routing from hooks that has no existing precedent in the codebase.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Backfill-only | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B — Constructor inject | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option C — session.start event | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: `_backfill_tool_events` and `_backfill_messages` in `session_store.py` already loop `for jsonl_file in jsonl_files` and extract `session_id = record.get("sessionId")` — both variables are in scope at the same time; reuse score 3/3
- Option B: `get_current_session_jsonl()` utility is reusable and constructor-injection matches sibling transports, but `AutoManager.__init__()` bypasses `wire_transports()` independently and stem-as-session_id is a heuristic that fails under concurrent `ll-parallel` sessions; reuse score 2/3
- Option C: `send()` branch pattern and schema migration machinery are well-templated by the `issue.*` branch, but no hook has ever held or used an EventBus reference — the only existing hook-to-DB write (`post_tool_use.py`) bypasses the bus entirely; reuse score 2/3

## API/Interface

New `sessions` table in `history.db`. New `ll-session path <session_id>` subcommand.

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    jsonl_path TEXT NOT NULL,
    started_at TEXT,
    project_path TEXT
);
```

## Scope Boundaries

- **In scope**: `sessions` table schema and migration; `backfill()` population from existing JSONL files; live population in `SQLiteTransport.send()` on first event per session; `ll-session path <session_id>` subcommand; `ll-session recent` JSONL path display.
- **Out of scope**: Issue-to-session cross-reference (ENH-1711); LCM-style history navigation; querying or indexing session content; changes to existing event tables or their schemas.

## Acceptance Criteria

- `ll-session path <session_id>` prints the JSONL path or exits non-zero if unknown.
- After `backfill()`, all session IDs present in `tool_events` or `message_events` have a corresponding row in `sessions` with a non-null `jsonl_path`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` - Add `sessions` table schema and schema migration
- `scripts/little_loops/cli/session.py` - Add `path` subcommand; update `recent` output to include JSONL path
- ~~`scripts/little_loops/transport.py`~~ - Not needed; Option A (backfill-only) was selected, no live population in `send()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store.py` `backfill()` function - Correlate session IDs from JSONL files during backfill

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py` — directly constructs `SQLiteTransport(db_path)` in `AutoManager.__init__()` outside `wire_transports()`; **must update** if Option B is chosen and `SQLiteTransport.__init__` gains a `jsonl_path` parameter [Agent 1 finding]
- `scripts/little_loops/hooks/session_start.py` — calls `ensure_db()` at session start; gains `sessions` table automatically via migration (no change needed unless Option C is chosen and `session.start` event is emitted here) [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — calls `wire_transports()`; must update if Option B changes the `wire_transports()` signature [Agent 1 finding]
- `scripts/little_loops/cli/loop/run.py` — calls `wire_transports()` [Agent 1 finding]
- `scripts/little_loops/cli/parallel.py` — calls `wire_transports()` [Agent 1 finding]
- `scripts/little_loops/cli/sprint/run.py` — calls `wire_transports()` [Agent 1 finding]

### Similar Patterns
- `ll-logs discover` in `scripts/little_loops/cli/` - Existing session-ID-to-path mapping logic to reuse/adapt

### Tests
- `scripts/tests/test_session_store.py` - Add tests for `sessions` table creation, migration, and `backfill()` population
- `scripts/tests/test_ll_session.py` - Add tests for `path` subcommand (found path, unknown session_id)
- `scripts/tests/test_transport.py` - Update if live session population is added to `SQLiteTransport.send()`

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will BREAK and must be updated:**
- `scripts/tests/test_session_store.py: TestBackfill.test_backfill_missing_sources_is_noop` — asserts exact dict equality `== {"issues": 0, "loops": 0, "tools": 0, "messages": 0}`; fails when `backfill()` adds `"sessions": 0` to return dict — add `"sessions": 0` to expected dict [Agent 3 finding]
- `scripts/tests/test_ll_session.py: TestMainSession.test_backfill_reports_messages_count` — hardcodes `"Backfilled 10"` (sum of mock return dict); if `main_session()` format string is updated to include `sessions=`, mock return dict needs `"sessions"` key and expected total must change — update mock and assertion [Agent 3 finding]

**New test methods needed:**
- `scripts/tests/test_session_store.py: TestSchemaV4` — new class with 3 methods following `TestSchemaV3` shape: (a) `test_sessions_table_exists_after_ensure_db` — assert `"sessions"` in `sqlite_master` tables after fresh `ensure_db()`; (b) `test_v3_db_upgrades_to_v4` — bootstrap v3 schema via `conn.executescript(...)`, call `ensure_db()`, assert `int(version) == SCHEMA_VERSION` and `"sessions"` in table names; (c) `test_sessions_insert_or_ignore_is_idempotent` — insert same `(session_id, jsonl_path)` twice, assert `COUNT(*) == 1` [Agent 3 finding]
- `scripts/tests/test_session_store.py: TestBackfill.test_backfill_tool_events_populates_sessions` — call `backfill(..., jsonl_files=[jsonl])` with JSONL containing `sessionId`, assert `counts["sessions"] == 1` and `sessions` table row has non-null `jsonl_path` [Agent 3 finding]
- `scripts/tests/test_ll_session.py: TestArgumentParsing.test_path_subcommand` — patch `sys.argv` with `["ll-session", "path", "abc123"]`, call `_parse_args()`, assert `args.command == "path"` and `args.session_id == "abc123"` [Agent 3 finding]
- `scripts/tests/test_ll_session.py: TestMainSession.test_path_found` — insert `sessions` row via `connect(db)`, patch `sys.argv` with `["ll-session", "--db", str(db), "path", "<session_id>"]`, assert `main_session() == 0` and JSONL path in stdout [Agent 3 finding]
- `scripts/tests/test_ll_session.py: TestMainSession.test_path_not_found` — empty DB via `ensure_db(db)`, patch `sys.argv` with `path NOPE`, assert `main_session() == 1` and "not found" (or equivalent) in stdout — mirror `test_related_no_match` shape [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — `ll-session` bullet in "CLI Tools" section explicitly lists subcommands `(search --fts / recent --kind / backfill)`; add `path <session_id>` [Agent 2 finding]
- `commands/help.md` — line 271, inline `ll-session` description lists `(search/recent/backfill)`; add `path` [Agent 2 finding]
- `docs/reference/CLI.md` — `### ll-session` Subcommands table and Examples block both missing `path` subcommand entry [Agent 2 finding]
- `docs/reference/API.md` — `### main_session` subcommand bullet list missing both `related` and `path` subcommands [Agent 2 finding]
- `docs/ARCHITECTURE.md` — inline comment on `session.py` in directory tree lists subcommands without `path` [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/user_messages.py` — `get_project_folder(cwd)` converts CWD to `~/.claude/projects/<encoded>/`; the canonical way to discover the JSONL directory for the current project
- `scripts/little_loops/session_log.py` — `get_current_session_jsonl()` returns the most recently modified non-agent JSONL file for the current project folder; candidate for live path resolution
- `scripts/little_loops/transport.py` — `wire_transports()` constructs `SQLiteTransport(db_path)` — the init site where session JSONL path could be injected if live population is implemented via Option B below

## Impact

- **Priority**: P3 - Foundational plumbing that unblocks ENH-1711 and session drill-down features; not urgent standalone.
- **Effort**: Small - Additive schema migration + backfill update + one new CLI subcommand; reuses existing `ll-logs discover` mapping logic.
- **Risk**: Low - Purely additive change; no existing tables, APIs, or CLI contracts are modified.
- **Breaking Change**: No

## Labels

`enhancement`, `database`, `session-management`, `captured`

## Status

**Open** | Created: 2026-05-26 | Priority: P3

## Resolution

Implemented Option A (backfill-only) as decided. Added `sessions` table via schema migration v4, `_backfill_sessions()` helper, `ll-session path <session_id>` subcommand, and updated backfill output to include `sessions=N`. All 8 new/updated tests pass.

## Session Log
- `/ll:manage-issue` - 2026-06-01T03:29:10Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f14a7706-20ac-420c-8865-404d97381536.jsonl`
- `/ll:ready-issue` - 2026-06-01T03:22:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ec2c276-2677-410c-87b1-51ca4b43b871.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/56875523-c5bf-4970-9487-416a6100b3b1.jsonl`
- `/ll:decide-issue` - 2026-06-01T03:17:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d099241-3331-40d2-823a-0f9b8f0d30f6.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6576658-4b5f-479e-9c7b-d58a456320d2.jsonl`
- `/ll:wire-issue` - 2026-06-01T03:09:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11bd8b12-b81e-4bd8-8cbc-d01584795db0.jsonl`
- `/ll:refine-issue` - 2026-06-01T03:02:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aae7b132-127e-4e9c-93e8-316decbbcb6d.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:format-issue` - 2026-05-26T20:18:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f238e1de-2a0d-4c63-94af-3f5bc586be30.jsonl`
- `/ll:capture-issue` - 2026-05-26T01:31:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d0765b0-9906-45d9-a15b-8eadbab154a7.jsonl`
