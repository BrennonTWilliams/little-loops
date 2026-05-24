---
id: ENH-1635
type: ENH
priority: P5
status: done
captured_at: '2026-05-23T19:10:14Z'
completed_at: '2026-05-24T00:01:04Z'
discovered_date: 2026-05-23
discovered_by: capture-issue
relates_to:
- FEAT-1112
- FEAT-324
labels:
- enhancement
- naming
- captured
confidence_score: 95
outcome_confidence: 73
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
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

### Files to Modify (Hardcoded `"session.db"` Literals)

These sites all hardcode the filename and must change. Three of them **bypass `DEFAULT_DB_PATH`**, so flipping the constant alone is insufficient.

- `scripts/little_loops/session_store.py:38` — `DEFAULT_DB_PATH = Path(".ll/session.db")`; module docstring (lines 1–22); add migration shim inside `ensure_db()` at line 173
- `scripts/little_loops/transport.py:626` — `bus.add_transport(SQLiteTransport(base / "session.db"))` — **bypasses `DEFAULT_DB_PATH` and `config.sqlite.path`** (see Risks)
- `scripts/little_loops/hooks/session_start.py:114` — `ensure_db(cwd / ".ll" / "session.db")` — bypasses `DEFAULT_DB_PATH`
- `scripts/little_loops/hooks/post_tool_use.py:62` — `connect(cwd / ".ll" / "session.db")` — bypasses `DEFAULT_DB_PATH`
- `scripts/little_loops/cli/ctx_stats.py:27` — `DEFAULT_DB_RELPATH = Path(".ll") / "session.db"` — local constant, **not** imported from `session_store`; also error-message strings (lines 143, 146, 154)
- `scripts/little_loops/config/features.py:464,470` — `SqliteEventsConfig.path` default literal `".ll/session.db"` (loaded into config but ignored by `wire_transports` — see Risks)
- `config-schema.json:1178,1182,1205` — `events.sqlite.path` JSON Schema default
- `.gitignore:92-94` — replace `.ll/session.db`, `.ll/session.db-shm`, `.ll/session.db-wal` with `.ll/history.db*`

### Dependent Files (Use `DEFAULT_DB_PATH` — auto-benefit from the constant change)

- `scripts/little_loops/cli/session.py:20,39` — imports `DEFAULT_DB_PATH`; argparse default + help text needs the new filename in description strings
- `scripts/little_loops/cli/history.py:35,205` — imports `DEFAULT_DB_PATH`; `db_path = project_root / DEFAULT_DB_PATH`
- `scripts/little_loops/__init__.py:43` — re-exports `SQLiteTransport` (no path string)
- 16 modules total import from `session_store`; the rest use `connect()` / `ensure_db()` / `backfill()` without hardcoding paths

### Host Adapter Files (Documentation/Comments)

- `hooks/adapters/opencode/index.ts:76` — comment referencing `.ll/session.db` byte-metrics destination
- `hooks/adapters/opencode/README.md:42,50` — `tool.execute.after` hook docs
- `hooks/adapters/codex/post-tool-use.sh:9` — shell comment about cache-metrics persistence

### Similar Patterns (from pattern-finder)

- **Migration shim location**: this codebase has two established patterns:
  - In-process silent fallback (read-only): `issue_history/parsing.py:334`, `issue_parser.py:139-144`, `fsm/persistence.py:685` — `if legacy.exists(): read_it()` with no rename, no logging
  - User-invoked CLI migration: `cli/migrate_status.py`, `cli/migrate.py`, `cli/migrate_relationships.py`, `cli/migrate_labels.py` — `--dry-run` + `--config` flags, `print()` results, return exit code
  - **Recommendation**: ENH-1635's choice (in-process rename inside `ensure_db()`) is a *third* pattern — first time the codebase performs a transparent write-side migration. Use `Path.rename()` (the codebase's rename primitive — `shutil.move` only appears in `merge_coordinator.py:1009` for worktree backups).
