---
id: FEAT-3524
type: FEAT
title: Pluggable storage backend for history.db with remote database support
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-22'
captured_at: '2026-09-22T15:39:38Z'
---

# FEAT-3524: Pluggable storage backend for history.db with remote database support

## Summary

Allow little-loops users to point `history.db` at a remote database (e.g. Postgres, MySQL, or a networked/hosted SQLite such as Turso/libSQL) via a pluggable storage backend configured under `history.*` in `.ll/ll-config.json`, instead of only the local in-repo `.ll/history.db` file.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

Teams running little-loops across several machines or CI runners (e.g. the self-hosted runner) have no way to share one history/analytics store. A remote backend enables cross-machine `ll-history` / `ll-logs` analytics, session digests, and compaction context without syncing `.db` files, and unblocks hosted dashboards reading the same store.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Current State

- `history.db_path` (config-schema.json, `history` block) only overrides the **local filesystem path** of `history.db`; relative paths resolve against the project root and the `LL_HISTORY_DB` env var takes precedence (ENH-2623). Resolution lives in `little_loops.session_store.db._resolve_db_path` / `resolve_history_db`.
- The storage layer is hardcoded to `sqlite3`. `little_loops.session_store.schema.ensure_db` opens `sqlite3.connect(str(db_path))` and applies `_configure_connection` (busy_timeout, `PRAGMA journal_mode = WAL`) plus `_apply_migrations`.
- `sqlite3.connect(` appears at roughly 28 call sites across ~15 modules (session_store/{schema,sessions,queries,lifecycle,writers}.py, history_reader/_base.py, issue_history/*, cli/{history,logs,doctor,doctor_trim,ctx_stats}.py, queue_store.py, codegraph.py). Many use `file:{path}?mode=ro` URI connections, PRAGMAs, and FTS5 — SQLite-specific features.
- `history.workspace_manifest_path` (FEAT-3409) aggregates **multiple local** `history.db` files across repos declared in a workspace manifest; it is not a live remote connection.

## Proposed Design

1. Introduce a `history.backend` config block, e.g.:
   ```json
   "history": {
     "backend": { "kind": "sqlite" | "postgres" | "libsql", "url": "postgresql://..." , "url_env": "LL_HISTORY_URL" }
   }
   ```
   Default `kind: sqlite` preserves current behavior (`db_path` / `LL_HISTORY_DB` unchanged). Secrets should come from an env var reference, never inline in the committed config.
2. Add a backend abstraction (`little_loops.session_store.backend`) exposing `connect()` / `connect_readonly()` / `ensure_schema()` and a small dialect shim, and route all session_store connection sites through it (`resolve_host()`-style single chokepoint, mirroring the host CLI abstraction rule).
3. Keep SQLite-only features (FTS5 search, WAL PRAGMAs, `VACUUM`) behind capability flags on the backend; degrade gracefully (e.g. `ll-session search --fts` reports "not supported by backend") rather than crashing.
4. Migrations: reuse `_apply_migrations` with per-dialect DDL where SQLite syntax diverges (AUTOINCREMENT, `json_extract`, etc.).
5. Out of scope for the first cut: `queue.db`, codegraph DB, and workspace-manifest aggregation over remote backends.

## Open Questions

- Which non-SQLite backend first? Postgres (widest team use) vs. libSQL/Turso (SQLite-compatible, minimal dialect work — likely the lowest-risk first target).
- Dependency policy: a Postgres driver (`psycopg`) would be a new third-party dependency; per CLAUDE.md it needs a justified, optional-extra pin (e.g. `pip install little-loops[postgres]`).
- Should `ll-doctor` validate remote connectivity and schema version at startup?

## Acceptance Criteria

- [ ] `history.backend` schema added to `config-schema.json` with `sqlite` default; existing `db_path` / `LL_HISTORY_DB` behavior unchanged (regression tests pass).
- [ ] A single backend chokepoint in `session_store`; no new bare `sqlite3.connect` in session_store write/read paths.
- [ ] At least one remote backend works end-to-end for `ll-history`, session digest, and compaction reads/writes, exercised by an integration test that skips when the backend is unavailable.
- [ ] SQLite-only features degrade with a clear message on unsupported backends.
- [ ] `docs/reference/` documents the new config and env-var secret pattern for end users.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-22 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-22T15:39:46 - `eaf98e36-fcf5-4247-8879-8cd909331a2a.jsonl`
