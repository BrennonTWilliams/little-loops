---
id: FEAT-3535
type: FEAT
title: Remote libSQL history backend via stdlib Hrana-over-HTTP client
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:46:29Z'
learning_tests_required:
- hrana-http
verify_verdict: VALID
reconcile_attempted: true
confidence_score: 90
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
blocked_by:
- ENH-3650
---

# FEAT-3535: Remote libSQL history backend via stdlib Hrana-over-HTTP client

## Summary

Let little-loops projects share one `history.db` store across machines through a remote
libSQL endpoint (self-hosted `sqld` or Turso Cloud). Talk to it with a small stdlib client
for libSQL's Hrana-over-HTTP protocol (`/v3/pipeline`), not the `libsql` Python binding.
This is the successor to FEAT-3524, which was cancelled on 2026-09-23. See FEAT-3524's
`### Decision Rationale`: this issue is its Option A.

## Current Behavior

`history.db` is always a local SQLite file. ENH-3525 and ENH-3526 (both done) delivered the
connection chokepoint in `little_loops.session_store.backend`: the `Backend` protocol,
`resolve_backend()`, `open_history()` / `open_history_readonly()` / `connect_readonly()`,
and the `HistoryError` taxonomy. The only registered backend is `SqliteBackend`, and no
remote transport exists.

## Expected Behavior

- An unset `history.backend`, or `provider: sqlite`, behaves exactly as today.
- `provider: libsql` routes history reads and writes to the remote store through a
  `LibsqlBackend` built on the stdlib Hrana client.
- Unsupported operations report a clear capability limitation naming the operation. These
  are the maintenance operations (`rebuild`, `prune`, `compact`, `recompress`, `VACUUM`),
  `ATTACH`, `create_function`, the WAL pragmas, and snapshot export. FTS5 search is
  supported remotely (probed 2026-09-28).
- Best-effort telemetry never aborts the operation it observes.
- Every network wait is time-limited.

## Motivation

FEAT-3524's Step 1 learning test (`.ll/learning-tests/libsql-remote.md`, `libsql` 0.1.11)
failed 7 required remote assertions:

- **F1:** a connect to an unreachable host cannot be time-limited.
- **F2:** the driver holds the GIL for the whole network call, so every thread freezes.
- **F3:** `isolation_level` is read-only after connect.
- **F4:** two concurrent initializers do not serialize.
- **F5:** there is no statement timeout.
- **F6:** idle streams expire.
- **F7:** `executescript` silently swallows errors in remote mode.

F1, F2, F3, F5 and F7 come from the binding, not from the protocol. A client built on
`http.client`/`urllib` gets real socket timeouts, releases the GIL, and returns structured
Hrana error codes. Those codes make `HistoryError` classification reliable instead of
depending on message matching. The client also adds no third-party dependency, as
CLAUDE.md asks. Server-side atomic `batch` requests with step conditions could replace the
interactive migration transaction, which would sidestep F4 and F6 for migrations.

The motivation is the same as FEAT-3524's: teams running little-loops on several machines
or CI runners have no shared history/analytics store.

## Proposed Solution

1. **Gate first:** produce a new learning test, `.ll/learning-tests/hrana-http.md` (new), against
   both `sqld` and Turso Cloud. It must prove:
   - `/v3/pipeline` request/response shape and baton/stream handling;
   - atomic `batch` with step conditions (rollback on a failed step);
   - two concurrent `migrate` runs serialize or fail safely (the F4 scenario);
   - the Hrana error codes in structured form (`SQLITE_CONSTRAINT`, `SQLITE_BUSY`,
     `STREAM_EXPIRED`, auth failure);
   - socket-level connect and read timeouts against a blackholed host;
   - that other threads keep running during a slow request.

   If any required assertion fails, stop and re-scope.
2. Implement a minimal Hrana-over-HTTP client module on `http.client`/`urllib`, following
   in-repo precedents:
   - `little_loops/link_checker.py:256`: `urllib` with bounded timeouts and classified
     transport vs. application errors.
   - `little_loops/mcp_call.py:75`: a JSON-RPC client written in-house, with a monotonic
     deadline.
3. Build `LibsqlBackend` on that client and register it in `resolve_backend()`.
4. Apply the settled design restated under Proposed Design below (configuration and
   precedence, `HistoryTarget`, env relay, errors and capabilities, operation matrix,
   remote ingestion, telemetry budget, migration policy and project identity, plus the
   `ll-doctor` backend diagnostic). It was reviewed under FEAT-3524, which is cancelled; the
   Hrana client replaces the `libsql` binding assumptions (no isolation-level workaround, no
   `executescript`, no extras dependency).

## Proposed Design

Restated from cancelled FEAT-3524 (§1-§10, reviewed 2026-09-22/23) and adapted to the Hrana client. This section is authoritative; the predecessor need not be read.

### 1. Configuration and precedence

```json
{"history": {"backend": {"provider": "libsql", "url_env": "LL_HISTORY_URL",
  "auth_token_env": "LL_HISTORY_AUTH_TOKEN", "project_id": "acme-api",
  "telemetry_timeout_ms": 1500}}}
```

- `provider` is the selector (`"enum": ["sqlite", "libsql"]`, default `"sqlite"`), matching `sync.provider` and `code_query.provider`. libSQL takes exactly one endpoint source: a non-secret literal `url` or `url_env`. `project_id` is required when `provider: libsql`. `auth_token_env` names an environment variable; a literal token is never accepted in config.
- Tokens are never committed, echoed by `ll-doctor`, emitted by `HistoryConfig.to_dict`, or written to logs or error text. There is no silent fallback to a local store after a remote failure.
- Unset backend or `provider: sqlite` is unchanged: `explicit path > LL_HISTORY_DB > history.db_path > DEFAULT_DB_PATH`.
- Under `provider: libsql`, default-shaped arguments (`DEFAULT_DB_PATH`, `None`) to `open_history`, `open_history_readonly` and `cli_event_context` select the remote store. An explicit non-default path, or `LL_HISTORY_DB` set, stays an explicit local SQLite target. `history.db_path` is ignored under `libsql`, and `ll-doctor` reports when both are set.
- `resolve_history_db()` and `ensure_db()` keep SQLite behavior for local targets and raise a typed `HistoryBackendNotLocal` for the remote target; no fabricated path is ever returned.
- The reader must apply the `ll.local.md` frontmatter deep merge (`config/core.py` `parse_local_override_frontmatter` and `deep_merge`); `db.py::_config_db_path` reads raw JSON and would ignore a local endpoint, so it is not copied. It never raises on the hook hot path (malformed config means `provider: sqlite` plus a one-time warning, never a silent remote-to-local switch after a remote provider was readable) and caches per process. User docs recommend setting the endpoint in `.ll/ll.local.md` so a clone does not silently join a shared store.

