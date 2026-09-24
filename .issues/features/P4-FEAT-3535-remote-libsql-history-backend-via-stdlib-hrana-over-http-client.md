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

1. **Gate first:** produce a new learning test, `.ll/learning-tests/hrana-http.md`, against
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

## Implementation Steps

1. Produce `.ll/learning-tests/hrana-http.md` (prerequisite gate).
2. Land FEAT-3524 §1a's SQLite-only `HistoryTarget` refactor, with no behavior change.
3. Add the Hrana HTTP client and its unit tests.
4. Add `history.backend` config and `LibsqlBackend`.
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
- `/ll:capture-issue` - 2026-09-24T00:46:36 - `037fa15a-ec40-4d82-9ee3-839372456150.jsonl`
