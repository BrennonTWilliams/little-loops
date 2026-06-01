---
id: ENH-1834
type: ENH
priority: P5
status: done
discovered_date: 2026-06-01
captured_at: '2026-06-01T01:10:54Z'
discovered_by: capture-issue
relates_to:
- EPIC-1707
- ENH-1833
labels:
- enhancement
- captured
parent: EPIC-1707
confidence_score: 100
outcome_confidence: 73
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
---

# ENH-1834: Record `ll-` CLI command invocations in history.db

## Summary

When a user runs `ll-loop run`, `ll-auto`, `ll-parallel`, `ll-sprint`, or any other
`ll-` CLI tool, the invocation itself (binary name, args, start timestamp, exit code,
duration) is not persisted to `history.db`. Downstream events (loop state transitions,
issue lifecycle changes) are recorded, but the top-level CLI call that caused them is
not. This makes it impossible to correlate "how many times was `ll-loop run` invoked
this month" or "what was the exit code of the last `ll-sprint` run" from the DB.

## Current Behavior

CLI invocations are not recorded in `history.db`. When a user runs `ll-loop run`,
`ll-auto`, `ll-parallel`, `ll-sprint`, or any other `ll-` CLI tool, the top-level
invocation — binary name, args, start timestamp, exit code, duration — is silently
dropped. Only downstream events (loop state transitions, issue lifecycle changes) are
captured; the triggering CLI call that caused them is absent from the DB.

## Expected Behavior

Each `ll-` CLI invocation writes a row to a new `cli_events` table in `history.db`
containing: `ts`, `binary`, `args` (JSON array, truncated), `exit_code`, and
`duration_ms`. The `ll-session recent --kind cli` subcommand queries and returns
these rows.

## Motivation

CLI invocation history enables usage analytics and debugging. Combined with
`loop_events` and `issue_events`, it provides a complete audit trail: what was
invoked, what states it transitioned through, and what issues it affected.

## Scope Boundaries

- **In scope**: `ll-` CLI entry points, new `cli_events` table, `ll-session recent --kind cli` query support
- **Out of scope**: Skill and agent invocations (tracked separately in ENH-1833), hook events (ENH-1832), non-`ll-` tools, sub-process invocations within a CLI run

## Acceptance Criteria

- A new `cli_events` table records: `ts`, `binary`, `args` (JSON array, truncated),
  `exit_code`, `duration_ms`
- Each `ll-` CLI entry point writes a row at startup (with `exit_code=NULL`) and
  updates it on exit with the actual exit code and duration
- `ll-session recent --kind cli` returns the captured rows
- The write path is a thin wrapper around the existing CLI entry points — no
  changes to core logic required

## API/Interface

```python
@contextmanager
def cli_event_context(
    db_path: Path,
    binary: str,
    args: list[str],
    config: dict | None = None,  # reserved for ENH-1835 gating; ignored in this issue
) -> Generator[None, None, None]:
    """Insert cli_events row on enter; update exit_code and duration_ms on exit."""
```

The `config` parameter is accepted but unused — it exists for forward-compatibility so ENH-1835 can wire the analytics gate without a signature change (per `/ll:audit-issue-conflicts` scope note).

**Insert-then-update mechanics**: Use `cursor = conn.execute("INSERT INTO cli_events...")` → `row_id = cursor.lastrowid` → yield → `conn.execute("UPDATE cli_events SET exit_code=?, duration_ms=? WHERE id=?", (..., row_id))`. The `exit_code` defaults to `NULL` in the inserted row (for crash-abort visibility); the UPDATE runs in `finally` so it executes even on exception, passing `exit_code=1` in the except path.

**DB path in CLI entry points**: Most CLIs do not expose `--db`. Resolve using `DEFAULT_DB_PATH` from `session_store`: `db_path = Path.cwd() / DEFAULT_DB_PATH` (or simply pass `DEFAULT_DB_PATH` directly since `connect()` resolves relative to CWD). Mirror the pattern in `ctx_stats.py` which does explicit CWD resolution.

Table schema:

