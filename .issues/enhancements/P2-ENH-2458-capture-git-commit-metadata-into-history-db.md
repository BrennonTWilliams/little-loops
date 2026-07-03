---
id: ENH-2458
title: Capture git commit metadata into history.db as commit_events
type: ENH
priority: P2
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - git
  - captured
---

# ENH-2458: Capture git commit metadata into history.db as commit_events

## Summary

`.ll/history.db` (schema v14) tracks sessions, tool calls, file ops, issue lifecycle, loop events, corrections, messages, assistant messages, skill events, CLI events, and the FTS5 index — but no commit-level record exists. `file_events.git_sha` is a per-event column without a parent record, so "which commit closed which issue," "what files did this commit touch as a set," and "what was the message" cannot be queried from the DB. Add a `commit_events` table populated at commit time (via a `git commit` wrapper or `post-commit` hook) carrying `(ts, commit_sha, message, author, branch, issue_id, files_json)`; link `issue_id` by parsing the commit message (e.g. `Captured-By:` trailers and `Closes/Fixes #1234` references) and branch-name conventions. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #1: *"the single biggest blind spot — it's the ground truth for 'what actually shipped,' and nothing else in the DB captures it."*

## Motivation

Without commit-level rows, `file_events` carry a `git_sha` value that's a foreign key with no parent table. SQLite has no referential-integrity backstop, so the column is silently orphaned. The same blind spot affects:

- **Effort / velocity analysis** — `ll-history` cannot answer "how long did ENH-2458 take from open to first commit?" without manual `git log` walks.
- **Issue closure provenance** — `ll-issues set-status` writes `status: done` but doesn't record which commit the work landed in.
- **Audit/debug** — when an issue is reopened (per the `capture-issue` reopen path), there's no automated way to identify the regressing commit.
- **Cross-issue conflict detection** — `ll-deps` cannot detect "this commit's touched files overlap with these other commits' touched files" without a commit-level join.

The existing `file_events.git_sha` column was a sentinel for this gap; the actual table needs to exist.

## Current Behavior

- A `git commit` produces a `(sha, message, author, branch, file_list)` tuple that lives only in `git log` output.
- `file_events.git_sha` references commits by SHA but no `commit_events` table exists; the column is orphaned.
- `ll-history summary` and `ll-session search --fts` cannot filter by commit.
- No automated link from a `done` issue transition back to the commit that landed the fix.

## Expected Behavior

- `commit_events` table exists in schema v15+ with columns: `id`, `ts`, `commit_sha` (UNIQUE), `message`, `author`, `branch`, `issue_id` (nullable FK-like reference), `files_json` (list of touched paths), `parent_sha`.
- A `git commit` wrapper or `post-commit` hook writes a row at commit time with the SHA, message, author, branch, touched-file list, and an inferred `issue_id` from message parsing.
- `ll-session recent --kind commit` returns commit rows; `ll-session search --fts "<message fragment>" --kind commit` returns matches.
- `issue_id` column joins commit rows back to the issue lifecycle; `ll-issues show <id>` can surface "first landed in commit X at timestamp Y."
- `file_events.git_sha` is enriched: a backfill or runtime join can now resolve commit metadata.

## Proposed Solution

### Schema migration (append to `_MIGRATIONS` in `session_store.py`)

```sql
CREATE TABLE IF NOT EXISTS commit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    commit_sha TEXT NOT NULL UNIQUE,
    parent_sha TEXT,
    message TEXT NOT NULL,
    author TEXT,
    branch TEXT,
    issue_id TEXT,
    files_json TEXT  -- JSON array of touched paths
);
CREATE INDEX IF NOT EXISTS idx_commit_events_issue_id ON commit_events(issue_id);
CREATE INDEX IF NOT EXISTS idx_commit_events_branch ON commit_events(branch);
CREATE INDEX IF NOT EXISTS idx_commit_events_sha ON commit_events(commit_sha);
```

Bump `SCHEMA_VERSION` accordingly. Add `"commit"` to `_VALID_KINDS` and `"commit": "commit_events"` to `_KIND_TABLE` so `ll-session recent --kind commit` works.

### Producer wiring

