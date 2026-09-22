---
id: FEAT-3524
type: FEAT
title: Pluggable storage backend for history.db with remote database support
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-22'
captured_at: '2026-09-22T15:39:38Z'
learning_tests_required:
  - psycopg
  - libsql
spike_attempted: true
spike_completed: true
---

# FEAT-3524: Pluggable storage backend for history.db with remote database support

## Summary

Allow little-loops users to point `history.db` at a remote database (e.g. Postgres, MySQL, or a networked/hosted SQLite such as Turso/libSQL) via a pluggable storage backend configured under `history.*` in `.ll/ll-config.json`, instead of only the local in-repo `.ll/history.db` file.

## Current Behavior

`history.db` is always a local SQLite file. `history.db_path` (`config-schema.json`
line 2164, `history` block) only overrides the local filesystem path — relative
paths resolve against the project root and `LL_HISTORY_DB` takes precedence
(ENH-2623), resolved by `little_loops.session_store.db._resolve_db_path` /
`resolve_history_db`. The storage layer itself is hardcoded to `sqlite3`:
`little_loops.session_store.schema.ensure_db` opens `sqlite3.connect(str(db_path))`
directly, and roughly 28 other call sites across ~15 modules
(`session_store/{schema,sessions,queries,lifecycle,writers}.py`,
`history_reader/_base.py`, `issue_history/*`,
`cli/{history,logs,doctor,doctor_trim,ctx_stats}.py`, `queue_store.py`,
`codegraph.py`) do the same, many relying on SQLite-specific features
(`file:{path}?mode=ro` URIs, WAL PRAGMAs, FTS5). There is no way to point
`history.db` at a network-accessible database instead of a local file.

## Expected Behavior

A user should be able to configure `history.backend` in `.ll/ll-config.json`
to point `history.db` at a remote database (Postgres, MySQL, or a networked
SQLite such as Turso/libSQL) instead of the local file, with the default
(`kind: sqlite`, unset `backend`) behaving exactly as today. All
`session_store` read/write paths (`ll-history`, `ll-logs`, session digests,
compaction context) should work transparently against the configured
backend, with SQLite-only features (FTS5 search, WAL, `VACUUM`) degrading
with a clear message rather than crashing on backends that don't support
them.

## Motivation

Teams running little-loops across several machines or CI runners (e.g. the self-hosted runner) have no way to share one history/analytics store. A remote backend enables cross-machine `ll-history` / `ll-logs` analytics, session digests, and compaction context without syncing `.db` files, and unblocks hosted dashboards reading the same store.

## Proposed Solution

Introduce a `history.backend` config block (`kind: sqlite|postgres|libsql` +
`url`/`url_env`, default `sqlite` = current behavior unchanged) and a new
backend abstraction module, `little_loops.session_store.backend`, exposing
`connect()` / `connect_readonly()` / `ensure_schema()` plus dialect
capability flags. Route every `sqlite3.connect(` call site in
`session_store` and its consumers through this single chokepoint (mirrors
the `resolve_host()` pattern in `little_loops/host_runner.py:2535` for host
CLI abstraction), keep SQLite-only features (FTS5, WAL PRAGMAs, `VACUUM`)
behind capability checks that degrade gracefully, and reuse
`_apply_migrations` with per-dialect DDL where SQLite syntax diverges. See
`## Proposed Design` below for the full phased breakdown and open questions
(backend choice, driver dependency policy, `ll-doctor` connectivity checks).

## Integration Map

### Files to Modify
- `little_loops/session_store/db.py` (`_resolve_db_path`, `resolve_history_db`)
- `little_loops/session_store/schema.py` (`ensure_db`, `_configure_connection`, `_apply_migrations`)
- `little_loops/session_store/{sessions,queries,lifecycle,writers}.py`
- `little_loops/history_reader/_base.py`
- `little_loops/issue_history/*`
- `little_loops/cli/{history,logs,doctor,doctor_trim,ctx_stats}.py`
- `little_loops/queue_store.py`, `little_loops/codequery/codegraph.py` (evaluate whether in scope for the first cut — see Proposed Design item 5)
- `little_loops/config-schema.json` (`history` block, line 2138 — add `backend`)

### Dependent Files (Callers/Importers)
- The ~28 `sqlite3.connect(` call sites enumerated above are themselves the
  callers that must move behind the new `session_store.backend` chokepoint;
  no external module imports `session_store` internals directly beyond the
  files already listed.

### Similar Patterns
- `little_loops/host_runner.py` `resolve_host()` (line 2535) is the existing
  single-chokepoint abstraction pattern for host CLI selection
  (`LL_HOST_CLI` / `orchestration.host_cli`) that this backend abstraction
  should mirror for `history.backend` selection.

### Tests
- `scripts/tests/test_session_store_db.py`, `test_session_store_schema.py`,
  `test_session_store_lifecycle.py`, `test_session_store_queries.py`,
  `test_session_store_writers.py`
- `scripts/tests/test_history_reader_*.py` (11 files) — exercise reads
  through the new backend for at least the default `sqlite` path