- **Logging**: `session_store.py:36` already declares `logger = logging.getLogger(__name__)`; existing calls use `%`-style format strings with `exc_info=True` (lines 293, 337). Match this style for the rename log: `logger.info("session_store: migrated %s -> %s", legacy, new)` on success, `logger.warning("session_store: legacy rename failed for %s; continuing with fresh db", legacy, exc_info=True)` on failure.

### Tests

- `scripts/tests/test_session_store.py` — add `test_migrates_legacy_session_db` covering rename of `.db` + `-shm` + `-wal`; follow `TestEnsureDb` shape (lines 21–67, pass explicit `tmp_path / ".ll" / "history.db"` to `ensure_db()`; pre-populate `tmp_path / ".ll" / "session.db"` to set up the legacy precondition; no `monkeypatch` on `DEFAULT_DB_PATH`). `test_v1_db_upgrades_to_v2_idempotently` (line 315) is the closest template for "construct legacy artifact → call function → assert"
- `scripts/tests/test_session_store.py` — has **34 occurrences** of `session.db` in path construction, almost all `tmp_path / "session.db"`; audit for the few that might assert on the literal name
- `scripts/tests/test_cli_ctx_stats.py` — 7 occurrences; lines 108, 127, 139, 165, 202, 219, 238 assert on `DEFAULT_DB_RELPATH` handling
- `scripts/tests/test_ll_session.py` — 7 occurrences; verify path defaults
- `scripts/tests/test_hook_post_tool_use.py` — 7 occurrences; lines 111–112, 145, 158, 171, 222 assert on `.ll/session.db` creation
- `scripts/tests/test_config_schema.py:240` — `assert sqlite_block["properties"]["path"]["default"] == ".ll/session.db"` — must flip to `.ll/history.db`
- `scripts/tests/test_transport.py:254` — `assert (tmp_path / "session.db").exists()` — flip to `history.db`
- `scripts/tests/test_issue_history_parsing.py`, `test_issue_history_cli.py`, `test_workflow_sequence_analyzer.py` — backfill-related path strings (low impact)
- `scripts/tests/test_hook_intents.py:345` — **hard-breaking** assertion (`assert not (tmp_path / ".ll" / "session.db").exists()`); must flip to `history.db` alongside `test_hook_post_tool_use.py` (previously underclassified as "low impact")

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_session_start.py` — covers `hooks/session_start.py` (changed at line 114); not in integration map; add `TestSessionStartDbMigration.test_migrates_legacy_session_db` using the `in_tmp` fixture (chdir into `tmp_path`): place `.ll/session.db`, call `handle(_event())`, assert `.ll/history.db` exists and `.ll/session.db` does not; follow the `TestSessionStartContextStateCleanup` class pattern

### Documentation (29 occurrences across 9 docs)

- `docs/reference/CLI.md` — 6 occurrences in `ll-session` (line 1247+), `ll-ctx-stats` (lines 143, 146, 154), `ll-history summary` (line 1018)
- `docs/reference/CONFIGURATION.md` — 5 occurrences: default path (line 879), example (line 888), scope description (line 418), `SQLiteTransport` description (line 790)
- `docs/reference/API.md` — 4 occurrences: `ll-session` (lines 3378, 3383), `ll-ctx-stats` (lines 3415, 3420)
- `docs/reference/HOST_COMPATIBILITY.md` — 2 occurrences: state-directory table (line 179), context note (line 39)
- `docs/ARCHITECTURE.md` — 1 occurrence: `SQLiteTransport` section
- `CHANGELOG.md:19` — release note under FEAT-1112 (historical — leave intact; add new entry per `feedback_changelog_no_unreleased`)
- `README.md`, `CONTRIBUTING.md`, `.claude/CLAUDE.md:116,136` — top-level references

### Configuration

- `config-schema.json:1176-1187` — `events.sqlite.path` default.

### CLI Help Strings (user-visible, not covered by DEFAULT_DB_PATH auto-update)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py:4,41` — module docstring (`"search and inspect the per-project \`.ll/session.db\`"`) and argparse `--help` string (`"Path to the session database (default: .ll/session.db)"`); neither is fixed by the `DEFAULT_DB_PATH` constant change; both are user-visible via `ll-session --help`
- `scripts/little_loops/cli/ctx_stats.py:52,263,286,300` — additional user-visible path strings beyond lines 143,146,154 already in Implementation Step 4: argparse `--db` help string (line 52), `main_ctx_stats` docstring (line 263), runtime `logger.warning` message (line 286, visible when DB is absent), and `logger.error` message (line 300) **Note**: the schema default and the `SqliteEventsConfig.path` dataclass field are both loaded but **never consumed** by `wire_transports` (see Risks). Renaming the default still surfaces correctly in generated docs/schemas, but does not affect runtime path selection.