```sql
CREATE TABLE cli_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    binary TEXT NOT NULL,
    args TEXT NOT NULL,  -- JSON array, truncated to reasonable length
    exit_code INTEGER,
    duration_ms INTEGER
);
```

## Implementation Steps

1. **Migrate schema** in `scripts/little_loops/session_store.py`: append a new SQL string to `_MIGRATIONS` (currently 8 entries, 0-indexed; new entry becomes index 8) using `CREATE TABLE IF NOT EXISTS cli_events (...)` with the schema above; bump `SCHEMA_VERSION = 7` → `8`

2. **Extend kind routing** in `session_store.py:49–58`: add `"cli"` to `_VALID_KINDS` frozenset and `"cli": "cli_events"` to `_KIND_TABLE` dict so `recent(db, kind="cli")` resolves correctly

3. **Implement `cli_event_context()`** in `session_store.py`, after `record_skill_event()` at line 382: follow the `record_skill_event()` open-insert-commit-close shape for the INSERT on enter; use `cursor.lastrowid` to capture the inserted row ID; in the `finally` block compute `duration_ms = int((time.time() - start) * 1000)` (mirror `timed_phase()` at `issue_manager.py:72`) and run `UPDATE cli_events SET exit_code=?, duration_ms=? WHERE id=?`; default `exit_code=0`, catch `BaseException` in the body to pass `exit_code=1` before re-raising. Export in `session_store.__all__`.

4. **Update `ll-session` choices** in `scripts/little_loops/cli/session.py:68` and `:80`: add `"cli"` to both `choices=[...]` lists on the `recent` and `search` subparsers

5. **Wrap CLI entry points**: in each `main_*()` function, import `cli_event_context, DEFAULT_DB_PATH` from `session_store`, resolve `db_path = DEFAULT_DB_PATH` (or the value of `args.db` if the CLI exposes it), wrap the body with:
   ```python
   with cli_event_context(db_path, "ll-<name>", sys.argv[1:]):
       # existing body
       return <exit_code>
   ```
   There is no shared `cli_main()` wrapper — each entry point is wrapped individually. Capture `sys.argv[1:]` (not the full `sys.argv`) to exclude the binary name.