- **Approach A (preferred)**: A `post-commit` hook registered via `git init.templateDir` or a `git config core.hooksPath` entry in the project — handler shell script invokes `git log -1 --format=...` and pipes into a small Python helper that calls a new `record_commit_event(db_path, sha, message, author, branch, issue_id, files)` in `session_store.py`.
- **Approach B (fallback)**: A wrapper inside the `ll-commit` skill (`skills/ll-commit/SKILL.md`) that records the event after `git commit` returns successfully. Simpler to wire but misses commits made outside the skill.

Recommended: Approach A (post-commit hook) covers all commit paths automatically.

### Issue-ID inference

Parse the commit message for:
- `Closes #<id>`, `Fixes #<id>`, `Resolves #<id>` — extract the integer.
- Conventional commit trailer like `Issue: ENH-2458` or `Captured-By:`.
- Branch-name convention: `feat/ENH-2458-*`, `fix/BUG-1234-*`.
- Fallback: `NULL`.

### Backfill (one-shot)

Add `_backfill_commit_events()` following the `_backfill_messages` pattern (`session_store.py:1218`): walk `git log --all --format=...` for the repo, dispatch to `record_commit_event()`, use `INSERT OR IGNORE` on the `commit_sha UNIQUE` constraint.

### Read API

Add `recent_commit_events(branch=None, issue_id=None, limit=20)` to `history_reader.py` (ENH-1752). Optional: `commits_touching_file(path)` returns commits that touched a given path by joining through `files_json`.

## Acceptance Criteria

- `commit_events` table exists in `.ll/history.db` after migration with `SCHEMA_VERSION` bumped.
- A `git commit` (anywhere in the project) writes a row to `commit_events` with the correct SHA, message, author, branch, touched-file list.
- `ll-session recent --kind commit` returns the row.
- `ll-session search --fts "<message fragment>" --kind commit` returns matching rows.
- An issue-ID-conventional branch produces a non-NULL `issue_id` on the row.
- `_backfill_commit_events` populates rows from `git log --all` without duplicating already-recorded commits.
- `history_reader.recent_commit_events(issue_id="ENH-2458")` returns the commit(s) that landed work on this issue.
- Documented in `docs/ARCHITECTURE.md` schema-versions table.

## Implementation Steps

1. Schema migration for `commit_events`; bump `SCHEMA_VERSION`.
2. Add `"commit"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_commit_event()` and `_backfill_commit_events()` in `session_store.py`.
4. Add `commit_events` to `__all__` in `session_store.py`.
5. Author `record-commit-post-commit` shell handler (under `hooks/scripts/`).
6. Wire shell handler via `git config core.hooksPath` if/when adopted (a project-level decision — document instead of forcing).
7. Add `recent_commit_events()` (and optional `commits_touching_file()`) to `history_reader.py`.
8. Add CLI: `ll-session search --fts ... --kind commit`, `ll-session recent --kind commit`.
9. Tests: `TestRecordCommitEvent`, `TestSchemaV15` (if first to bump), `TestBackfillCommitEvents`, hook-dispatch tests.
10. Docs: `docs/ARCHITECTURE.md` schema-version row, `docs/reference/API.md` for `record_commit_event`/`recent_commit_events`, `docs/reference/CLI.md` for the `--kind commit` flag.

## Sources

- `thoughts/history-db-expand-wiring.md` — original findings report, recommendations §2 row 1 ("Git commit metadata") and §3 ranked recommendation #1
- `scripts/little_loops/session_store.py:_MIGRATIONS` — schema migration pattern
- `scripts/little_loops/session_store.py:_backfill_messages` — template for `_backfill_commit_events()`
- `scripts/little_loops/history_reader.py` — read API to extend
- EPIC-1707 — closed parent epic; sets the graceful-degradation and `contextlib.suppress(Exception)` write-guard contract

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; producer/consumer flow |
| `docs/reference/API.md` | `session_store` module reference for `record_commit_event` |
| `docs/reference/CLI.md` | `ll-session` `--kind commit` flag documentation |
| `.claude/CLAUDE.md` | Git conventions (`feedback_no_claude_coauthor`) |

## Status

**Open** | Created: 2026-07-02 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