### Verified Issue Claims

- "~155 string occurrences": **confirmed** 163+ across 47 files (count includes issue/planning markdown files the original count likely excluded)
- "~20 import sites": **confirmed** 16 files with imports, 20 distinct import statements
- "Only persistent SQLite store": **confirmed** — no other `.db` paths to keep consistent

## Implementation Steps

1. **Core constant + docstring** — `scripts/little_loops/session_store.py`:
   - Line 38: `DEFAULT_DB_PATH = Path(".ll/history.db")`
   - Lines 1–22: update module docstring to say `history.db` and clarify "per-project event history across all Claude Code sessions"
2. **Migration shim** — insert at the top of `ensure_db()` (line 173, before `db_path.parent.mkdir(...)`):
   ```python
   db_path = Path(path)
   legacy = db_path.parent / "session.db"
   if legacy.exists() and not db_path.exists():
       for suffix in ("", "-shm", "-wal"):
           src = legacy.parent / f"session.db{suffix}"
           if src.exists():
               try:
                   src.rename(db_path.parent / f"history.db{suffix}")
                   logger.info("session_store: migrated %s -> %s", src, db_path.parent / f"history.db{suffix}")
               except OSError:
                   logger.warning(
                       "session_store: legacy rename failed for %s; continuing with fresh db",
                       src, exc_info=True,
                   )
                   break
   ```
   Matches existing logging style at `session_store.py:36,293,337` (module-level `logger`, `%`-format strings, `exc_info=True`).
3. **Update hardcoded literals that bypass `DEFAULT_DB_PATH`** (3 sites):
   - `transport.py:626` — `SQLiteTransport(base / "history.db")`
   - `hooks/session_start.py:114` — `ensure_db(cwd / ".ll" / "history.db")`
   - `hooks/post_tool_use.py:62` — `connect(cwd / ".ll" / "history.db")`
4. **Update remaining hardcoded literals**:
   - `cli/ctx_stats.py:27` — `DEFAULT_DB_RELPATH = Path(".ll") / "history.db"`; update error-message strings (lines 143, 146, 154)
   - `config/features.py:464,470` — `SqliteEventsConfig.path` default → `".ll/history.db"`
   - `config-schema.json:1178,1182,1205` — JSON Schema default
