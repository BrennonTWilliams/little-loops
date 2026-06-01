---
id: ENH-1849
type: ENH
priority: P5
status: open
parent: ENH-1834
relates_to:
- EPIC-1707
- ENH-1834
- ENH-1848
labels:
- enhancement
size: Large
---

# ENH-1849: Wire `cli_event_context` into CLI entry points, tests, and docs

## Summary

Decomposed from ENH-1834: Record `ll-` CLI command invocations in history.db.

Applies the `cli_event_context()` context manager (introduced in ENH-1848) across all 27 `ll-` CLI entry points, adds `"cli"` to `ll-session` subparser choices, wires integration tests in `test_ll_session.py`, and updates all documentation. **Depends on ENH-1848 merging first.**

## Parent Issue

Decomposed from ENH-1834: Record `ll-` CLI command invocations in history.db

## Acceptance Criteria

- All 27 CLI entry points registered in `scripts/pyproject.toml` are wrapped with `cli_event_context`
- `ll-session recent --kind cli` accepted by argparser and returns captured rows
- Integration tests in `test_ll_session.py` pass
- `docs/ARCHITECTURE.md`, `docs/reference/API.md`, `docs/reference/CLI.md`, and docstrings updated
- Completeness check: `grep -rl "cli_event_context" scripts/little_loops/cli/ | wc -l` matches `grep "ll-" scripts/pyproject.toml | wc -l`

## Implementation Steps

4. **Update `ll-session` choices** in `scripts/little_loops/cli/session.py:68` and `:80`: add `"cli"` to both `choices=[...]` lists on the `recent` and `search` subparsers

5. **Wrap CLI entry points**: in each `main_*()` function below, import `cli_event_context, DEFAULT_DB_PATH` from `session_store`, resolve `db_path = DEFAULT_DB_PATH`, wrap the body with:
   ```python
   with cli_event_context(db_path, "ll-<name>", sys.argv[1:]):
       # existing body
       return <exit_code>
   ```
   Capture `sys.argv[1:]` (not full `sys.argv`) to exclude the binary name.

   Entry points to wrap (all return `int` via `main_<name>()`; none call `sys.exit()`):
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

9. **Update `scripts/tests/test_ll_session.py`**: add `test_recent_subcommand_cli_accepted` to `TestArgumentParsing` (mirrors `test_recent_subcommand_skill_accepted` at line 58); add `test_recent_cli_kind` and `test_recent_cli_empty` to `TestMainSession` (mirrors `test_recent_skill_kind` / `test_recent_skill_empty` at lines 413–423)

10. **Update `docs/ARCHITECTURE.md`**: add v8 row to schema versions table; update `### Write Path` mermaid sequence label from `ensure_db() (v1–v7)` to `(v1–v8)` and add `cli_event_context()` producer note; update `### Components` table `ensure_db()` description from "v1–v7" to "v1–v8" and add `cli_event_context()` row

11. **Update `docs/reference/API.md` and `docs/reference/CLI.md`**: add `cli` to all `--kind` enumeration strings in the `ll-session` documentation sections (`{tool,file,issue,loop,correction,message,skill}` → add `cli`)

12. **Update docstrings**: `scripts/little_loops/cli/session.py` module-level docstring (line 9) and `recent()` docstring — add `cli` (and pre-existing gaps `message`, `skill`); `scripts/little_loops/session_store.py` `recent()` docstring (line ~446) — add `message`, `skill`, `cli`

## Completeness Verification

After wrapping all entry points, run:
```bash
grep -rl "cli_event_context" scripts/little_loops/cli/ | wc -l
grep "ll-" scripts/pyproject.toml | wc -l
```
The counts should match (allowing for `docs.py` having 3 mains in 1 file). Consider adding a `test_all_entry_points_wrapped` test in `TestCliEventContext` that introspects `pyproject.toml`.

## Impact

- **Priority**: P5
- **Effort**: Medium — mechanical but broad (27 entry points + tests + docs)
- **Risk**: Low — additive wiring only; wrapping is thin and non-invasive
- **Breaking Change**: No

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0686c0da-b3e0-4215-b978-6a0771cae829.jsonl`

---

**Open** | Created: 2026-06-01 | Priority: P5