6. **Tests** in `scripts/tests/test_session_store.py`: add a `TestCliEventContext` class following `TestRecordSkillEvent` (line 1221) with:
   - `test_cli_event_roundtrip`: insert via context manager, assert row in `recent(db, kind="cli")`
   - `test_cli_event_exception_exit`: enter context, raise inside body, assert `exit_code=1` in DB
   - `test_cli_event_duration_accuracy`: assert `duration_ms >= 0` and is integer
   - `test_schema_v8_cli_events_table_exists`: mirror `TestSchemaV7` — bootstrap v7 schema, call `ensure_db()`, assert `SCHEMA_VERSION == 8` and `cli_events` in tables

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_session_store.py` → `TestSchemaV6.test_schema_version_is_seven`: change `assert SCHEMA_VERSION == 7` to `assert SCHEMA_VERSION == 8` (or remove the literal; the `assert int(row[0]) == SCHEMA_VERSION` line above it already covers the contract)
8. Update `scripts/tests/test_session_store.py` → `TestEnsureDb.test_all_tables_created`: add `"cli_events"` to the `for table in (...)` set alongside the other event tables
9. Update `scripts/tests/test_ll_session.py`: add `test_recent_subcommand_cli_accepted` to `TestArgumentParsing`; add `test_recent_cli_kind` and `test_recent_cli_empty` to `TestMainSession` — follow the exact pattern of the ENH-1833 equivalents (`test_recent_subcommand_skill_accepted`, `test_recent_skill_kind`, `test_recent_skill_empty`)
10. Update `docs/ARCHITECTURE.md`: add v8 row to schema versions table; update write-path mermaid and components table to include `cli_event_context()` and bump `v1–v7` labels to `v1–v8`
11. Update `docs/reference/API.md` and `docs/reference/CLI.md`: add `cli` to all `--kind` enumeration strings in the `ll-session` documentation sections
12. Update `scripts/little_loops/cli/session.py` module docstring (line 9) and `scripts/little_loops/session_store.py` `recent()` docstring to include `cli` (and fix pre-existing gaps `message`, `skill`)

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `cli_events` table migration, `cli_event_context()` context manager, `kind='cli'` in `_VALID_KINDS`/`_KIND_TABLE`
- `scripts/little_loops/cli/*.py` — wrap `main()` entry points with `cli_event_context`

### Dependent Files (Callers/Importers)

All 25 CLI entry points registered in `scripts/pyproject.toml` under `[project.scripts]` need wrapping. Each exposes a `main_<name>() -> int` function:

- `scripts/little_loops/cli/action.py` — `main_action()`
- `scripts/little_loops/cli/auto.py` — `main_auto()`
- `scripts/little_loops/cli/parallel.py` — `main_parallel()`
- `scripts/little_loops/cli/loop/__init__.py` — `main_loop()`
- `scripts/little_loops/cli/sprint/__init__.py` — `main_sprint()`
- `scripts/little_loops/cli/session.py` — `main_session()`
- `scripts/little_loops/cli/history.py` — `main_history()`
- `scripts/little_loops/cli/history_context.py` — `main_history_context()`
- `scripts/little_loops/cli/messages.py` — `main_messages()`
- `scripts/little_loops/cli/logs.py` — `main_logs()`
- `scripts/little_loops/cli/issues/__init__.py` — `main_issues()`
- `scripts/little_loops/cli/deps.py` — `main_deps()`
- `scripts/little_loops/cli/sync.py` — `main_sync()`
- `scripts/little_loops/cli/docs.py` — `main_check_links()`, `main_verify_docs()`, `main_verify_skill_budget()`
- `scripts/little_loops/cli/doctor.py` — `main_doctor()`
- `scripts/little_loops/cli/gitignore.py` — `main_gitignore()`
- `scripts/little_loops/cli/ctx_stats.py` — `main_ctx_stats()`
- `scripts/little_loops/cli/migrate.py` — `main_migrate()`
- `scripts/little_loops/cli/migrate_labels.py` — `main_migrate_labels()`
- `scripts/little_loops/cli/migrate_relationships.py` — `main_migrate_relationships()`
- `scripts/little_loops/cli/migrate_status.py` — `main_migrate_status()`
- `scripts/little_loops/cli/create_extension.py` — `main_create_extension()`
- `scripts/little_loops/cli/learning_tests.py` — `main_learning_tests()`
- `scripts/little_loops/cli/schemas.py` — `main_generate_schemas()`
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — `main_adapt_skills_for_codex()`
- `scripts/little_loops/cli/adapt_agents_for_codex.py` — `main_adapt_agents_for_codex()`
- `scripts/little_loops/cli/generate_skill_descriptions.py` — `main_generate_skill_descriptions()`

None of these functions call `sys.exit()` — they return `int` directly. The console_scripts machinery handles exit codes. Most do not accept or reference `db_path`; the context manager must resolve it via `DEFAULT_DB_PATH` imported from `session_store`.

### Similar Patterns
- `scripts/little_loops/session_store.py:382` — `record_skill_event()` (ENH-1833 predecessor) follows the open-insert-index-commit-close pattern; the new `cli_event_context()` INSERT on enter follows this exactly
- `scripts/little_loops/issue_manager.py:72` — `timed_phase()` is the closest existing `@contextmanager` using `time.time()` before yield and a `finally` block to compute elapsed — models the timing teardown for `cli_event_context()`
- `scripts/little_loops/file_utils.py:60` — `acquire_lock()` shows the `yield` inside `try/finally` inside a `with open(...)` block pattern for resource-lifetime contexts

### Tests
- `scripts/tests/test_session_store.py` — CLI event tests: normal exit, exception exit, duration accuracy
- `scripts/tests/test_session_store.py` → `TestSchemaV6.test_schema_version_is_seven` — **will break**: hard-codes `assert SCHEMA_VERSION == 7`; update assertion to `== 8` or drop the literal [Wiring pass added by `/ll:wire-issue`]
- `scripts/tests/test_session_store.py` → `TestEnsureDb.test_all_tables_created` — **will break**: expected table set does not include `"cli_events"`; add it [Wiring pass added by `/ll:wire-issue`]
- `scripts/tests/test_ll_session.py` — add `test_recent_subcommand_cli_accepted` to `TestArgumentParsing` (mirrors `test_recent_subcommand_skill_accepted` at line 58); add `test_recent_cli_kind` and `test_recent_cli_empty` to `TestMainSession` (mirrors `test_recent_skill_kind` / `test_recent_skill_empty` at lines 413–423) [Wiring pass added by `/ll:wire-issue`]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — `history.db schema versions` table ends at v7; add v8 row for `cli_events`; update `### Write Path` mermaid sequence label from `ensure_db() (v1–v7)` to `(v1–v8)` and add `cli_event_context()` producer note; update `### Components` table `ensure_db()` description from "v1–v7" to "v1–v8" and add `cli_event_context()` row
- `docs/reference/API.md` — `main_session()` `recent` subcommand kind enumeration reads `{tool,file,issue,loop,correction,message,skill}`; add `cli`
- `docs/reference/CLI.md` — `ll-session` section has two `--kind` flag description rows for `search` and `recent` subcommands; add `cli` to both `{...}` enumerations
- `scripts/little_loops/cli/session.py` — module-level docstring kind list (line 9) and `recent()` docstring are stale; add `cli` (and pre-existing gaps `message`, `skill`)
- `scripts/little_loops/session_store.py` — `recent()` docstring (line ~446) reads `(tool, file, issue, loop, correction)`; add `message`, `skill`, `cli`

### Configuration
- N/A

## Impact

- **Priority**: P5 — Usage analytics improvement; does not block any existing feature
- **Effort**: Small — Thin wrapper reusing existing `session_store.py` infrastructure
- **Risk**: Low — Additive write path only; no changes to core CLI logic required
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 73/100 → MODERATE

### Outcome Risk Factors
- **Broad enumeration across 27 sites without a completeness check**: All 27 CLI entry points are listed explicitly, but there is no verification grep (e.g., `grep -c "cli_event_context" scripts/little_loops/cli/*.py` vs. the registered console_scripts count) or automated test that asserts every registered entry point is wrapped. A missed wrapping would pass all tests silently.
- **Mitigation**: After wrapping all entry points, run a quick count: `grep -rl "cli_event_context" scripts/little_loops/cli/ | wc -l` and compare against `grep "ll-" scripts/pyproject.toml | wc -l`. Consider adding a `test_all_entry_points_wrapped` test in `TestCliEventContext` that introspects pyproject.toml.

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0686c0da-b3e0-4215-b978-6a0771cae829.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/90ff1d73-dbfe-4bdb-964a-84b3b2df9205.jsonl`
- `/ll:wire-issue` - 2026-06-01T12:02:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f11ecb7-7e09-429e-b3ad-966ac0288a36.jsonl`
- `/ll:refine-issue` - 2026-06-01T11:58:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a34339e-2d82-4143-857a-a0945994b101.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T04:19:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f60c9218-3661-4445-8adb-23f9182491a5.jsonl`
- `/ll:format-issue` - 2026-06-01T01:23:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ccce6dd-ca36-49fd-8bf7-a050f93f3840.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `analytics.capture.cli_commands` config gate is out of scope for this issue and owned by ENH-1835. This issue ships the `cli_event_context()` context manager as unconditional. Design `cli_event_context()` to accept an optional config argument so ENH-1835 can wire the gate without a method signature change. Related: ENH-1834 vs ENH-1835 (MEDIUM requirement conflict resolved by /ll:audit-issue-conflicts).

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-01
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1848: Core `cli_events` infrastructure in session_store.py
- ENH-1849: Wire `cli_event_context` into CLI entry points, tests, and docs

---

**Done** | Created: 2026-06-01 | Priority: P5