- New: an integration test for the first remote backend that skips when
  that backend is unavailable (per Acceptance Criteria)

### Documentation
- `docs/reference/` — new `history.backend` config keys and the env-var
  secret pattern (per Acceptance Criteria)

### Configuration
- `.ll/ll-config.json` `history.backend` block; `LL_HISTORY_DB` /
  `history.db_path` remain the sqlite-only path override, unchanged

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- **Closer existing precedent than `resolve_host()`**: `resolve_provider()` (`codequery/core.py:103`) is a config-driven, pluggable-backend resolver — a `@runtime_checkable` Protocol + a lazy-import `name -> (module_path, class_name)` registry (`_PROVIDER_MAP`, `codequery/core.py:93-96`) + `"auto"` fallback that tries candidates in registry order. It explicitly documents mirroring `little_loops.adapters.core` (FEAT-2391, FEAT-2576). Unlike `resolve_host()`'s eagerly-imported class registry, `resolve_provider()`'s registry entries are resolved via `importlib.import_module` only on demand — the rationale given (`codequery/core.py:93-96`) is that concrete provider modules import back from `core.py`, so eager import would create a cycle. Whichever eager-vs-lazy shape is chosen for `session_store.backend`, the codebase currently holds both conventions, not one.
- **Config-schema shape for a discriminated backend selector**: a `"provider"`/`"kind"` string with a JSON Schema `"enum"` + `"default"` sits alongside a same-named nested settings object, even when only one provider currently exists (`sync.provider`, `config-schema.json:1390-1445`, `"enum": ["github"]` with a full nested `"github"` object) or several do (`code_query.provider`, `config-schema.json:1449-1484`, `"enum": ["auto", "codegraph", "fallback"]` with a nested `"codegraph"` settings object).
- **Existing degradation precedent is exception-based, not a `supports()` boolean check**: `Unsupported(CodeQueryError)` (`codequery/core.py:39-44`) is raised by a provider for a query kind outside its `capabilities()`; its docstring claims the resolver catches this to fall through to a fallback provider, but a repo-wide search found no `except Unsupported` anywhere outside `cli/code.py:146` — the only live catch site logs and exits (`return 2`), it does not fall through. `HostCapabilities` (`host_runner.py:294-318`) is the other existing capability-flag precedent: a frozen dataclass of plain booleans, with an unsupported capability silently dropped and a `CapabilityNotSupported(UserWarning)` emitted rather than raised.
- **`_apply_migrations` (`session_store/schema.py:1492-1567`) is single-dialect today**: it takes a live `sqlite3.Connection` directly (not a path or dialect token), `_MIGRATIONS` is an unconditional `list[str]` of raw SQL with no per-dialect branch, and locking is SQLite-specific (`BEGIN IMMEDIATE`, manual `isolation_level = None`, a custom `_split_sql_statements()` helper whose docstring explains it avoids `executescript()`'s implicit `COMMIT` that would release the write lock mid-migration). `_configure_connection()` (`schema.py:1443-1459`) applies WAL/`busy_timeout` pragmas wrapped in `try/except sqlite3.OperationalError` — today's one instance of graceful degradation in this file is per-pragma try/except, not a capability-flag check.
- **No existing `connect_readonly()` counterpart anywhere in the tree** (repo-wide search, zero hits). The closest analog is two independently-duplicated private `_open_db()` helpers — `issue_history/evolution.py:30` and `codequery/codegraph.py:81` — both opening `file:{path}?mode=ro` with `uri=True` and `PRAGMA query_only = ON`, never raising (`except sqlite3.Error: return None`). The `codegraph.py` copy's docstring states it explicitly mirrors the `evolution.py` one rather than sharing a common module — i.e. the current convention for a read-only SQLite open is duplication-by-mirroring, not a shared function.
- **Optional-dependency extras** (`pyproject.toml:141-199`) follow `<name> = ["pkg<constraint>"]` under `[project.optional-dependencies]`, with an inline justification comment on any version bound — the `mcp` extra (`pyproject.toml:178-191`) is the fullest example, explaining both the exact pin and why it's an extra rather than a base dependency (16 mandatory transitive deps otherwise landing on every install). A repo-wide search found no existing reference to `postgres`, `libsql`, `psycopg`, or `sqlalchemy` anywhere in `scripts/pyproject.toml` or `scripts/little_loops/`.
- **No dialect abstraction exists anywhere in the codebase today**: a repo-wide search for `dialect` as a code identifier and for any `*Dialect` class found zero hits. `little_loops.session_store.backend` (the module this issue proposes) has no current counterpart in the tree.

## Implementation Steps

1. Add `history.backend` to `config-schema.json` with `sqlite` default; confirm existing `db_path` / `LL_HISTORY_DB` regression tests still pass unchanged.
2. Build `little_loops.session_store.backend` (`connect()` / `connect_readonly()` / `ensure_schema()` + capability flags) and route all `session_store` connection sites through it.
3. Gate SQLite-only features (FTS5 search, WAL PRAGMAs, `VACUUM`) behind capability checks with a clear "not supported by backend" degradation path.
4. Extend `_apply_migrations` with per-dialect DDL for the first non-SQLite backend chosen (see Open Questions).
5. Add an integration test for the chosen remote backend (skips when unavailable) and document the new config + secret pattern in `docs/reference/`.

## Impact

- **Priority**: P3 - Cross-machine/CI analytics sharing is valuable but no current user is blocked; local `.ll/history.db` remains fully functional.
- **Effort**: Large - ~28 call sites across ~15 modules must move behind a new chokepoint, plus a new optional third-party driver dependency and per-dialect migration handling.
- **Risk**: Medium - default (`sqlite`, no `backend` configured) preserves current behavior exactly, but the abstraction touches every session_store read/write path, so a regression could silently corrupt or misroute local history data.
- **Breaking Change**: No - opt-in via `history.backend`; unset behaves identically to today.

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

## Program Design

### Types

- `BackendKind: Literal["sqlite", "postgres", "libsql"]`
- `BackendConfig: dataclass` (`kind: BackendKind`, `url: str | None`, `url_env: str | None`)

### Signatures

- `resolve_backend(config: dict) -> Backend` (mirrors `resolve_host()` in `host_runner.py:2535`)
- `Backend.connect(self) -> Connection`
- `Backend.connect_readonly(self) -> Connection`
- `Backend.ensure_schema(self) -> None`
- `Backend.supports(self, capability: str) -> bool` (gates FTS5/WAL/`VACUUM`)

### Call Path

`session_store.schema.ensure_db` -> `session_store.backend.resolve_backend` -> `Backend.connect` / `Backend.ensure_schema` -> `session_store.schema._apply_migrations`

## Use Case

**Who**: A little-loops maintainer running work across several machines and
a self-hosted CI runner (per `.claude/CLAUDE.md`'s Thinky runner).

**Context**: Each machine currently writes its own local `.ll/history.db`,
so `ll-history` / `ll-logs` analytics, session digests, and compaction
context are fragmented per machine with no way to sync without shipping
`.db` files around.

**Goal**: Point every machine's `history.backend` at one shared Postgres (or
libSQL/Turso) instance via `.ll/ll-config.json`, so all machines write to
and read from the same store.

**Outcome**: `ll-history` and `ll-logs` see session/usage data from every
machine, session digests and compaction context stay consistent regardless
of which machine ran a session, and a hosted dashboard can read the same
store live.

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

## Spike Results

_Added by `/ll:spike` on 2026-09-22_

**Retired risks**

| Risk (from standalone analysis of Proposed Solution) | Proven by | Result |
|----------------------------------|-----------|--------|
| (a) Zero precedent: dialect abstraction driving `_apply_migrations`'s `BEGIN IMMEDIATE`/manual-isolation/split-statement locking sequence with per-dialect DDL | `TestDialectMigration::test_sqlite_backend_migrates_with_existing_locking_sequence`, `test_stub_remote_backend_uses_dialect_specific_ddl`, `test_rerunning_ensure_schema_is_idempotent` | ✓ pass |
| (a) Concurrent migration race under a dialect-parameterized chokepoint | `TestConcurrentMigration::test_concurrent_migration_race_still_serializes` | ✓ pass |
| (b) No existing test exercises capability-gated degradation for SQLite-only features | `TestCapabilityGate::test_capability_check_gates_unsupported_feature`, `test_capability_check_passes_for_supported_feature` | ✓ pass |
| isolation guard | `TestSpikeIsolation::test_spike_does_not_import_production_session_store` | ✓ pass |

**Spike location**: `scripts/tests/spike/session_store_backend_dialect/`
**Verification**: 7 tests pass across 2 commands (spike AC suite + `test_session_store_schema.py` regression, 193 tests, both untouched).
**Excluded from scope** (per user confirmation): real Postgres/libSQL driver connectivity (`/ll:explore-api` territory, already tracked via `learning_tests_required`) and the Postgres-vs-libSQL backend choice (`/ll:decide-issue` territory, issue's own Open Questions).
**Promotion**: fold `backend.py`'s `Backend` protocol and dialect-parameterized `apply_migrations` into `little_loops/session_store/backend.py` (new production module) and `little_loops/session_store/schema.py`, with tests promoted into `scripts/tests/test_session_store_backend.py`, in a separate PR.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-22 | Priority: P3


## Session Log
- `/ll:spike` - 2026-09-22T16:01:14 - `69316b42-0fe0-49ed-a8dc-481387700cff.jsonl`
- `/ll:refine-issue` - 2026-09-22T15:53:02 - `24e361bf-844f-4527-b6ee-85c86b44db2a.jsonl`
- `/ll:format-issue` - 2026-09-22T15:43:55 - `f8344c01-034b-4d86-8218-d0d7fb43cbd5.jsonl`
- `/ll:capture-issue` - 2026-09-22T15:39:46 - `eaf98e36-fcf5-4247-8879-8cd909331a2a.jsonl`
