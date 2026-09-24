---
id: FEAT-3535
type: FEAT
title: Remote libSQL history backend via stdlib Hrana-over-HTTP client
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:46:29Z'
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
- Unsupported operations report a clear capability limitation. These include FTS5 and
  maintenance operations, `ATTACH`, `create_function`, and snapshot export.
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
4. Reuse FEAT-3524's Proposed Design, which was already reviewed and settled:
   - `history.backend` config and its precedence rules (§1);
   - `HistoryTarget` target-type refactor (§1a);
   - `LL_HISTORY_DB` env relay (§1b);
   - shared-store operation matrix (§7);
   - per-machine ingestion watermark and incremental materialization (§7a);
   - telemetry latency budget (§8);
   <!-- ll-prose-ok: migrate is a planned new subcommand delivered by this issue -->
   - `ll-session migrate` and no migrate-on-open (§9);
   - project-identity stamp (§10);
   - the `ll-doctor` backend diagnostic.

   Where those sections assumed the `libsql` binding (e.g. the isolation-level workaround,
   `executescript` avoidance), re-derive them against the Hrana client.

## Integration Map

### Files to Modify
- `little_loops/session_store/backend.py`: register `LibsqlBackend`; move to the
  `HistoryTarget` target type.
- New module for the Hrana HTTP client, beside `session_store/backend.py`.
- The remaining Files to Modify, Dependent Files, Tests and Documentation lists are
  inherited from FEAT-3524's Integration Map, which was verified 2026-09-22/23.

### Tests
- New learning test `hrana-http` (prerequisite).
- Remote integration tests selected by `LL_TEST_LIBSQL_URL` + `LL_TEST_LIBSQL_AUTH_TOKEN`:
  they skip only when that configuration is absent, and a failure against a configured
  endpoint fails the test.
- Unit tests for the Hrana client against a local stub HTTP server: timeouts, error-code
  mapping, batch encoding.

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
- Learning tests are markdown files under `.ll/learning-tests/` with frontmatter (`target`, `date`, `status`, `assertions` of claim/result, `raw_output_path`, `proven_package`, `proven_version`), managed by `ll-learning-tests` (`check`, `prove`, `list`, `mark-stale`). `libsql-remote.md` exists; `hrana-http.md` does not.

## Acceptance Criteria

- [ ] With `history.backend` unset or `provider: sqlite`, the existing history test suite passes unchanged.
- [ ] `resolve_backend("libsql")` returns a `LibsqlBackend`; history reads and writes round-trip against a `sqld` endpoint.
- [ ] Every network wait uses a socket-level timeout; a connect to a blackholed host fails within the configured limit and raises a `HistoryError` subclass.
- [ ] Hrana error codes (`SQLITE_CONSTRAINT`, `SQLITE_BUSY`, `STREAM_EXPIRED`, auth failure) map to distinct `HistoryError` classes without message matching.
- [ ] Unsupported operations (FTS5, maintenance, `ATTACH`, `create_function`, snapshot export) raise a capability-limitation error naming the operation.
- [ ] Two concurrent remote migrations serialize or one fails safely, leaving the schema consistent.
- [ ] A failing best-effort telemetry write never aborts the observed operation and stays within the telemetry latency budget.
- [ ] The `hrana-http` learning test passes against `sqld` and Turso Cloud before any client code lands.
- [ ] Remote integration tests skip only when `LL_TEST_LIBSQL_URL` / `LL_TEST_LIBSQL_AUTH_TOKEN` are absent; `python -m pytest scripts/tests/` exits 0.

## Program Design

### Types

- `HranaClient`: stdlib `http.client` client for `/v3/pipeline` holding base URL, auth token, connect/read timeouts, and the current baton
- `HranaError(HistoryError)`: carries the structured Hrana error `code` and message
- `LibsqlBackend`: `Backend` implementation built on `HranaClient`; `supports()` returns False for FTS5, maintenance, `ATTACH`, `create_function`, and snapshot export

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
- `HistoryTarget` does not exist in code; the signatures above reference it as a type from FEAT-3524 §1a. Until Step 2 lands, `Backend.connect` takes `Path`.
- `resolve_backend(provider: str = "sqlite")` imports lazily through `_BACKEND_MAP` entries of the form (module path, class name) and raises `HistoryUnsupported` for unknown providers; the entry points do not currently accept a provider, so the provider must be sourced from config inside the chokepoint.
- Decision Rules (advisory): capability strings consulted through `supports()` today are `attach`, `vacuum`, `create_function`; the limitation list in Expected Behavior needs a defined capability name per operation, and the raised error must name the operation.

## Implementation Steps

1. Produce `.ll/learning-tests/hrana-http.md` (new) (prerequisite gate).
2. Land FEAT-3524 §1a's SQLite-only `HistoryTarget` refactor, with no behavior change.
3. Add the Hrana HTTP client and its unit tests.
4. Add `history.backend` config and `LibsqlBackend`.
<!-- ll-prose-ok: migrate is a planned new subcommand delivered by this issue -->
5. Remote migrations via atomic `batch`, plus `ll-session migrate`.
6. Operation matrix, per-machine ingestion, telemetry budget, and the doctor diagnostic.
7. Docs and the `/ll:configure` history-area mirrors.

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


## Session Log
- `/ll:refine-issue` - 2026-09-24T00:55:16 - `851cba84-d70b-4baa-8370-ffdce9646511.jsonl`
- `/ll:format-issue` - 2026-09-24T00:50:45 - `037fa15a-ec40-4d82-9ee3-839372456150.jsonl`
- `/ll:capture-issue` - 2026-09-24T00:46:36 - `037fa15a-ec40-4d82-9ee3-839372456150.jsonl`
