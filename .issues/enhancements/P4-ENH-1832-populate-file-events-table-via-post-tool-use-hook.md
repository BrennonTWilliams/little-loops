---
id: ENH-1832
type: ENH
priority: P4
status: done
discovered_date: 2026-06-01
captured_at: '2026-06-01T01:10:54Z'
completed_at: '2026-06-01T05:23:49Z'
discovered_by: capture-issue
relates_to:
- EPIC-1707
- FEAT-1112
labels:
- enhancement
- captured
parent: EPIC-1707
confidence_score: 96
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
---

# ENH-1832: Populate `file_events` table via post_tool_use hook

## Summary

The `file_events` table in `history.db` has a complete schema (`path`, `op`,
`issue_id`, `git_sha`, `session_id`) but no active write path. The `post_tool_use`
hook already fires on every tool call and writes `tool_events`; extending it to
also write a row to `file_events` when the tool is Read/Write/Edit/Glob/Grep/Bash
(with a file argument) would enable `history_reader.recent_file_events()` queries.

## Current Behavior

The `file_events` table exists in `history.db` with a complete schema (`path`, `op`,
`issue_id`, `git_sha`, `session_id`), but no write path is active. The `post_tool_use`
hook fires on every tool call and writes to `tool_events`, but does not write to
`file_events`. As a result, `history_reader.recent_file_events()` always returns `[]`.

## Expected Behavior

The `post_tool_use` hook writes one row to `file_events` for each tool call where
`tool_name` is in `{Read, Write, Edit, Glob, Grep}` or is `Bash` with a detectable
file path argument. `history_reader.recent_file_events(path)` returns non-empty results
for files that have been accessed. The write is gated on `analytics.enabled` in config,
consistent with `tool_events` behavior.

## Motivation

`recent_file_events()` exists as a typed read API in `history_reader.py` but always
returns `[]` because the table is empty. File-operation history would let skills like
`refine-issue` and `confidence-check` surface recently touched files related to an
issue, giving them richer context about where work is actually happening.

## Acceptance Criteria

- `post_tool_use` intent handler writes one `file_events` row per tool call where
  `tool_name` is in `{Read, Write, Edit, Glob, Grep}` or is `Bash` with a detectable
  file path argument
- `path` is stored relative to the project root (no leading `./`)
- `op` is the tool name (e.g., `"Write"`, `"Edit"`, `"Bash"`)
- `issue_id` is `NULL` unless a `.issues/` path is detected in the tool args
- `git_sha` is `NULL` (populated only if a git context is available — out of scope here)
- `history_reader.recent_file_events(path)` returns results for files that have been
  accessed
- The FTS5 `search_index` is updated with `kind='file'` rows
- Write is gated on `analytics.enabled` in config (same gate as `tool_events`)

## Scope Boundaries

- `git_sha` population is out of scope; the column is written as `NULL`
- Bash commands with no detectable file path argument are not recorded
- Retroactive backfill of historical tool calls is out of scope
- FTS5 indexing of file content (vs. file path) is out of scope

## Implementation Steps

1. In `scripts/little_loops/hooks/post_tool_use.py` `handle()`, after the existing
   `tool_events` INSERT block (lines 59–81), add a `file_events` write branch using the
   same `contextlib.suppress(Exception)` / lazy-import / connect-execute-commit-close
   pattern. Extract the path per tool name using this mapping:
   - `Read`, `Write`, `Edit` → `tool_input.get("file_path")`
   - `Glob` → `tool_input.get("path") or tool_input.get("pattern")`
   - `Grep` → `tool_input.get("path")`
   - `Bash` → attempt regex extraction from `tool_input.get("command", "")`; skip if no
     file path detected
   Detect `issue_id` by checking whether the extracted path contains `.issues/` and
   parsing the issue ID from the path segment (e.g. `P4-ENH-1832-...md` → `ENH-1832`).
   Store path relative to `cwd` (strip leading `./`).