5. **`.gitignore`** — replace lines 92–94 (`.ll/session.db*` trio) with `.ll/history.db`, `.ll/history.db-shm`, `.ll/history.db-wal`
6. **Update docs** (29 occurrences across 9 files — see Integration Map for line numbers):
   - `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/API.md`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/ARCHITECTURE.md`
   - `README.md`, `CONTRIBUTING.md`, `.claude/CLAUDE.md:116,136`
   - `hooks/adapters/opencode/index.ts:76`, `hooks/adapters/opencode/README.md:42,50`, `hooks/adapters/codex/post-tool-use.sh:9` (comments only)
7. **Update test fixtures**:
   - `test_config_schema.py:240` — flip literal `".ll/session.db"` → `".ll/history.db"`
   - `test_transport.py:254` — flip `(tmp_path / "session.db")` → `(tmp_path / "history.db")`
   - Audit `test_session_store.py` (34 occurrences), `test_cli_ctx_stats.py` (7), `test_ll_session.py` (7), `test_hook_post_tool_use.py` (7) for any `tmp_path / "session.db"` assertions that must reflect the new default; most are arbitrary tmp names and can stay as `session.db` if the test isn't asserting on the *default* path
8. **New test** — `test_session_store.py::test_migrates_legacy_session_db` following `TestEnsureDb` shape (lines 21–67):
   ```python
   def test_migrates_legacy_session_db(self, tmp_path: Path) -> None:
       ll_dir = tmp_path / ".ll"
       ll_dir.mkdir()
       legacy = ll_dir / "session.db"
       legacy.write_bytes(b"")  # any pre-existing file triggers rename
       (ll_dir / "session.db-wal").write_bytes(b"wal-data")
       new = ll_dir / "history.db"
       ensure_db(new)
       assert new.exists()
       assert not legacy.exists()
       assert (ll_dir / "history.db-wal").read_bytes() == b"wal-data"
   ```
9. **CHANGELOG** — add entry under the next concrete release section (per `feedback_changelog_no_unreleased`), not `[Unreleased]`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/little_loops/cli/session.py:4,41` — module docstring and argparse `--help` string both embed `.ll/session.db`; update to `history.db`
11. Update `scripts/little_loops/cli/ctx_stats.py:52,263,286,300` — additional path strings not covered by Step 4 (lines 143,146,154): argparse `--db` help (line 52), `main_ctx_stats` docstring (line 263), `logger.warning` message (line 286), `logger.error` message (line 300)
12. Add `test_hook_session_start.py::TestSessionStartDbMigration.test_migrates_legacy_session_db` — use `in_tmp` fixture (chdir to `tmp_path`), ensure `.ll/session.db` exists, call `handle(_event())`, assert `.ll/history.db` exists and `.ll/session.db` does not; follow `TestSessionStartContextStateCleanup` class pattern
13. Correct Step 7 audit for `test_hook_intents.py:345` — this is a hard-breaking path assertion (`assert not (tmp_path / ".ll" / "session.db").exists()`); update to `history.db` alongside `test_hook_post_tool_use.py`

## Risks / Notes

- **Migration must be best-effort**: `ensure_db()` is called from `session_start.py:107-114` which **already wraps the entire call in `contextlib.suppress(Exception)`**. Any exception from the rename is therefore silenced at the hook layer — the shim still needs its own `try/except` around `Path.rename()` so that (a) a `-wal` rename failure doesn't abort the whole migration and (b) the failure is *logged* with `exc_info=True` for diagnostic visibility (the suppressed-at-hook path is silent).
- **`events.sqlite.path` config key is dead code in the transport path**: `transport.py:626` constructs `SQLiteTransport(base / "session.db")` directly, ignoring `SqliteEventsConfig.path` loaded at `config/features.py:464,470`. This means flipping only `DEFAULT_DB_PATH` is insufficient — the hardcoded literals at `transport.py:626`, `hooks/session_start.py:114`, `hooks/post_tool_use.py:62`, and `cli/ctx_stats.py:27` must all be updated (see Implementation Steps 3–4). A separate enhancement could wire `config.sqlite.path` through to `wire_transports` so the config key becomes meaningful; out of scope here.
- **`-shm` / `-wal` sidecars rarely exist in practice**: no `PRAGMA journal_mode=WAL` is set anywhere in the Python code (verified via grep on `WAL`, `journal_mode`, `PRAGMA`). SQLite's default is DELETE journaling, which uses a `-journal` file only during transactions and removes it on commit. The `-shm`/`-wal` files only appear if an external tool (e.g., `sqlite3` CLI with `.open --wal`) put the DB into WAL mode. Migration should still attempt the rename to be safe, but tolerating absence is the common case, not the edge case.
- **Naming tension with `ll-history` CLI**: `ll-history` operates on issue frontmatter; the new `history.db` is queried via `ll-session`. Scope A leaves this tension intact — call it out in `docs/reference/CLI.md` so users aren't surprised that two "history" concepts coexist. A future EPIC could consolidate them, but that's a much bigger decision than a filename.
- **No breaking change for existing users**: auto-migration on `ensure_db()` means upgrading just works. The shim is idempotent — second invocation finds the new file already in place and skips.
- **Novel migration pattern for this codebase**: existing in-process migrations (`issue_history/parsing.py:334`, `issue_parser.py:139-144`, `fsm/persistence.py:685`) are *read-only fallbacks* that don't move files. Existing rename-style migrations are explicit user-invoked CLIs (`ll-migrate-*`). This issue introduces the codebase's first transparent write-side rename. Worth noting in the PR description so reviewers know the pattern is intentional, not an oversight.

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