### 2. Target type (SQLite-only refactor, lands first, no behavior change)

- `HistoryTarget = LocalTarget(path: Path) | RemoteTarget(config: BackendConfig)` (frozen dataclasses). `_resolve_once(target)` returns it.
- `Backend.connect`, `connect_readonly` and `ensure_schema` take a `HistoryTarget`. `SqliteBackend` accepts only `LocalTarget`, `LibsqlBackend` only `RemoteTarget`; a mismatch raises `HistoryUnsupported`. The backend is chosen from the target: entry points call `resolve_backend(target.provider)`.
- The three entry points' return annotation narrows to `HistoryConnection`. Callers needing `sqlite3` specifics (`create_function`, `ATTACH`, `row_factory`) keep `sqlite3.Connection` and gate on `supports()` first.
- **Fail-closed scope of remote support.** The lower-level `schema.connect` and `ensure_db` seam is made target-aware once, rather than editing every call site. Under a `RemoteTarget`, every site that reaches it either performs an operation the matrix in section 5 marks supported, or raises `HistoryUnsupported` before any mutation. Sites holding a `LocalTarget` keep SQLite behavior. This bounds "history reads and writes route to the remote store" without migrating the roughly 50 bypassing sites one by one.

### 3. Env relay

`worktree_utils.py` exports `LL_HISTORY_DB=str(resolve_history_db())` before worktree creation. When the resolved target is a `RemoteTarget` the relay exports nothing and does not raise, so descendants resolve the same config and reach the same store. If `LL_HISTORY_DB` is already set while `provider: libsql` is configured, the relay leaves it (a deliberate local override) and `ll-doctor` reports the conflict. The same rule covers `pytest_history_plugin.py`; `hooks/session_start.py` is handled as an ingestion writer (section 6).

### 4. Errors, capabilities and timeouts

- Error mapping is the Error Code Mapping table under Program Design. Stream-lost errors are retryable once for idempotent reads; never inside a write transaction; telemetry drops instead of retrying. An ambiguous commit (connection lost during a `batch`) is resolved by re-reading an idempotent marker, such as the schema-version row for migrations.
- `HistoryUnsupported` gains an optional keyword-only `operation` attribute (backward compatible), so the raised error names the operation.
- Capability names are a closed set defined once in `backend.py`: existing `attach`, `vacuum`, `create_function`, plus new `wal` (the `journal_mode` and `busy_timeout` pragmas) and `snapshot_export`. `LibsqlBackend.supports()` is False for all five; the maintenance operations in section 5 are rejected by name rather than by capability.
- **FTS5 is supported remotely.** A probe on 2026-09-28 (Turso, `CREATE VIRTUAL TABLE ... USING fts5`, `MATCH`, `bm25`, `PRAGMA table_info`) succeeded, matching the `libsql-remote` record. `PRAGMA journal_mode`, `busy_timeout`, `ATTACH` and `VACUUM` return `SQL_PARSE_ERROR` with "SQL not allowed statement", so `LibsqlBackend` skips the WAL setup instead of relying on error mapping.
- `create_function` is unavailable remotely; `history_reader/formatting.py::ll_grep` under `libsql` prefilters with a bounded plain SQL predicate and applies the regex in Python.
- Every network wait uses a socket timeout with a monotonic total deadline (`mcp_call.py::_send_jsonrpc` pattern). Explicit reads and maintenance default to 10s; telemetry paths use `telemetry_timeout_ms`.
- Rows are adapted to the `HistoryRow` and `HistoryCursor` protocols (name and index access, `keys()`, `dict(row)`, `lastrowid`, `rowcount`, `executemany`); nothing assumes `sqlite3.Row`.

### 5. Shared-store operation matrix (hard gate)

A rejected operation raises `HistoryUnsupported` (naming the operation) before any mutation.