2. Add `write_file_event(db_path, session_id, path, op, issue_id=None)` to
   `scripts/little_loops/session_store.py` as a new named function (analogous to the
   inline pattern in `handle()`, but factored out). Design the signature to accept an
   optional `config` argument (e.g. `config: dict | None = None`) per the ENH-1835
   note below, so the finer-grained gate can be wired later without a signature change.
   **Note**: `session_store.write_tool_event()` does not exist as a named function —
   the `tool_events` INSERT is inlined in `handle()` (lines 59–81). The new
   `write_file_event()` is a net-new function, not a clone of an existing one. Follow
   the inline INSERT pattern for the implementation body.
3. After writing to `file_events`, call `_index()` (imported from `session_store`) with:
   `content=path, kind="file", ref=path, anchor=tool_name, ts=_now()`.
   `_index()` signature: `_index(conn, *, content, kind, ref, anchor, ts)` — see
   `session_store.py` line 274. This is a new call site; `post_tool_use.handle()` does
   not currently call `_index()` at all.
4. Add tests in `scripts/tests/test_hook_post_tool_use.py` for per-tool extraction
   logic (one case per tool name), and a round-trip test using the
   `TestPostToolUseWithSessionStore` class pattern (invoke `handle()` with analytics
   enabled, then query `file_events` directly via `sqlite3.connect`). Follow the
   `_write_config()` helper at line 85 for config fixture setup.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `config-schema.json` — change `analytics.enabled` description string to mention file-event recording alongside per-tool byte tracking (same key, description-only change)
6. Update `docs/reference/CONFIGURATION.md` — revise the `analytics.enabled` row under `### analytics` to mention that the gate also controls `file_events` writes (not only `tool_events` byte metrics)
7. Update `hooks/adapters/codex/post-tool-use.sh` — revise inline comment (line 8) to mention `file_events` write alongside byte metrics
8. Update `hooks/adapters/opencode/README.md` — update `tool.execute.after` intent table row description to reflect dual write

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/post_tool_use.py` — extend `handle()` with `file_events` write
- `scripts/little_loops/session_store.py` — add `write_file_event()` method
- `config-schema.json` — update `analytics.enabled` description string (currently says "Enable per-tool byte tracking in post_tool_use hook." — incomplete after ENH-1832 gates file_events too) [Wiring pass]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/history_reader.py` — `recent_file_events()` read path benefits from populated table

_Wiring pass added by `/ll:wire-issue`:_
- **Host dispatch scope note**: `hooks/hooks.json` has **no Claude Code `PostToolUse` entry** that invokes the Python `post_tool_use.handle()` dispatcher. The Python handler runs only for Codex (via `hooks/adapters/codex/post-tool-use.sh`) and OpenCode (via `hooks/adapters/opencode/index.ts`). ENH-1832's `file_events` writes — like the existing `tool_events` writes — are unreachable on the Claude Code host until a separate `PostToolUse` hook entry is added to `hooks/hooks.json`. This is consistent with the existing scope and is not a regression; it is noted here to avoid surprise during implementation verification. [Agent 2 finding]

### Similar Patterns
- `session_store.write_tool_event()` — existing pattern to follow for the new write method

