# FEAT-1112: Unified Session Store (SQLite + FTS5) — Implementation Plan

**Issue**: `.issues/features/P4-FEAT-1112-unified-session-sqlite-fts5-store.md`
**Date**: 2026-05-22
**Action**: implement (via `/ll:manage-issue features fix FEAT-1112`)

## Scope decision

The issue specifies 19 steps. Steps 12, 13, 15–18 were already carved into
ENH-1619 (mechanical docs/help/allow-list wiring). This plan implements the
**functional core + functional wiring + tests** (Steps 1–5, 7–11, 14, 19-functional).

**Adapted scope — Step 6 (migrate analyze-* skills to query the DB):** deferred.
The specified `tool_events` / `issue_events` schemas do not carry enough fields
to reconstruct what `scan_completed_issues()` (rich `IssueInfo`) and
`analyze_workflows()` (user message text + pattern YAML) consume. Migrating
those two CLIs to be DB-backed would require either a much wider schema or a
rewrite of their analysis logic on top of SQL — a regression risk for two
working CLIs that is out of proportion to a P4 additive feature. The DB query
surface itself (`ll-session search` / `recent`) ships and is the foundation a
follow-up migration issue can build on. Recommend a follow-up ENH, mirroring
the ENH-1619 carve-out precedent.

## What was implemented

### New module: `scripts/little_loops/session_store.py`
- SQLite schema (migration 0): `tool_events`, `file_events`, `issue_events`,
  `loop_events`, `user_corrections`, FTS5 `search_index`, `meta`.
- `tool_events` reserves `bytes_in`/`bytes_out`/`cache_hit` for FEAT-1160.
- Migration framework: ordered `_MIGRATIONS` list keyed by `meta.schema_version`;
  `_apply_migrations()` applies only pending entries (idempotent).
- `ensure_db()` bootstrap, `connect()` (Row factory).
- `SQLiteTransport` — EventBus `Transport` sink; records recognised FSM events
  to `loop_events`; `check_same_thread=False` + lock; fully best-effort (DB
  errors logged and swallowed) so the 4 `wire_transports` callers cannot break.
- `search()` (FTS5 + `bm25()` ranking, anchors), `recent(kind)`.
- `backfill()` — seeds from `.issues/**` frontmatter, `.loops/.running` +
  `.loops/.history` state JSON, and session JSONL tool-use blocks.

### New CLI: `scripts/little_loops/cli/session.py`
- `ll-session search --fts`, `recent --kind`, `backfill`; `--db` override.
- Modeled on `cli/logs.py` (`_build_parser` / `_parse_args` / `main_session`).

### Functional wiring
- `transport.py`: `"sqlite"` in `_TRANSPORT_REGISTRY`, `wire_transports` branch,
  module docstring.
- `__init__.py`: `SQLiteTransport` re-export + `__all__`.
- `cli/__init__.py`: `main_session` import + `__all__` + docstring.
- `config/features.py`: `SqliteEventsConfig` + `EventsConfig.sqlite` field.
- `config-schema.json`: `events.sqlite` property block.
- `pyproject.toml`: `ll-session` entry point.
- `hooks/session_start.py`: best-effort `ensure_db()` bootstrap for initialized
  projects only (no-op when no config — never creates a stray `.ll/`).
- `.gitignore`: `.ll/session.db` (+ `-shm`/`-wal`).

### Tests
- `test_session_store.py` (24 tests), `test_ll_session.py` (12 tests),
  `test_transport.py::test_sqlite_registered_by_name`,
  `test_config_schema.py` `events.sqlite` assertions.

## Verification
- New + affected suites green (`test_session_store`, `test_ll_session`,
  `test_transport`, `test_config_schema`, `test_cli`, `test_feat1504_doc_wiring`,
  `test_hook_intents`, `test_hook_session_start`).
- `ruff check` / `ruff format` / `mypy` clean on new modules.

## Follow-up
- New ENH: migrate `main_history()` and `analyze_workflows()` to query the
  session DB (Step 6), once a richer schema or backfill content is in place.
