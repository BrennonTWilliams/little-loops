---
id: ENH-1635
type: ENH
priority: P5
status: open
captured_at: "2026-05-23T19:10:14Z"
discovered_date: 2026-05-23
discovered_by: capture-issue
relates_to:
- FEAT-1112
- FEAT-324
labels:
- enhancement
- naming
- captured
---

# ENH-1635: Rename `.ll/session.db` to `.ll/history.db`

## Summary

Rename the per-project SQLite + FTS5 store created by FEAT-1112 from
`.ll/session.db` to `.ll/history.db`. The current name suggests the file
holds only the current/most-recent Claude Code session, when it actually
accumulates events from every session run inside the project indefinitely.

## Motivation

The "session" in `session.db` refers to the `session_id` *column* (which
ties each row back to the originating Claude Code session JSONL), not to
the file's scope. The file itself is an append-only, never-rotated index
of tool events, file modifications, issue transitions, loop runs, user
corrections, and messages across the project's lifetime. New users
reasonably read the filename as "current session state" and assume it
gets cleared between runs — which is wrong, and undersells what the
store actually enables (cross-session queries like "which loops failed
on issues touching file X?").

`history.db` matches how the data is actually used and reads naturally
alongside the existing `ll-history` CLI and the historical
`/ll:analyze-history` skill. FEAT-324 (`status: done`, superseded by
FEAT-1112) originally proposed exactly this name — `.ll/history.db` —
before the unified store landed under a different name.

## Current Behavior

- File path: `.ll/session.db` (plus `-shm`/`-wal` sidecars)
- `DEFAULT_DB_PATH = Path(".ll/session.db")` at
  `scripts/little_loops/session_store.py:38`
- `.gitignore:92-94` excludes `.ll/session.db*`
- Module name: `scripts/little_loops/session_store.py`
- CLI: `ll-session` (`search`, `recent`, `backfill` subcommands)
- Config key: `events.sqlite` (transport name, unrelated to filename)
- ~155 string occurrences of `session.db` / `session_store` /
  `SQLiteTransport` across `scripts/`, `docs/`, `commands/`, `skills/`,
  `README.md`, `CONTRIBUTING.md`, `.claude/CLAUDE.md`, `.gitignore`

## Expected Behavior

- File path: `.ll/history.db` (plus `-shm`/`-wal` sidecars)
- `DEFAULT_DB_PATH = Path(".ll/history.db")`
- `.gitignore` updated accordingly
- One-time migration on `ensure_db()`: if `.ll/session.db` exists and
  `.ll/history.db` does not, rename in place (with `-shm`/`-wal`).
- Docstrings and docs reflect the new name and clarify the scope
  ("per-project event history across all Claude Code sessions").

## Scope Decisions (proposed — open for review)

This rename has three concentric scopes; the issue ships **Scope A** by
default and defers B/C unless explicitly approved:

**Scope A — file path only (default, minimal blast radius):**
- Rename `.ll/session.db` → `.ll/history.db` on disk
- Update `DEFAULT_DB_PATH`, `.gitignore`, docstrings, user-facing docs
- Keep Python module name `session_store.py` (internal symbol)
- Keep CLI name `ll-session` (avoids collision with existing
  `ll-history`, which queries completed issues — different domain)
- Keep `events.sqlite` config key (already accurate — it's the
  transport implementation, not the filename)
- Add one-time auto-migration: `ensure_db()` renames old path if found

**Scope B — also rename module (optional):**
- `scripts/little_loops/session_store.py` → `history_store.py`
- Update all imports (~20 sites)

**Scope C — also rename CLI (NOT recommended without separate decision):**
- `ll-session` → ??? — `ll-history` is already taken by issue-history
  tooling. Would require either merging the two CLIs or picking a
  third name (e.g. `ll-events`, `ll-store`). Out of scope for this
  issue.

## Use Case

**Who**: A developer new to little-loops (or a returning user) inspecting
`.ll/` to understand persisted state.

**Context**: They see `session.db` and assume it's per-session scratch
state, possibly clearable between sessions. They don't realize it's the
project's permanent event index until they read the source or FEAT-1112.

**Goal**: The filename should communicate "long-lived history of this
project" at a glance.

**Outcome**: `.ll/history.db` is self-explanatory; pairs cleanly with the
existing `ll-history` mental model; no ambiguity about scope or
lifetime.

## Acceptance Criteria

- `DEFAULT_DB_PATH` is `Path(".ll/history.db")`
- `.gitignore` excludes `.ll/history.db*` (old `session.db*` entries
  removed)
- `ensure_db()` migrates an existing `.ll/session.db` (+ `-shm`, `-wal`)
  to the new path on first call after upgrade; logs at INFO level
- All user-facing docs (`docs/reference/CLI.md`,
  `docs/ARCHITECTURE.md`, `docs/reference/CONFIGURATION.md`, README,
  CONTRIBUTING, CLAUDE.md) reference `history.db`
- Module docstring at `session_store.py:1-22` updated
- Existing tests still pass; one new test covers the rename-migration
  branch (`test_session_store.py::test_migrates_legacy_session_db`)
- CHANGELOG entry under the next concrete release section (per
  feedback_changelog_no_unreleased)

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `DEFAULT_DB_PATH`, module docstring, `ensure_db()` migration shim
- `.gitignore` — replace `.ll/session.db*` entries with `.ll/history.db*`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/session_start.py` — calls `ensure_db()` on hook entry; must tolerate migration failure
- ~20 import sites of `session_store` symbols across `scripts/little_loops/` (grep `from little_loops.session_store` and `import session_store`)
- `scripts/little_loops/cli/ll_session.py` (and any other CLI entrypoints constructing the default path)

### Similar Patterns
- N/A — `.ll/session.db` is the only persistent SQLite store in the project; no other DB paths to keep consistent.

### Tests
- `scripts/tests/test_session_store.py` — add `test_migrates_legacy_session_db` covering the rename shim (`.db`, `-shm`, `-wal`); audit existing tests for hardcoded `session.db` strings (most use `tmp_path`)
- `scripts/tests/test_ll_session.py` — verify any path assertions reference the new default

### Documentation
- `docs/reference/CLI.md` — `ll-session` section and any path references
- `docs/ARCHITECTURE.md` — `SQLiteTransport` description, directory tree
- `docs/reference/CONFIGURATION.md` — `events.sqlite` example path
- `docs/reference/HOST_COMPATIBILITY.md` — state directory table
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — if it cites the path
- `README.md`, `CONTRIBUTING.md`, `.claude/CLAUDE.md` — top-level references

### Configuration
- N/A — config key `events.sqlite` (transport name) is intentionally unchanged per Scope A; only the on-disk filename changes.

## Implementation Steps

1. Update `DEFAULT_DB_PATH` and docstring in
   `scripts/little_loops/session_store.py`
2. Add migration shim to `ensure_db()`: if legacy path exists and new
   path does not, `Path.rename()` all three files (`.db`, `-shm`,
   `-wal`); log the rename
3. Update `.gitignore` (replace `.ll/session.db*` lines with
   `.ll/history.db*`)
4. Update all docs referencing `.ll/session.db`:
   - `docs/reference/CLI.md` (ll-session section)
   - `docs/ARCHITECTURE.md` (SQLiteTransport, directory tree)
   - `docs/reference/CONFIGURATION.md` (events.sqlite example)
   - `docs/reference/HOST_COMPATIBILITY.md` (state directory table)
   - `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` (if it cites the path)
   - `README.md`, `CONTRIBUTING.md`, `.claude/CLAUDE.md`
5. Update inline comments and string literals in tests that
   construct/assert on the path (`test_session_store.py`,
   `test_ll_session.py`, etc. — most use `tmp_path` fixtures so the
   filename doesn't matter, but a few may hardcode it)
6. Add `test_migrates_legacy_session_db` covering the migration shim
7. Update CHANGELOG entry under the next concrete release

## Risks / Notes

- **Migration must be best-effort**: `ensure_db()` is called from
  `session_start.py` hook; a failed rename must not crash the hook.
  Wrap in try/except, log, and fall through to creating a fresh
  `history.db` if the rename fails (the user keeps their old data
  under the old name and can recover manually).
- **`-shm` / `-wal` sidecars**: only present when the DB was opened in
  WAL mode and not cleanly closed. Migration should attempt all three
  but tolerate any subset being missing.
- **Naming tension with `ll-history` CLI**: `ll-history` operates on
  issue frontmatter; the new `history.db` is queried via `ll-session`.
  Scope A leaves this tension intact — call it out in
  `docs/reference/CLI.md` so users aren't surprised that two
  "history" concepts coexist. A future EPIC could consolidate them,
  but that's a much bigger decision than a filename.
- **No breaking change for existing users**: auto-migration on
  `ensure_db()` means upgrading just works.

## Impact

- **Priority**: P5 — Pure naming/clarity improvement; nothing is broken,
  no user is blocked, and the existing name is functional. Worth doing
  before the install base grows but not urgent.
- **Effort**: Small (Scope A) — One module change, one migration shim,
  ~10–15 doc/text edits, one new test.
- **Risk**: Low — Auto-migration preserves data; rollback is just
  reverting the path constant.
- **Breaking Change**: No (migration shim handles existing installs).

## References

- FEAT-1112: original implementation that named the file `session.db`
- FEAT-324: superseded predecessor that originally proposed
  `.ll/history.db` for completed issue + session indexing
- Discussion context: 2026-05-23 conversation reviewing FEAT-1112 scope,
  noting that "session.db" misleadingly suggests single-session scope
  when the file is actually a per-project, cross-session, append-only
  event history.

## Status

**Open** | Created: 2026-05-23 | Priority: P5

## Session Log
- `/ll:format-issue` - 2026-05-23T19:14:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0c42e29-d786-4417-87f6-edeb32ecf0f3.jsonl`
- `/ll:capture-issue` - 2026-05-23T19:10:14Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/<current>.jsonl`