| Operation | Under `libsql` |
|---|---|
| `rebuild()` (also the backfill worker's rebuild flag) | rejected: global `DELETE` on derived tables with no concurrency guarantee |
| full `backfill` (`ll-session backfill`) | rejected: overwrites other machines' rows |
| `backfill_incremental` and `backfill_raw_events` (SessionStart worker) | supported, with the per-machine watermark (section 6) |
| `prune()`, `ll-session compact`, `compact --and-prune`, `recompress` | rejected: rewrite or delete `raw_events` other machines use |
| `VACUUM` | rejected: local-file operation (the `hooks/sweep_stale_refs.py` hook only writes a lifecycle event row, an ordinary supported event write) |
| reads, event writes, search, `ll-history`, `ll-logs`, digests, context compaction (`little_loops.compaction`) | supported |
| snapshot export | rejected (`ATTACH` to a local destination is unavailable) |

"Compaction" names two things: context compaction (additive, supported) and the `ll-session compact` raw-event rewrite (destructive, rejected); docs, errors and tests use the full names. With prune, compact and recompress rejected, a remote store has no retention path in the first release; user docs say so and `ll-doctor` reports row counts for the largest tables. Prune stays manual-only. Identity: a stable random machine ID lives in a gitignored machine-local file (`~/.ll/machine-id`) and is used only for the watermark; foreign `jsonl_path` values are skipped and labelled "recorded on another machine", never treated as errors; no provenance column is added unless the copied-session test below proves it necessary.

### 6. Remote ingestion

- `backfill_raw_events()` reads and writes `meta.last_raw_event_ts:<machine_id>` instead of the global key (a global key lets one machine's progress silently skip another's older transcripts). SQLite keeps the global key.
- After ingest, derived `_REBUILD_TABLES` rows are materialized for only the newly inserted `raw_events` rows, additively and idempotently (`INSERT OR IGNORE` or upsert; no `DELETE`). First confirm which derived tables live hooks already write (`writers.py`, `hooks/post_tool_use.py`, `fsm/continuity.py`) so nothing is double-written; any derived table with no natural dedup key gets one by migration before it is materialized remotely.
- `hooks/session_start.py` resolves a `HistoryTarget`, passes it to `cli/backfill_worker.py`, never passes a rebuild flag, and never migrates on open; the worker refuses a rebuild under `libsql`. A copied session JSONL at a different path is tested; if it double-ingests, remote ingestion dedups on `(session_id, line_no)`.
- Schema bumps that would trigger a local rebuild are out of scope; the migrate command reports that derived tables for pre-bump rows are not re-materialized.

### 7. Telemetry latency budget

Hooks have a 5s timeout (`hooks/hooks.json`) and every `ll-*` CLI is wrapped by `cli_event_context`, so a slow endpoint must not cost every invocation the full wait.

- Telemetry and best-effort paths (hooks, `cli_event_context`, `SQLiteTransport`) use `telemetry_timeout_ms` (default 1500 total per write). Explicit reads and maintenance use the longer bound.
- The Hrana client needs one HTTP round trip per execute and no separate ensure connection. `LibsqlBackend` caches "schema verified at version N" per process. Because hooks are one process per event, a file-backed verification cache (endpoint hash, verified version, `project_id`, TTL 300s) sits next to the unreachable marker; a schema or constraint failure invalidates it. Explicit reads, the migrate command and `ll-doctor` ignore it.
- On a connect failure or timeout in a telemetry path, write an unreachable marker under `.ll/` (TTL 60s, keyed by endpoint hash, never the token); later telemetry writes within the TTL skip immediately with no network attempt and no repeated warning. Explicit reads and `ll-doctor` ignore it.
- Both files are gitignored in this repository and in consuming projects (`init/writers.py::_GITIGNORE_ENTRIES`), by explicit entries or an existing ignored glob such as `.ll/*.lock`. Dropped telemetry is not buffered or replayed.
- Success-path budget: a hook-path telemetry write on a healthy endpoint with a warm cache stays well under the hook timeout. Measured on 2026-09-28, one `select 1` took a median 180ms on Turso Cloud (fresh connection) and 1ms on a local `sqld`.

### 8. Migration policy and project identity


<!-- ll-prose-ok: migrate is a planned new subcommand delivered by this issue -->
- Opens never migrate under `libsql`. Schema changes happen only through the new `ll-session migrate` command (valid for both providers, a no-op when current), which reports the before and after version and sends each migration as one atomic `batch`.
- Store behind client (`recorded < len(_MIGRATIONS)`): writes and `ensure=True` reads raise `HistoryUnsupported` naming the migrate command; telemetry paths warn once and skip; strict reads proceed. Store ahead of client: reads proceed, writes are refused with an "upgrade little-loops" message, and the BUG-3255 stamp self-heal never runs against a remote store. `ll-doctor` reports recorded and installed versions.
- The migrate command on an empty remote store stamps `meta.project_id` from `history.backend.project_id`. Every remote open compares the two once per process and raises `HistoryUnsupported` on mismatch; `ll-doctor` reports a mismatch. Sharing one store across unrelated projects is prevented, not merely unsupported.

### 9. Out of scope

Postgres, MySQL or a general SQL dialect layer; other Turso engines or drivers; embedded replicas and offline sync; migrating `queue.db` or codegraph databases; workspace-manifest aggregation over remote backends (`history.workspace_manifest_path` stays local); multi-project tenancy and machine-filtered analytics; a remote retention or prune path; buffering or replaying dropped telemetry; seeding a remote store from an existing local `history.db` (a new store starts empty apart from each machine's own transcript backfill; user docs say so); snapshot export under `libsql`; re-materializing derived tables after a schema bump.

## Integration Map

### Files to Modify
- `little_loops/session_store/backend.py`: register `LibsqlBackend` in `_BACKEND_MAP`; source
  the provider from config inside `resolve_backend`/the entry points (`BackendProvider` is
  `Literal["sqlite"]` today); add the `wal` and `snapshot_export` capability strings and
  the `HistoryUnsupported.operation` attribute. The `HistoryTarget` retype of `Backend`,
  `_resolve_once` and the entry points is delivered first by ENH-3650.
- New module for the Hrana HTTP client, beside `session_store/backend.py`.
- Hook paths and the environment-override readers (`main_hooks`, `post_tool_use`,
  `session_start`, `post_commit`, `pytest_history_plugin`) and `db.py::_resolve_db_path`
  move onto the target seam in ENH-3650; this issue only adds the `RemoteTarget` branch
  (relay export, ingestion worker target).
- `little_loops/session_store/schema.py`: remote migration path via atomic `batch`
  (preserve re-read-under-lock semantics; `_configure_connection` pragmas and the
  `_schema_manifest` structural comparison have no remote analogue yet).
- `little_loops/config-schema.json` (`history` block, `additionalProperties: false`),
  `config/features.py::HistoryConfig.from_dict`, `config/core.py`: declare `history.backend`.
- `little_loops/cli/session.py::_build_parser`: add the `migrate` subparser (module
  docstring and epilog too).
- `little_loops/cli/doctor.py::_history_db_data`: remote probe branch (currently hard-codes
  `Path.cwd() / DEFAULT_DB_PATH` and a SQLite-header check); never echo the auth token.
- Remaining call sites that bypass the chokepoint (`writers.py` ~30 and `lifecycle.py` 12
  `schema.connect` sites, `queries.py`, `workflow_sequence/io.py`, `compaction/result.py`,
  `issue_history/parsing.py`, `cli/harness.py`, `cli/history_context.py`,
  `fsm/continuity.py`) reach the target-aware `schema.connect` seam from ENH-3650, so under
  a `RemoteTarget` each is fail-closed per the operation matrix (Proposed Design section 5)
  rather than migrated site by site.

### Dependent Files (Callers/Importers)
- Chokepoint callers that must keep working unchanged for `sqlite`:
  `session_store/writers.py::SQLiteTransport`, `session_store/lifecycle.py`
  (`recompress`/`prune`/retirement run `VACUUM`), `history_reader/_base.py::_connect_readonly`
  (~80 reader functions; also serves `issue_history/{agent_quality,collisions,rework}.py`),
  `cli/history.py`, `cli/ctx_stats.py`, `cli/logs.py`, `issue_history/workspace_quality.py`,
  `issue_history/evolution.py`, `cli/doctor.py`, `cli/doctor_trim.py`.
- A `HistoryError`-only backend is not caught by the ~127 `except sqlite3.(Error|OperationalError)`
  sites (e.g. `writers.py::record_hook_event`, `cli/doctor.py::_history_db_data`); review each
  site's best-effort role.

### Tests
- New learning test `hrana-http` (proven 2026-09-28).
- Remote integration tests marked `pytest.mark.integration` and selected by
  `LL_TEST_LIBSQL_URL` + `LL_TEST_LIBSQL_AUTH_TOKEN`: they skip only when that configuration
  is absent, and a failure against a configured endpoint fails the test.
- Unit tests for the Hrana client against a real stdlib stub HTTP server bound to
  `127.0.0.1` port 0 in a daemon thread (`test_flux_image_generator.py::flux_stub` pattern;
  `shutdown()` then `server_close()`): timeouts, error-code mapping, batch encoding. The
  blackhole-connect timeout needs a real socket; mocked `urlopen` cannot prove it.
- Keep green: `test_session_store_backend.py` (`TestResolveBackend`,
  `TestProtocolConformance`, `TestCapabilityGate`), `test_history_store_chokepoint_gate.py`,
  `test_session_store_writers.py`, `test_session_store_lifecycle.py`, `test_config_schema.py`,
  `test_config.py::TestHistoryConfig`, `test_wiring_reference_docs.py`,
  `test_wiring_init_and_configure.py`.

### Documentation
- `docs/reference/CONFIGURATION.md` (`history.backend`), `docs/reference/CLI.md`
  <!-- ll-prose-ok: migrate is a planned new subcommand delivered by this issue -->
  (`ll-session migrate`), `skills/configure/areas.md` `## Area: history` (decide knowingly
  whether `backend` follows the fuller or thinner `workspace_manifest_path` precedent);
  skill/README edits trip the mirror gates (`ll-adapt --host <gemini|kimi-code|qwen> --apply`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

- **Chokepoint coverage is partial.** `open_history`, `open_history_readonly`, and `connect_readonly` in `session_store/backend.py` each call `resolve_backend()` with no argument, so provider is hard-defaulted to `sqlite`; `BackendProvider` is `Literal["sqlite"]` and `_BACKEND_MAP` has one entry. `Backend.connect`/`connect_readonly`/`ensure_schema` take `Path` and return `sqlite3.Connection`; `_resolve_once` returns `Path`; `open_history_readonly` catches `sqlite3.Error` directly. The `Backend` docstring says the connect methods narrow to `HistoryConnection` when a second provider lands.
- **Callers that go through the chokepoint** (must keep working unchanged for `sqlite`): `SQLiteTransport.__init__` in `session_store/writers.py` (`open_history(..., check_same_thread=False)`, best-effort: failure disables the sink); `recompress`/`prune`/retirement in `session_store/lifecycle.py` (run `VACUUM` on the connection); `history_reader/_base.py::_connect_readonly` (`open_history_readonly(ensure=True)`, converts `HistoryError` to a logged warning and `None`; ~80 reader functions depend on it); `cli/history.py`, `cli/ctx_stats.py`, `cli/logs.py` (module `connect_readonly`); `issue_history/workspace_quality.py`, `issue_history/evolution.py`, `cli/doctor.py`, `cli/doctor_trim.py` (`resolve_backend().connect_readonly`).
- **Callers that bypass the chokepoint** and stay hard-sqlite unless moved: 30+ `schema.connect` sites in `writers.py`, ~14 in `lifecycle.py`, `queries.py`, `hooks/post_tool_use.py`, `hooks/session_start.py` (also `ensure_db` and a detached `backfill_worker` that receives the DB path as a string argv), `workflow_sequence/io.py`, `compaction/result.py`, `issue_history/parsing.py`, `cli/harness.py`, `cli/session.py`, `cli/history_context.py`, `fsm/continuity.py`; direct `sqlite3.connect(... mode=ro)` in `session_store/queries.py`, `session_store/sessions.py`, and the private `_connect_readonly` helpers in `issue_history/{agent_quality,collisions,rework}.py`. The scope of "history reads and writes route to the remote store" is therefore bounded by how many of these are migrated; the issue's inherited Files-to-Modify list should be reconciled against this set.
- **SQLite-specific features a remote backend cannot honour**, by location: `ATTACH` (`issue_history/workspace_quality.py`, snapshot export in `session_store/queries.py`); `create_function` (`history_reader/formatting.py` registers a regexp function); FTS5 `search_index` virtual table (created in `schema.py` migrations, written by `writers.py::_index`, queried in `queries.py`, `history_reader/search.py`, `mcp_server/tools.py`, `cli/history_context.py`); `VACUUM` (`lifecycle.py`); `PRAGMA` calls (`schema._configure_connection`, `_schema_manifest`, `sessions.py`, `workspace_quality.py`); `row_factory = sqlite3.Row` name/index access relied on by readers; `conn.getlimit`. No `executescript` call and no sqlite `.backup` call exists in source (`schema._apply_migrations` deliberately avoids `executescript` via `_split_sql_statements`).
- **Capability vocabulary gap.** `_SQLITE_CAPABILITIES` is only `attach`, `vacuum`, `create_function`; `supports()` has one consumer today (`workspace_quality.py`, which raises `HistoryUnsupported` when `attach` is absent). The issue's FTS5, maintenance, and snapshot-export limitations have no capability strings yet, and `HistoryUnsupported` is a bare class with no fields (no operation name).
- **Error taxonomy has no structured code.** `HistoryError` has four bare subclasses; `translate_sqlite_errors()` only maps `IntegrityError` to `HistoryIntegrityError` and any other `sqlite3.Error` to `HistoryOperationError`; it never yields `HistoryUnavailable`/`HistoryUnsupported`. `schema._current_version` detects a missing table by message text. The Hrana error-code to class mapping is new surface with no in-repo precedent for carrying a `code`.
- **Config and env today.** No `history.backend` key exists in `config-schema.json`, `config/features.py::HistoryConfig`, or `session_store/db.py`. `db.py::_resolve_db_path` precedence is `LL_HISTORY_DB`, then `history.db_path` (read by raw JSON, not `BRConfig`), then the explicit/default path, and only overrides default-shaped paths. `LL_HISTORY_DB` is also read independently by `hooks/session_start.py`, `hooks/post_commit.py`, and `pytest_history_plugin.py`, so a target-type change must reach those readers too.
- **Latency-constrained best-effort paths.** `hooks/hooks.json` gives most hook entries a 5-second timeout (session-start, post-tool-use, precompact, subagent start/stop). `hooks/post_tool_use.py` performs its analytics write synchronously under `contextlib.suppress(Exception)` via `schema.connect`; `session_start.py` wraps `ensure_db` and a version read in `suppress(Exception)`. The only local wait bound today is `_BUSY_TIMEOUT_MS = 5000` in `schema.py`. A remote connect in these hooks must fit inside that hook timeout.
- **Migration path constraint.** `schema._apply_migrations` sets `isolation_level = None`, issues `BEGIN IMMEDIATE`, re-reads the version inside the lock, applies `_MIGRATIONS`, and rolls back on `BaseException`; its fast path returns early when the recorded version equals `len(_MIGRATIONS)`. Any remote migration must preserve the re-read-under-lock semantics that make concurrent initializers safe.

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

- **Conventions in force.** (1) Outbound HTTP passes a caller-supplied timeout to the socket call and classifies failures in one function, handling `HTTPError` before `URLError` with a catch-all last, into an outcome enum (`link_checker.py::_check_url_once`, `_classify_url_error`; anchors cited by the issue at `link_checker.py:256` and `mcp_call.py:75` both resolve). (2) Total-deadline budgeting is done inline with `time.monotonic()` plus a timeout and per-wait `remaining` (`mcp_call.py::_send_jsonrpc`, `transport.py`, `file_utils.py`); there is no shared deadline helper. (3) Registries of pluggable providers are lazy (module, class) maps mirroring `codequery.core.resolve_provider`. (4) A new config key touches: `config-schema.json` `history` block, `config/features.py::HistoryConfig.from_dict` (lenient), `config/core.py` wiring, `skills/configure/areas.md` `## Area: history`, `docs/reference/CONFIGURATION.md`, and structural (non-jsonschema) assertions in `test_config_schema.py` plus `test_config.py`; the most recent history example is `workspace_manifest_path`. Editing skills or README trips the mirror gates. (5) `ll-session` subcommands register in `cli/session.py::_build_parser` via `subparsers.add_parser` and dispatch through a linear `if args.command` chain inside `cli_event_context`; there is no `migrate` subparser yet. (6) Doctor checks are `@register_check` functions returning `CheckResult` lists in `cli/doctor.py`; an unconfigured optional feature reports informational, and only error-severity unsupported results produce exit 1.
- **Env-indirection has no precedent.** No `url_env`/`auth_token_env`-style config key exists anywhere; secrets are read by fixed-name `os.environ.get` (`host_runner.py`, `fsm/executor.py`). The issue's `url_env` / `auth_token_env` naming is a new config convention and should be decided knowingly, including that the token must never be echoed by `ll-doctor`, config `to_dict`, or logs.
- **No in-repo Hrana or JSON-POST client exists.** Non-test HTTP source is `link_checker.py` (urllib GET/HEAD) and servers in `transport.py` and `cli/artifact/{serve,policy_builder_routes}.py`; the cited precedents cover timeout and error classification, not request/response session handling (baton, stream expiry).

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

**Test conventions:**
- Convention: network-client tests run a real stdlib server bound to `127.0.0.1` port 0 in a daemon thread and tear it down with `shutdown()` then `server_close()`, with a small explicit client timeout (`scripts/tests/test_flux_image_generator.py` fixture `flux_stub`; `scripts/tests/test_feat3323_sse_bridge.py`). Contested: `scripts/tests/test_link_checker.py` instead mocks `urlopen` and injects exceptions to test timeout classification; a blackhole-connect timeout needs a real socket, which mocks cannot prove.
- Convention: opt-in external gates skip with a stated reason at module or test level (`test_host_conformance.py` gates live tiers on `LL_HOST_CONFORMANCE_LIVE`; `test_transport.py` uses `skipif` on a missing import). Tests needing a live endpoint are marked `pytest.mark.integration` and excluded from CI by `-m "not integration and not conformance"`. No `LL_TEST_LIBSQL_*` reference exists outside FEAT-3524/3535.
- Learning tests are markdown files under `.ll/learning-tests/` with frontmatter (`target`, `date`, `status`, `assertions` of claim/result, `raw_output_path`, `proven_package`, `proven_version`), managed by `ll-learning-tests` (`check`, `prove`, `list`, `mark-stale`). `libsql-remote.md` and `hrana-http.md` both exist (`hrana-http` proven 2026-09-28).

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Corrections to the earlier chokepoint-coverage finding (verified against current source).** `issue_history/{agent_quality,collisions,rework}.py` do not carry private raw `sqlite3.connect(mode=ro)` helpers; they import `_connect_readonly` from `little_loops.history_reader`, which goes through `open_history_readonly(ensure=True)`, so they are on the chokepoint. `session_store/sessions.py` opens Codex's own state index, not `history.db`, and is a permanent non-history entry in the `test_history_store_chokepoint_gate.py` allowlist. `lifecycle.py` has 12 `_pkg.connect` sites plus one `_pkg.ensure_db` (not ~14), and `writers.py` about 30. The only remaining private raw read-only opener for `history.db` is `session_store/queries.py::_connect_readonly` (allowlisted, pinned by `test_feat3304_artifact_dashboard.py`).
- **A history write path the earlier list missed.** `hooks/__init__.py::main_hooks` wraps every hook intent in `session_store.hook_event_context(<root>/.ll/history.db, ...)` when hook telemetry is enabled. It derives the path from the cwd rather than `resolve_history_db`, so a target-type change that only touches `_resolve_once` will not reach it. `hooks/post_tool_use.py` likewise hard-codes `cwd/.ll/history.db` for its direct `schema.connect`.
- **Gate that already pins the chokepoint boundary.** `scripts/tests/test_history_store_chokepoint_gate.py` AST-scans `scripts/little_loops/` for `sqlite3.connect(` and fails on any call outside its allowlist. A `LibsqlBackend` that never calls `sqlite3.connect` is unaffected; a change that routes more sites through the chokepoint should shrink, not grow, that allowlist. `~30` `_pkg.connect` (i.e. `schema.connect`) sites in `writers.py`/`lifecycle.py`/`queries.py` and the hook/CLI sites listed above are *not* covered by that gate, since it only matches `sqlite3.connect`.
- **Provider is not selectable through the chokepoint today.** `open_history`, `open_history_readonly`, and `connect_readonly` each call `resolve_backend()` with no argument, and `doctor.py`, `doctor_trim.py`, `issue_history/evolution.py`, and `issue_history/workspace_quality.py` call `resolve_backend().connect_readonly(...)` the same way. The provider must be sourced from config inside `resolve_backend`/the entry points, or every one of these call sites keeps selecting sqlite.
- **Row/cursor surface a Hrana-backed connection must satisfy** (verified consumption): `row["col"]`/`row[i]` and `row.keys()` (about 120 subscripts in `history_reader/`, plus `_base.py::_row_to_dataclass`), `dict(row)` (about 15 sites across `mcp_server/tools.py`, `session_store/queries.py`, `lifecycle.py`, `cli/history.py`, `cli/session.py`, `history_reader/{usage,subagents,formatting,sessions}.py`), `cursor.lastrowid` (4 sites each in `lifecycle.py` and `writers.py`), `executemany` (one site each), and `cursor.rowcount` (`hooks/post_tool_use.py`). `in_transaction`, `cursor.description`, `executescript`, `.backup`, and `iterdump` are declared or historically feared but have no consumer in `little_loops` outside `backend.py`/`schema.py`.
- **Error-handling split that bounds "clear capability limitation" and "HistoryError classification".** About 127 `except sqlite3.(Error|OperationalError)` sites across 29 files remain, versus about 33 `HistoryError`/`translate_sqlite_errors` uses across 8 files. `writers.py::SQLiteTransport` catches `HistoryError`, but `writers.py::record_hook_event` in the same file still catches `sqlite3.Error`; `cli/doctor.py::_history_db_data` catches `(sqlite3.Error, HistoryUnavailable)` together. A non-sqlite backend raising only `HistoryError` subclasses will not be caught by the `sqlite3.Error` sites, which is either the intended behavior or a gap depending on each site's best-effort role.
- **In-repo spike is a completed FEAT-3524 artifact and proves only local mechanics.** `scripts/tests/spike/session_store_backend_dialect/` (with plan `.ll/spikes/spike-FEAT-3524.md`) has a `StubRemoteBackend` that is a `sqlite3` connection with an empty capability set and DDL lacking `AUTOINCREMENT`. It proves the migration locking sequence works with per-dialect DDL, `ensure_schema` idempotency, four-thread race convergence, and a capability-gate error that names the capability and backend. It contains no socket, HTTP, batch, or baton code; FEAT-3524's Spike Results state it does not establish remote behavior. Its capability names (`fts5`, `wal`, `vacuum`) differ from production `_SQLITE_CAPABILITIES` (`attach`, `vacuum`, `create_function`); production analogues live in `test_session_store_backend.py` (`TestDialectMigration`, `TestCapabilityGate`, `TestConcurrentMigration`). FEAT-3535 does not currently cite the spike.
- **Migration facts a remote path must preserve (verified).** `schema.SCHEMA_VERSION` is 55 (the `libsql-remote` learning record's 52-migration count is out of date). `_configure_connection` issues `busy_timeout` and `journal_mode = WAL` pragmas, which the learning record found rejected on sqld/Turso, and swallows the failure at debug level. `_current_version` detects a missing schema by matching "no such table" in the error message, and re-raises anything else. Above-current stamps trigger a `_schema_manifest`/`_reference_manifest_at` structural comparison built from `PRAGMA table_info`/`index_list`/`index_info`; that comparison has no remote analogue defined yet. `schema.connect` opens two connections per call (one to migrate, one with `row_factory = sqlite3.Row`).
- **Test files the change must keep green** (in addition to the inherited list): `scripts/tests/test_session_store_backend.py` (`TestResolveBackend`, `TestProtocolConformance` — its docstring anticipates a `libsql` provider — `TestCapabilityGate`), `test_history_store_chokepoint_gate.py`, `test_session_store_writers.py` (ENH-3526 translation test), `test_session_store_lifecycle.py` (monkeypatches `open_history`), `test_config_schema.py` (history block has `additionalProperties: false`, so an undeclared `backend` key is rejected until declared), `test_config.py::TestHistoryConfig`, and `test_wiring_reference_docs.py` / `test_wiring_init_and_configure.py`, which pin per-key doc strings.
- **Conventions in force for the new pieces** (rule first, files as evidence):
  - Provider registries are lazy `(module_path, class_name)` maps whose resolver raises the domain error listing sorted registered names (`session_store/backend.py::_BACKEND_MAP`, `codequery/core.py::_PROVIDER_MAP`, `adapters/core.py::_EMITTER_MAP`); providers satisfy a `@runtime_checkable` Protocol structurally. Contested: `host_runner._HOST_RUNNER_REGISTRY` is an eager class dict and `transport._TRANSPORT_REGISTRY` warns rather than raises on unknown names.
  - Capabilities are plain strings gated by `supports()` with the *caller* raising `HistoryUnsupported` naming the capability and provider (`issue_history/workspace_quality.py`, around the `attach` gate).
  - `HistoryError` subclasses carry no structured fields; the nearest structured-code carriers are `cli/artifact/policy_builder_routes.py::_RouteError.code` and `host_runner.BlockingJsonError.details`. `translate_sqlite_errors` always chains with `from exc`.
  - Outbound HTTP passes one caller timeout to the socket call and classifies in a single function with `HTTPError` before `URLError`, catch-all last (`link_checker.py::_check_url_once`, `_classify_url_error`). `mcp_call.py` is subprocess/stdio JSON-RPC, not HTTP; its `_send_jsonrpc` shows the inline `time.monotonic()` deadline. There is no shared deadline helper anywhere. `http.client` is not used in package source (only in tests); `transport.py::WebhookTransport` uses `httpx` behind an optional extra with the dependency justified beside its pin in `scripts/pyproject.toml`, so a stdlib client is consistent with the minimize-third-party rule.
  - No secret-masking utility exists for config/doctor/log output: `pii.py::redact_pii`/`CREDENTIAL_RULES` cover fixed token shapes (not an arbitrary `Authorization` value) and are used for corpus filtering, and `cli/doctor.py`/`config/features.py` mask nothing. The token-never-echoed requirement noted earlier is therefore a new obligation on the doctor diagnostic, `HistoryConfig.to_dict`, and log lines.
  - `ll-session` subcommands are inline `subparsers.add_parser` blocks in `cli/session.py::_build_parser` (no `_add_*_parser` helper), dispatched through a linear `if args.command` chain inside `cli_event_context`; a new subcommand also touches the module docstring, the parser epilog, and `docs/reference/CLI.md`.
  - Doctor checks: a `_X_data()` dict plus a `@register_check` function, a JSON payload key, and a `_print_X_section()`; an absent optional feature is `unsupported` + `informational`, and only error-severity unsupported yields exit 1. `_history_db_data` currently hard-codes `Path.cwd() / DEFAULT_DB_PATH` and a 16-byte SQLite-header file check before `resolve_backend().connect_readonly`, so a remote target needs its own probe branch.
  - A new `history.*` key touches `config-schema.json`, `HistoryConfig.from_dict` (lenient), `config/core.py` wiring, `docs/reference/CONFIGURATION.md`, and the structural asserts in `test_config_schema.py`/`test_config.py`. Contested: the recent `history.db_path` and `workspace_manifest_path` keys were *not* added to `config/core.py::to_dict()`, `skills/configure/areas.md` `## Area: history`, or `skills/configure/show-output.md`; the inherited Files-to-Modify list (step 7 "configure history-area mirrors") should decide knowingly whether `backend` follows the fuller or the thinner precedent. Skill/README edits trip the mirror gates (`ll-adapt --host <gemini|kimi-code|qwen> --apply`).
  - Test placement: network-client tests use a real stdlib server on `127.0.0.1` port 0 in a daemon thread with `shutdown()` then `server_close()` (`test_flux_image_generator.py::flux_stub`), whereas `test_link_checker.py` mocks `urlopen`; no existing test blackholes a connect. Live-endpoint tests are `pytest.mark.integration` (excluded by `-m "not integration and not conformance"`) and env-gated via a predicate read at fixture time (`tests/conftest.py::_live_conformance_allowed`). `conftest.py` autouse fixtures set `LL_HISTORY_DB` and guard against opening the real `.ll/history.db`, so any non-sqlite test runs with that env already set.
- **Learning-test gate is enforced.** This issue's frontmatter `learning_tests_required` key lists `hrana-http`; its cancelled predecessor listed `libsql` and `libsql-remote`. The key is enforced by `learning_tests/gate.py`/`ll-learning-tests assess`. `hrana-http.md` exists and is proven (2026-09-28); like the stdlib-target record `httpserver.md` it omits `proven_package`/`proven_version` and uses age-based staleness.
- **No other open issue gates this one.** FEAT-3524 is `cancelled` (predecessor), ENH-3525 and ENH-3526 are `done`; no open issue mentions `HistoryTarget`, `history.backend`, or Hrana beyond this one.

## Acceptance Criteria

- [ ] With `history.backend` unset or `provider: sqlite`, the existing history test suite passes unchanged.
- [ ] `resolve_backend("libsql")` returns a `LibsqlBackend`; with `history.backend.provider: libsql`, the chokepoint entry points (`open_history`, `open_history_readonly`, `connect_readonly`) and the hook paths (`main_hooks`, `post_tool_use`) select it without callers passing a provider, and history reads and writes round-trip against a `sqld` endpoint.
- [ ] Every network wait uses a socket-level timeout; a connect to a blackholed host fails within the configured limit and raises a `HistoryError` subclass.
- [ ] Hrana error codes map to `HistoryError` classes without message matching, per the Error Code Mapping table under Program Design: `SQLITE_CONSTRAINT` to `HistoryIntegrityError`; `STREAM_EXPIRED` (sqld) and `SQLITE_BUSY` (Turso idle-transaction rollback) to one retryable stream-lost class; HTTP 400/401/403 and `BLOCKED` to `HistoryUnavailable`; `SQL_PARSE_ERROR` and `SQLITE_UNKNOWN` to `HistoryOperationError`.
- [ ] Unsupported operations (`rebuild`, `prune`, `compact`, `recompress`, `VACUUM`, `ATTACH`, `create_function`, snapshot export) raise `HistoryUnsupported` with an `operation` attribute naming the operation, before any mutation, per the operation matrix under Proposed Design; FTS5 search round-trips against a remote endpoint.
<!-- ll-prose-ok: migrate is a planned new subcommand delivered by this issue -->
- [ ] Under `provider: libsql`, opens never migrate; `ll-session migrate` is the only path that changes the remote schema, and a store behind or ahead of the client raises `HistoryUnsupported` for writes.
- [ ] `backfill_raw_events` under `libsql` reads and writes `meta.last_raw_event_ts:<machine_id>`; the SQLite path keeps the global key.
- [ ] `meta.project_id` is stamped by the migrate command and compared on every remote open; a mismatch raises `HistoryUnsupported`.
- [ ] The auth token never appears in `ll-doctor` output, `HistoryConfig.to_dict`, log lines or `HistoryError` text (asserted by a test that plants a sentinel token).
- [ ] Two concurrent remote migrations, each sent as one atomic `batch` (never an interactive transaction), both complete or one fails with a structured error, leaving exactly one schema-version row.
- [ ] A write that contends with another open transaction is bounded by the client read timeout and raises a `HistoryError` subclass; the client never relies on receiving `SQLITE_BUSY` (both endpoints block until the server reaps the idle holder, sqld ~5s, Turso ~10s).
- [ ] A failing best-effort telemetry write never aborts the observed operation and stays within the telemetry latency budget.
- [x] The `hrana-http` learning test is proven (`ll-learning-tests assess --issue FEAT-3535` exits 0) before any client code lands. Done 2026-09-28: 12 passing assertions, 2 recorded failures that re-scoped the criteria above. Auth-failure assertions were proven on Turso Cloud only, because the local `sqld` ran unauthenticated.
- [ ] Remote integration tests skip only when `LL_TEST_LIBSQL_URL` / `LL_TEST_LIBSQL_AUTH_TOKEN` are absent; `python -m pytest scripts/tests/` exits 0.

## Program Design

### Types

- `HranaClient`: stdlib `http.client` client for `/v3/pipeline` holding base URL, auth token, connect/read timeouts, and the current baton
- `HranaError(HistoryError)`: carries the structured Hrana error `code` and message; a retryable stream-lost subclass covers `STREAM_EXPIRED` and idle-transaction `SQLITE_BUSY`
- `LibsqlBackend`: `Backend` implementation built on `HranaClient`; `supports()` returns False for `attach`, `vacuum`, `create_function`, `wal` and `snapshot_export`

### Error Code Mapping

Observed in `.ll/learning-tests/hrana-http.md` (2026-09-28). Errors arrive in `results[i].error` (`{message, code}`) with HTTP 200, except where noted.

| Observed | Where | `HistoryError` class |
|---|---|---|
| `SQLITE_CONSTRAINT` (PK and NOT NULL) | both | `HistoryIntegrityError` |
| `SQL_PARSE_ERROR`, `SQLITE_UNKNOWN` (missing table) | both | `HistoryOperationError` |
| `STREAM_EXPIRED`: HTTP 400, top-level `{message, code}` body, not in `results` | sqld | retryable stream-lost |
| `SQLITE_BUSY` with "interactive transaction was rolled back because the stream was idle" | Turso | retryable stream-lost |
| HTTP 400 malformed JWT, HTTP 401 empty token | Turso | `HistoryUnavailable` |
| `BLOCKED` (read-only token write) | Turso | `HistoryUnavailable` |
| second `BEGIN IMMEDIATE` under contention | both | no error; blocks until the holder is reaped, so the client read timeout bounds it |

The client must parse both the per-result `error` and the top-level HTTP-error body. Turso cannot distinguish busy from expired by code, so the one stream-lost class is deliberate. Migrations use an atomic `batch` (`begin immediate`, conditional statements, conditional `commit`, `not ok` conditional `rollback`), which serialized four concurrent runs with one schema row.

### Signatures

- `HranaClient.execute(sql: str, params: Sequence[Any] = ()) -> HistoryCursor` — one statement over a pipeline request
- `HranaClient.batch(steps: Sequence[BatchStep]) -> list[StepResult]` — atomic batch with step conditions
- `LibsqlBackend.connect(path: Path | HistoryTarget, *, check_same_thread: bool = True) -> HistoryConnection` — open a remote connection
- `resolve_backend(provider: str = "sqlite") -> Backend` — gains a `"libsql"` branch

### Call Path

`open_history` -> `resolve_backend` -> `LibsqlBackend.connect` -> `HranaClient.execute`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

- `HistoryConnection` (protocol in `session_store/backend.py`) declares only `in_transaction`, `execute`, `executemany`, `commit`, `rollback`, `close`, and forbids consumers assigning `row_factory`. `HistoryCursor` requires `description`, `lastrowid`, `rowcount`, `fetchone/fetchall/fetchmany`, `__iter__`; `HistoryRow` requires `keys()` and `__getitem__`. A Hrana-backed connection and cursor must satisfy exactly these, including name and index access on rows.
- `HistoryTarget` is not yet in code; the signatures above reference it as a type from FEAT-3524 §1a. Until Step 2 lands, `Backend.connect` takes `Path`.
- `resolve_backend(provider: str = "sqlite")` imports lazily through `_BACKEND_MAP` entries of the form (module path, class name) and raises `HistoryUnsupported` for unknown providers; the entry points do not currently accept a provider, so the provider must be sourced from config inside the chokepoint.
- Decision Rules (advisory): capability strings consulted through `supports()` today are `attach`, `vacuum`, `create_function`; the limitation list in Expected Behavior needs a defined capability name per operation, and the raised error must name the operation.

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Signature drift to reconcile.** `Backend.connect`/`connect_readonly`/`ensure_schema` currently take `Path` and return `sqlite3.Connection` (`session_store/backend.py`); the Signatures above assume `Path | HistoryTarget` and `HistoryConnection`. `HistoryTarget` is not in code, and `_resolve_once` returns `Path`, so the target-type change also lands in `open_history`, `open_history_readonly`, and `connect_readonly`.
- **Provider selection has no seam yet.** The three module entry points and four direct callers call `resolve_backend()` with the default provider; `BackendProvider` is `Literal["sqlite"]`. Any design must state where config selects the provider so those callers pick it up without each passing an argument.
- **Capability names to define.** Production `supports()` knows `attach`, `vacuum`, `create_function`; the spike used `fts5`, `wal`, `vacuum`. The Expected Behavior limitations (FTS5, maintenance, snapshot export) need one capability string each, and `HistoryUnsupported` has no field for the operation name, so the naming requirement in Acceptance Criteria implies either a message convention or a new field.
- **Decision Rules (advisory) — resolved 2026-09-28.** Hrana error-code to `HistoryError` class mapping is settled by the `hrana-http` learning test: see Error Code Mapping under Program Design. Busy and expired share one retryable stream-lost subclass (Turso reports an expired idle transaction as `SQLITE_BUSY`), so the four codes do not each get a distinct class.

## Implementation Steps

1. ~~Produce `.ll/learning-tests/hrana-http.md`~~ Done 2026-09-28 (proven; see Error Code Mapping under Program Design).
2. ~~Land the SQLite-only `HistoryTarget` refactor~~ Split out as ENH-3650 (blocks this issue): it
   covers the chokepoint entry points, `_resolve_once`, the target-aware `schema.connect` seam,
   `main_hooks`, `post_tool_use` and the independent `LL_HISTORY_DB` readers.
3. Add the Hrana HTTP client and its unit tests (real stdlib stub server on `127.0.0.1`).
   The client parses both the per-result `error` and the top-level HTTP-error body, and maps
   codes per the Error Code Mapping table.
4. Add `history.backend` config (schema, `HistoryConfig.from_dict`, `config/core.py`),
   source the provider from config inside the chokepoint, define the capability strings
   (`wal`, `snapshot_export` plus the existing three) and the `HistoryUnsupported.operation`
   attribute, make the `schema.connect`/`ensure_db` seam target-aware (fail-closed per the
   operation matrix), and add `LibsqlBackend`.
<!-- ll-prose-ok: migrate is a planned new subcommand delivered by this issue -->
5. Remote migrations via atomic `batch` (no interactive transaction), plus `ll-session migrate`.
6. Operation matrix, per-machine ingestion, telemetry budget, and the doctor diagnostic
   (remote probe branch in `_history_db_data`; the auth token is never echoed by doctor,
   `HistoryConfig.to_dict`, or logs).
7. Docs and the `/ll:configure` history-area mirrors (run `ll-adapt` mirror gates after
   skill/README edits).

## Impact

- **Priority**: P4. Opt-in, nice to have, and nothing depends on it.
- **Effort**: Large. It inherits FEAT-3524's remaining scope and adds a protocol client
  to own.
- **Risk**: Medium until the `hrana-http` learning test passes. The team owns the
  protocol client and must follow protocol changes.
- **Breaking Change**: None. Remote support is opt-in.

## Use Case

A developer runs little-loops on a laptop and on the self-hosted CI runner. They set
`history.backend.provider: libsql` with `url_env` / `auth_token_env` in `.ll/ll.local.md`.
Both machines then write to and read from the same remote store, through `ll-history`,
`ll-logs`, session digests and compaction context. An unreachable endpoint never stalls a
hook past its latency budget.

## Related

- FEAT-3524 (cancelled; its Decision Rationale records this route as Option A)
- ENH-3525, ENH-3526 (chokepoint prerequisites, done)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-28 (re-score after ENH-3650 landed in 0284bd4ad)_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- The `hrana-http` record is `proven` but carries 2 contradicted claims (expired-stream code on Turso; `SQLITE_BUSY` under write contention). The criteria already absorb both, but the rubric keeps a -5 modifier on the duplicate-implementation score while any claim is contradicted.
- Two conditional items are settled only as tests: the copied-session double-ingest check, and dedup keys for derived tables that have none.
- Some Codebase Research Findings still describe the pre-ENH-3650 chokepoint (path-typed signatures, `_resolve_once` returning `Path`). The seam is now target-aware; `BackendConfig` is a minimal two-field placeholder (`provider`, `url`) that this issue must extend for `url_env`, `auth_token_env`, `project_id` and `telemetry_timeout_ms`.

### Outcome Risk Factors
- Broad enumeration across roughly 10 files in Files to Modify (new client module, backend registration, config schema and wiring, migrate subcommand, doctor branch, ingestion worker).
- Moderate per-site complexity: a new protocol client with baton, batch and error-code handling, plus a remote migration path.

## Session Log
- `/ll:confidence-check` - 2026-09-29T03:00:46 - `4d45d755-73ff-4de3-8bd1-bb8e866143f2.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:44:43 - `82825f0f-e592-4590-85b9-5a65863337be.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:39:42 - `82825f0f-e592-4590-85b9-5a65863337be.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:35:02 - `73686e01-7e81-40c2-bf94-43634394b513.jsonl`
- `/ll:verify-issues` - 2026-09-29T02:33:55 - `82825f0f-e592-4590-85b9-5a65863337be.jsonl`
- `/ll:reconcile-issue` - 2026-09-29T02:31:02 - `efa5da7e-d183-4626-be25-08b53ab75362.jsonl`
- `/ll:verify-issues` - 2026-09-29T02:24:24 - `82825f0f-e592-4590-85b9-5a65863337be.jsonl`
- `/ll:refine-issue` - 2026-09-29T01:36:58 - `53ec1cbf-a55d-477a-91f3-8081b28d4c2d.jsonl`
- `/ll:refine-issue` - 2026-09-24T00:55:16 - `851cba84-d70b-4baa-8370-ffdce9646511.jsonl`
- `/ll:format-issue` - 2026-09-24T00:50:45 - `037fa15a-ec40-4d82-9ee3-839372456150.jsonl`
- `/ll:capture-issue` - 2026-09-24T00:46:36 - `037fa15a-ec40-4d82-9ee3-839372456150.jsonl`