### Tests
- `scripts/tests/test_session_store.py` — add `file_events` write/read round-trip tests
- `scripts/tests/test_hook_post_tool_use.py` — add `file_events` extraction tests alongside existing `TestPostToolUseWithSessionStore`; use `_write_config()` helper already defined there
- `scripts/tests/test_history_reader.py` — `TestRecentFileEvents` already tests the read side; `_insert_old_file_event()` (lines 101–112) shows the raw INSERT pattern

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_post_tool_use.py` — FTS5 round-trip: after a `file_events` write via `handle()`, `search(db, query="<path fragment>")` should return a result with `kind="file"` (validates step 3 of Implementation Steps — the `_index()` call) [Agent 3 finding]
- `scripts/tests/test_hook_post_tool_use.py` — issue-id extraction: a `file_path` containing `.issues/P4-ENH-1832-foo.md` should yield `issue_id="ENH-1832"` in the stored `file_events` row; a plain path should yield `issue_id=NULL` (Acceptance Criteria requirement, not yet in listed test cases) [Agent 3 finding]
- `scripts/tests/test_hook_post_tool_use.py` — per-tool path extraction parametrized cases: one test per tool name (`Read`→`file_path`, `Write`→`file_path`, `Edit`→`file_path`, `Glob`→`path`/`pattern`, `Grep`→`path`, `Bash` with detectable path, `Bash` without path → zero rows) [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `analytics.enabled` description under `### analytics` says "Enable per-tool byte tracking in `post_tool_use` hook." After ENH-1832 the same gate also controls `file_events` writes; description needs updating [Agent 2 finding]
- `config-schema.json` — `analytics.enabled` description string has the same incomplete text; update to mention file-event recording alongside byte tracking [Agent 2 finding]
- `hooks/adapters/codex/post-tool-use.sh` — inline comment (line 8) describes handler as persisting only byte metrics; update to mention `file_events` write [Agent 2 finding]
- `hooks/adapters/opencode/README.md` — intent table row for `tool.execute.after` names only byte metrics; update to reflect dual write [Agent 2 finding]

### Configuration
- `analytics.enabled` in `.ll/ll-config.json` — existing gate already controls this write

## Impact

- **Priority**: P4 — Enables richer context for skills (`refine-issue`, `confidence-check`) but not blocking any current workflows
- **Effort**: Small — Extends existing `post_tool_use` hook with one new write branch; `write_file_event()` follows the existing `write_tool_event()` pattern
- **Risk**: Low — Additive write gated on `analytics.enabled`; no changes to read paths or existing behavior
- **Breaking Change**: No

## Resolution

- Extended `post_tool_use.handle()` with a second `contextlib.suppress` block that extracts a file path per tool (`Read`/`Write`/`Edit` → `file_path`, `Glob` → `path`/`pattern`, `Grep` → `path`, `Bash` → regex extraction) and calls `session_store.write_file_event()`
- Added `write_file_event(db_path, session_id, path, op, issue_id, config=None)` to `session_store.py`; it INSERTs into `file_events` and calls `_index()` for FTS5 before committing
- Added helper functions: `_extract_file_path()`, `_normalize_path()`, `_detect_issue_id()`, `_BASH_PATH_RE`, `_ISSUE_ID_RE`
- Added 6 new tests in `TestFileEventsWrite`: per-tool parametrized path extraction (7 cases), bash-no-path zero-row case, issue-id extraction, null issue_id for plain path, FTS5 round-trip, analytics-disabled gate
- Updated `config-schema.json`, `docs/reference/CONFIGURATION.md`, `hooks/adapters/codex/post-tool-use.sh`, `hooks/adapters/opencode/README.md` to reflect dual write

## Status

**Done** | Completed: 2026-06-01 | Priority: P4

## Session Log
- `/ll:manage-issue` - 2026-06-01T05:23:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-06-01T05:12:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c75d9a1f-96fe-46f0-a149-329161e01f6c.jsonl`
- `/ll:confidence-check` - 2026-06-01T06:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7c73638-1dd9-4405-b0f3-9e427938de09.jsonl`
- `/ll:wire-issue` - 2026-06-01T05:09:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/080ad113-1a44-449a-a452-5a8ff905c5dc.jsonl`
- `/ll:refine-issue` - 2026-06-01T05:01:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e95db2d6-551c-48ea-abbd-e148791d8b78.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T04:19:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f60c9218-3661-4445-8adb-23f9182491a5.jsonl`
- `/ll:format-issue` - 2026-06-01T01:20:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c78d4399-dc58-4488-ac5a-557b6cd5e073.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `analytics.capture.file_events` gate is out of scope for this issue and owned by ENH-1835. Ship this issue with the existing `analytics.enabled` gate (consistent with `tool_events`). ENH-1835 will upgrade all write paths to the finer-grained `analytics.capture` sub-block. Design `write_file_event()` to accept an optional config argument so ENH-1835 can wire the gate without a method signature change. Related: ENH-1832 vs ENH-1835 (HIGH requirement conflict resolved by /ll:audit-issue-conflicts).