**Done** | Created: 2026-05-23 | Completed: 2026-05-24 | Priority: P5

## Resolution

Implemented per the Integration Map and Implementation Steps. Summary:

- `DEFAULT_DB_PATH` is now `Path(".ll/history.db")` (`session_store.py:38`)
- `ensure_db()` performs a one-time transparent rename of legacy
  `session.db` (and `-shm`/`-wal` sidecars) to `history.db`, with
  per-suffix `try/except` and INFO/WARNING logging
- All three bypass sites updated: `transport.py:626`, `hooks/session_start.py:114`, `hooks/post_tool_use.py:62`
- `cli/ctx_stats.py` constant + user-visible strings updated; `config/features.py` `SqliteEventsConfig.path` default flipped; `config-schema.json` defaults flipped; `.gitignore` swapped
- CLI help text on `ll-session` and `ll-ctx-stats` updated
- Documentation updated across `docs/reference/{CLI,CONFIGURATION,API,HOST_COMPATIBILITY}.md`, `docs/ARCHITECTURE.md`, `.claude/CLAUDE.md`, host-adapter comments
- New tests: `TestEnsureDb::test_migrates_legacy_session_db`,
  `TestEnsureDb::test_migration_skipped_when_new_db_exists`,
  `TestSessionStartDbMigration::test_migrates_legacy_session_db`
- Existing tests updated: `test_config_schema.py:240`,
  `test_transport.py:254`, `test_hook_intents.py:345`,
  `test_hook_post_tool_use.py` (5 default-path asserts),
  `test_cli_ctx_stats.py` (default-path setups), `test_issue_history_cli.py:165`
- CHANGELOG entry added under `[1.106.0] - 2026-05-23` (per
  `feedback_changelog_no_unreleased`, not under `[Unreleased]`)

233 tests pass across all touched test modules; ruff clean. Verification grep
confirms no residual `session.db` references outside intentional sites
(migration shim, arbitrary `tmp_path / "session.db"` test names, generated
`.pyc`/`.hypothesis`/`htmlcov` artifacts, and the historical
CHANGELOG:19 FEAT-1112 release note).

## Session Log
- `/ll:manage-issue` - 2026-05-24T00:01:04Z - implementation + verification

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-23_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 73/100 → MODERATE

### Outcome Risk Factors
- **Wide enumeration across 30+ sites without a verification sweep** — Integration Map enumerates every file but specifies no post-implementation check. Add a final step: `grep -rn 'session\.db' scripts/ hooks/ docs/ .gitignore README.md CONTRIBUTING.md | grep -v '\.issues/'` should return zero hits; any remainder is a miss. This closes the gap that cost 15 points in Criterion D.
- **Novel migration pattern** — `ensure_db()` is the codebase's first transparent write-side rename. Existing in-process migrations are read-only fallbacks; rename-style migrations are user-invoked CLIs. Call this out explicitly in the PR description so reviewers understand it's intentional.

## Session Log
- `/ll:confidence-check` - 2026-05-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/254f6dbe-67d6-4708-98a6-e02c9e7c7d23.jsonl`
- `/ll:wire-issue` - 2026-05-23T23:36:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b6b8c22-4624-47e4-a6df-c62189c87ec3.jsonl`
- `/ll:refine-issue` - 2026-05-23T23:27:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/879ef0aa-ab10-4b20-a07d-bc946499c21d.jsonl`
- `/ll:format-issue` - 2026-05-23T19:14:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0c42e29-d786-4417-87f6-edeb32ecf0f3.jsonl`
- `/ll:capture-issue` - 2026-05-23T19:10:14Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/<current>.jsonl`
