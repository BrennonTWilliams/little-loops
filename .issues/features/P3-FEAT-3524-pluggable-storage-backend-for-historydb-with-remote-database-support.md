---
id: FEAT-3524
type: FEAT
title: Pluggable history.db backend with remote libSQL support
priority: P3
status: cancelled
decision_needed: false
discovered_by: ll-issues-create
discovered_date: '2026-09-22'
captured_at: '2026-09-22T15:39:38Z'
learning_tests_required:
- libsql
- libsql-remote
spike_attempted: true
spike_completed: true
verify_verdict: VALID
confidence_score: 80
outcome_confidence: 43
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 0
missing_artifacts: true
---

# FEAT-3524: Pluggable history.db backend with remote libSQL support

## Summary

Allow little-loops users to share a history store across machines running the same
project by configuring a remote libSQL database through `history.backend` in
`.ll/ll-config.json`. Preserve local SQLite as the unchanged default. This issue
adds the `libsql` adapter, the `history.backend` configuration, the doctor
diagnostic, and the shared-store safety rules on top of the SQLite-only chokepoint
delivered by ENH-3525 (Phase A). Postgres, MySQL, other Turso engines/drivers, and
embedded-replica synchronization are out of scope.

## Blocked By

- Both Phase A/A2 connection-chokepoint blockers were satisfied — ENH-3525 and
  ENH-3526 merged `status: done` on 2026-09-22 (removed from frontmatter
  `blocked_by` 2026-09-23); see Current Behavior for what they delivered and
  Verification Notes for the codebase verification.
- `.ll/learning-tests/libsql-remote.md` — **produced 2026-09-23 (Step 1), and 7
  required assertions failed.** Per the §2 Step 1 failure contingency this issue is
  `blocked` pending a re-scope decision (`decision_needed: true`). See
  [Step 1 Learning Test Result](#step-1-learning-test-result-2026-09-23).

## Step 1 Learning Test Result (2026-09-23)

Implementation Step 1 ran against both planned endpoints with `libsql` 0.1.11
(Python 3.12): a self-hosted `sqld` 0.24.8 (`http://`, SQLite 3.44.0, JWT auth) and
Turso Cloud (`libsql://…aws-us-east-2.turso.io`, SQLite 3.47.0). Record:
`.ll/learning-tests/libsql-remote.md` (`proven`, 24 claims — 12 pass / 12 fail,
`proven_package: libsql`, `proven_version: 0.1.11`). Raw output (gitignored):
`.ll/learning-tests/raw/libsql-remote.txt`. Both endpoints behaved the same except
where noted, so the "Turso Cloud governs" tie-break was never needed.

**Required assertions that passed:** direct remote mode (`connect(url,
auth_token=…)`; `connect()` is lazy — no network until the first execute); bad or
missing token fails in <0.35 s; `connect(isolation_level=None)` + explicit
`BEGIN IMMEDIATE`/`COMMIT` with correct `in_transaction`; rollback after a
mid-migration failure leaves `meta.schema_version` unchanged; the full `_MIGRATIONS`
chain (52 migrations / 244 statements incl. FTS5) applies from empty in one
transaction (sqld 4.7 s, Turso 26.2 s) and repeats as a no-op; `PRAGMA table_info` /
schema-version reads; `INSERT OR IGNORE`/`executemany`/`lastrowid`/`rowcount`/
`description`; one connection shared across threads under a lock; ambiguous commit is
detectable (sqld via a response-dropping proxy: the client raises
`ValueError: connection closed before message completed` while the commit landed; an
idempotent marker re-read detects it; the client's `in_transaction` stays stale
`True`). Latency medians: sqld cold 103 ms / warm 20 ms; Turso cold 339 ms / warm
79 ms. Each `execute()` is two HTTP round trips (`describe` + `batch`).

**Required assertions that failed (contingency triggers):**

| # | Failure | Source | Design impact |
|---|---|---|---|
| F1 | No bounded connect to an unreachable host: `connect(timeout=)` is ignored; a blackholed IP blocks the first execute ~75 s (OS TCP timeout). Refused ports / unknown Turso hosts fail in <0.4 s | driver | §8 telemetry budget unenforceable in-process |
| F2 | The driver **holds the GIL** for the whole network call — every thread in the process freezes, so no thread-based deadline can bound F1/F5 | driver | §8; also stalls `SQLiteTransport`'s background thread |
| F3 | `Connection.isolation_level` is read-only after connect (`AttributeError`); only `connect(isolation_level=…)` sets it | driver | `_apply_migrations` cannot be reused unchanged (§4) |
| F4 | Two concurrent initializers do not serialize: the lock-waiter's interactive transaction is aborted server-side (sqld `TRANSACTION_TIMEOUT` ~5 s; Turso `SQLITE_BUSY` "stream idle" ~10 s) and its `ROLLBACK` then raises "no transaction is active". Final schema is correct; a naive retry livelocked on Turso (>120 s) | server | §9's explicit `ll-session migrate` makes this rarer but two concurrent `migrate` runs remain unsafe |
| F5 | No statement timeout: a 60–87 s query ran despite `timeout=1.0`; no API exists | driver | §8 |
| F6 | Idle connections die: sqld expires the stream after ~10 s idle (`STREAM_EXPIRED`, permanent — the connection must be replaced); Turso rolls back an interactive transaction idle ~10 s | server | long-lived connections (`SQLiteTransport`, cached per-process connections) need reconnect-on-expiry |
| F7 | `executescript` **silently swallows every error** in remote mode, stops at the first failure, and can leave a transaction open | driver | never usable for migrations or batch writes |

Also confirmed: every error is a plain `builtins.ValueError` carrying a
Hrana-formatted message with the SQLite/Hrana code only in the text (e.g.
`SQLITE_CONSTRAINT`, `SQLITE_BUSY`, `STREAM_EXPIRED`, `TRANSACTION_TIMEOUT`) — the §3
error contract stands. **Probes** (non-blocking): FTS5 + `MATCH` + `bm25()` work on
both; `PRAGMA journal_mode`/`busy_timeout`/`query_only`, `ATTACH`, `VACUUM`, and
`create_function` are unsupported on both.

**Re-scope options (decision needed — do not switch drivers mid-implementation):**

- **Option A — Stdlib Hrana-over-HTTP client (recommended to evaluate first).** F1, F2, F3,
   F5, F7 are properties of the `libsql` 0.1.11 binding, not the protocol. A small
   client on `http.client`/`urllib` speaking `/v3/pipeline` gets real socket
   timeouts, releases the GIL, returns structured Hrana error codes (making the §3
   classification reliable instead of message-matching), and adds no dependency.
   Server-side atomic `batch` requests (with step conditions) could replace the
   interactive migration transaction, sidestepping F4/F6 for migrations. Cost: we own
   a protocol client. Needs its own learning test (e.g. `hrana-http`) proving batch
   atomicity, concurrent `migrate`, and error codes before design changes land.
- **Option B — Keep `libsql`, contain it out of process.** Run every remote call in a bounded
   subprocess (or a pre-flight `socket.create_connection(timeout=…)` check) to satisfy
   §8; reconnect on `STREAM_EXPIRED`; open with `isolation_level=None`; serialize
   `migrate` with an advisory lock row. Cheapest code change, but a per-hook
   subprocess adds latency on top of the 339 ms cold connect, and F5 stays open.
- **Option C — Embedded replicas** (`sync_url`) — local reads/writes against a replica file,
   syncing to the remote. Avoids per-call network latency but is currently out of
   scope (§11) and needs a separate learning test of write-forwarding semantics.
- **Option D — Descope remote support** and close the libSQL half of this issue.
  > **Selected:** (D) — descope; driver immaturity (7 failed required assertions) outweighs a P3 opt-in feature with no downstream dependents

## Current Behavior

_As of 2026-09-22, ENH-3525 and ENH-3526 have both merged (`status: done`) and
delivered the consolidated chokepoint this section originally described as
absent: `session_store/backend.py` now defines `Backend`/`SqliteBackend`,
`resolve_backend()`, `open_history()`/`open_history_readonly()`,
`connect_readonly()`, and the `HistoryError` taxonomy
(`HistoryUnavailable`/`HistoryIntegrityError`/`HistoryUnsupported`/`HistoryOperationError`).
Raw `sqlite3.connect(` call sites outside `session_store/backend.py` itself are
down to 7 files (`queue_store.py`, `codequery/codegraph.py` — deliberately
out of scope per this issue's own audit-only note; `session_store/{schema,
sessions,queries}.py` and `issue_history/workspace_quality.py` — the sites this
issue's wiring passes already name for migration onto the chokepoint). See
Verification Notes for detail. `BackendProvider` is currently
`Literal["sqlite"]` — no `libsql` entry exists yet, and `history.backend` is
not yet in `config-schema.json` — both remain this issue's own scope, unchanged
by ENH-3525/ENH-3526._

`history.db` is always a local SQLite file. `history.db_path` (`config-schema.json`
`history` block) only overrides the local filesystem path — relative paths resolve
against the project root and `LL_HISTORY_DB` takes precedence (ENH-2623), resolved by
`little_loops.session_store.db._resolve_db_path` / `resolve_history_db`. The
chokepoint is path-typed end to end and returns `sqlite3.Connection`; the only
registered backend is `SqliteBackend`, and consumers still rely on SQLite-specific
features (`file:{path}?mode=ro` URIs, WAL PRAGMAs, FTS5, `ATTACH`, Python UDFs). There
is no way to point `history.db` at a network-accessible database instead of a local
file.

Session/transcript data reaches the store only through ingestion:
`hooks/session_start.py` spawns the backfill worker, which calls
`session_store/lifecycle.py` `backfill_incremental()` → `backfill_raw_events()` (`INSERT OR IGNORE` into the
raw-events table, keyed on `(source_path, line_no)`, then advances a single global
`meta.last_raw_event_ts` watermark, `lifecycle.py:857`). The derived cache tables in
`_REBUILD_TABLES` (`lifecycle.py:940`: `tool_events`, `message_events`,
`assistant_messages`, `skill_events`, `sessions`, `user_corrections`,
`summary_nodes`, `summary_spans`) are materialized from `raw_events` by `rebuild()` —
a `DELETE`-then-replay — which the worker runs (`--rebuild`) when `SCHEMA_VERSION`
has advanced past `meta.last_rebuild_version`.

## Expected Behavior

An unset `history.backend` or `provider: sqlite` preserves today's local behavior.
With `provider: libsql`, `ll-history`, `ll-logs`, session digests, context-compaction
reads and writes (`little_loops.compaction`, e.g. `compaction/instant.py` — distinct from
the `ll-session compact` raw-event rewrite, which §7 rejects), and event sinks use the
configured remote history store. Unsupported
FTS5/maintenance/export operations report a clear capability limitation rather
than crashing or silently using a different local store. Compatibility is proven
for the selected remote driver and deployment, not inferred from SQLite syntax.

Best-effort telemetry must not abort the operation it observes; explicit reads,
migrations, and maintenance must expose actionable failures. `ll-doctor` provides
an explicit, bounded, non-mutating connectivity/authentication/schema diagnostic.

## Motivation

Teams running little-loops across several machines or CI runners (e.g. the self-hosted runner) have no way to share one history/analytics store. A remote backend enables cross-machine `ll-history` / `ll-logs` analytics, session digests, and compaction context without syncing `.db` files, and unblocks hosted dashboards reading the same store.

## Proposed Solution

Introduce `history.backend` with `provider: sqlite|libsql`, endpoint settings
`url`/`url_env`, `auth_token_env`, `project_id` (required for `libsql`), and
`telemetry_timeout_ms`. Register a `LibsqlBackend` in the
`resolve_backend()` registry that ENH-3525 lands, implementing the same
`Backend` protocol, `HistoryError` taxonomy, and backend-aware entry points.
Classified history consumers already route through that chokepoint; this issue
makes the chokepoint select the remote adapter when configured, and preserves
deliberately local stores, explicit local targets, and scratch artifacts.

Reuse compatible SQL and the existing migration sequence only after the
`libsql-remote` learning test proves it against a real endpoint. Capability
handling must cover connection setup, read-only access, search, maintenance,
snapshot export, and — as a hard gate — shared-store mutation safety (see the
operation matrix under Proposed Design). A connection chokepoint does not remove
SQL, filesystem, transaction, or network-latency assumptions.

### Decision Rationale

**Decision point:** Step 1 re-scope (Options A–D)

Decided by `/ll:decide-issue` on 2026-09-23.

**Selected**: Option D — Descope remote support

**Reasoning**: The reusable groundwork (connection chokepoint, `HistoryError` taxonomy,
path repairs) already shipped in ENH-3525/ENH-3526 and stands on its own; no other
issue lists FEAT-3524 in `blocked_by`/`depends_on`. The remaining work was already rated
Large effort / Medium-high risk before the `libsql` 0.1.11 driver failed 7 required
assertions (F1–F7), and CLAUDE.md's minimize-dependencies rule argues against adopting a
defect-laden driver for a P3 opt-in feature. Option A (stdlib Hrana-over-HTTP client) is
the viable path if remote history is revisited; it is captured as FEAT-3535, gated on its own
`hrana-http` learning test.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Stdlib Hrana-over-HTTP client | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| B — Contain `libsql` out of process | 1/3 | 2/3 | 1/3 | 1/3 | 5/12 |
| C — Embedded replicas | 0/3 | 1/3 | 1/3 | 0/3 | 2/12 |
| D — Descope remote support | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- A: `link_checker.py:256` (`urllib` with bounded timeouts, classified errors) and `mcp_call.py:75` (hand-rolled JSON-RPC client with deadline) are precedents; but no `http.client` usage or Hrana implementation exists, and it needs a new learning test before design lands.
- B: No precedent for sandboxing an in-process library call in a subprocess or for `socket.create_connection` pre-flight; most hooks run on a 5 s budget (`hooks/hooks.json`); F5 (no statement timeout) stays open.
- C: Explicitly out of scope four times (Summary, §2, §11, options list); single-truth `meta.schema_version` / `last_raw_event_ts` assumptions (`schema.py:1492`, `lifecycle.py:857`) conflict with replica sync.
- D: No downstream dependents (repo-wide `FEAT-3524` grep); ENH-3525/ENH-3526 `done`; issue's own Impact section rates remaining work Large / Medium-high risk.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/backend.py` (created by ENH-3525) — add `LibsqlBackend` to the registry; `libsql` adapter module may live beside it
- `scripts/pyproject.toml` — justified `libsql` extras entry after driver proof
- `little_loops/session_store/__init__.py` — preserve public connection/path contracts
- `little_loops/issue_manager.py` and other `SQLiteTransport` constructors — target resolution and lifecycle
- `little_loops/session_store/db.py` (`_resolve_db_path`, `resolve_history_db`)
- `little_loops/session_store/schema.py` (`ensure_db`, `_configure_connection`, `_apply_migrations`)
- `little_loops/session_store/{sessions,queries,lifecycle,writers}.py`
- `little_loops/history_reader/_base.py`
- `little_loops/issue_history/*`
- `little_loops/cli/{history,logs,doctor,doctor_trim,ctx_stats}.py`
- `little_loops/queue_store.py`, `little_loops/codequery/codegraph.py` — audit only to distinguish history consumers from independent local stores; do not migrate `queue.db` or codegraph databases
- `little_loops/config-schema.json` (`history` block, line 2138 — add `backend` with a `provider` enum selector, matching `sync.provider` / `code_query.provider`)

_Wiring pass added by `/ll:wire-issue`:_
- `little_loops/cli/session.py` — `help=` strings hardcode SQLite feature names for FTS5/VACUUM (`:117`, `:118`, `:269`, `:356`, `:368`); must stay accurate or become conditional once these features are capability-gated on non-sqlite backends [Agent 2 finding]
- _Done by ENH-3525/ENH-3526 (verified 2026-09-22, no longer in scope):_ `cli/doctor.py`
  `_schema_drift_data()` (now `resolve_history_db()` + `resolve_backend().connect_readonly`),
  `cli/history.py` `root` handler (now `connect_readonly`),
  `issue_history/workspace_quality.py` `_open_member_readonly()` (now
  `resolve_backend().connect_readonly`).

_Second wiring pass added by `/ll:wire-issue`:_
- _Done by ENH-3525/ENH-3526 (verified 2026-09-22, no longer in scope):_
  `decisions.py` `generate_from_completed()` (now `resolve_history_db(root=...)`) and
  `history_reader/_base.py` `_connect_readonly()` (now `open_history_readonly(ensure=True)`,
  BUG-3181 no-re-resolve contract preserved by `_resolve_once`). Remaining libsql work
  there: `resolve_history_db()` raising `HistoryBackendNotLocal` under `libsql` must be
  handled by `decisions.py`'s DB-vs-filesystem fallback so it reads the remote store
  rather than silently scanning the filesystem.
- `little_loops/issue_history/parsing.py` — `scan_completed_issues_from_db()` and `HistoryDbUnavailable`, called from the `decisions.py` coupling above; previously covered only implicitly by the `issue_history/*` wildcard [Agent 1 finding]
- `little_loops/session_store/backend.py` — `Backend` protocol (`:148-150`), `_resolve_once()` (`:233`), and `connect_readonly()`/`open_history()`/`open_history_readonly()` (`:257-311`) are path-typed and return `sqlite3.Connection`; the target-type refactor (Proposed Design §1a) lands here
- `little_loops/worktree_utils.py:336` — `os.environ.setdefault("LL_HISTORY_DB", str(resolve_history_db()))` relay before worktree creation; under `libsql` it must not raise and must not export a local path (Proposed Design §1b)
- `little_loops/hooks/session_start.py:146` and `little_loops/pytest_history_plugin.py:45` — read `LL_HISTORY_DB` directly; same relay rule applies
- `little_loops/cli/session.py` — add a new `migrate` subcommand (backed by `migrate_history()`, Proposed Design §9); `ll-session` has no migrate subcommand today
- `little_loops/history_reader/formatting.py:55` (`ll_grep`) — registers a Python UDF `regexp_match` via `conn.create_function` and calls it inside SQL; cannot execute on a remote server (Proposed Design §5)

_Review pass — 2026-09-23:_
- `little_loops/hooks/session_start.py:145-200` — **split-brain writer, not just an env reader.** Builds `_db_path` as `LL_HISTORY_DB` or a hardcoded `root / ".ll" / "history.db"` (bypasses `history.db_path` and the chokepoint), passes it as the backfill worker's positional DB arg, and reads `meta.last_rebuild_version` via `connect(_db_path)` (migrate-on-open). Under `libsql` the worker would ingest into a local DB. Must resolve a `HistoryTarget`, pass the remote target to the worker (e.g. omit the positional path / pass a sentinel the worker resolves through config), never append `--rebuild`, and never migrate on open (Proposed Design §7a, §9)
- `little_loops/cli/backfill_worker.py` — accept a remote target; refuse `--rebuild` under `libsql`
- `little_loops/session_store/lifecycle.py` — `backfill_raw_events()`/`backfill_incremental()` global `last_raw_event_ts` watermark (`:857`, `:1123`, `:1175`) → per-machine key under `libsql`; new additive incremental materialization of `_REBUILD_TABLES` rows for newly ingested raw-event rows (Proposed Design §7a)
- `little_loops/session_store/db.py` `_config_db_path()` (`:35-69`) — reads `ll-config.json` with raw `json.loads`, **no `.ll/ll.local.md` merge**. The new `history.backend` reader must not copy this pattern (Proposed Design §1)
- `.gitignore` and `little_loops/init/writers.py` `_GITIGNORE_ENTRIES` (`:98`) — ignore the §8 unreachable marker and verification cache in this repo and in consuming projects (or name them to match an existing ignored glob such as `.ll/*.lock`)

### Dependent Files (Callers/Importers)
- The ~28 `sqlite3.connect(` call sites enumerated above are themselves the
  inventory to classify; only history-store callers move behind the new chokepoint;
  also audit filesystem operations and explicit-path callers; connection counts
  alone do not define the implementation scope.

_Wiring pass added by `/ll:wire-issue`:_
- `little_loops/session_store/__init__.py:79-151` — re-exports `connect`, `ensure_db`, `resolve_history_db`, and other backend-relevant symbols from `db.py`/`schema.py`/`lifecycle.py`/`queries.py`/`writers.py`/`sessions.py`; this is the package's public API surface, now explicitly included in Files to Modify [Agent 1 finding]
- `little_loops/cli/artifact/dashboard.py:35,42` — imports `session_store.queries.build_snapshot_db` and `session_store.schema.SCHEMA_VERSION` directly, bypassing the `session_store/__init__.py` re-export surface; downstream consumers `little_loops/cli/artifact/serve.py`, `little_loops/cli/artifact/__init__.py`, and `little_loops/cli/loop/run.py:634,675` (`render_live_fragment`) build on it [Agent 1 + Agent 2 finding]
- `little_loops/user_messages.py:14,35,495,747,797,923,1191,1192` — imports `detect_sessions`, `SessionHandle`, `host_layout_for`, `iter_events`, `DEFAULT_DB_PATH`, `resolve_history_db` from `session_store` [Agent 1 finding]
- ~19 further production modules import `little_loops.session_store`'s public re-export surface (`resolve_history_db`, `connect`, `ensure_db`, `record_*` event writers, `REGISTERED_HOSTS`, `SQLiteTransport`, etc.) and need a caller-contract audit: `connect()` returns a connection but `ensure_db()` currently returns a path; preserve local behavior and adapt remote callers explicitly: `little_loops/worktree_utils.py:334`, `little_loops/mcp_server/tools.py:158-172`, `little_loops/work_verification.py:278-280`, `little_loops/issue_manager.py:52`, `little_loops/transport.py:2024`, `little_loops/cli_args.py:352`, `little_loops/pytest_history_plugin.py:126`, `little_loops/runner_spec.py:323,326`, `little_loops/parallel/orchestrator.py:44`, `little_loops/parallel/merge_coordinator.py:28`, `little_loops/parallel/worker_pool.py:27`, `little_loops/init/cli.py:16`, `little_loops/compaction/instant.py:128`, `little_loops/compaction/result.py:43,100`, `little_loops/advisor.py:478`, `little_loops/fsm/executor.py:1946,2013,2630,4368,4393`, `little_loops/fsm/continuity.py:16`, `little_loops/hooks/{pre_compact,subagent_stop,session_start,sweep_stale_refs}.py`, `little_loops/workflow_sequence/io.py:47`, `little_loops/__init__.py:75` [Agent 1 finding]
- `hooks/scripts/context-monitor.sh:56,82` — a shell hook with inline Python importing `record_session_lifecycle_event`/`record_context_pressure_event`, `resolve_history_db` from `session_store`; outside the Python package, easy to miss during the chokepoint migration [Agent 1 finding]

_Second wiring pass added by `/ll:wire-issue`:_
- `little_loops/cli/{adapt,adapt_agents_for_codex,adapt_skills_for_codex,advise,auto,code,config,create_extension,deps,docs,generate_skill_descriptions,gitignore,help,migrate,migrate_labels,migrate_relationships,migrate_status,queue,schemas,sync,verify_cli_allowlist,verify_decisions,verify_des_audit,verify_design_tokens,verify_evidence,verify_host_map,verify_package_data,verify_private_refs,verify_skill_prose,verify_triggers}.py`, `little_loops/cli/issues/__init__.py`, `little_loops/cli/loop/__init__.py`, `little_loops/cli/sprint/__init__.py`, `little_loops/hooks/user_prompt_submit.py` — ~35 modules with an identical module-scope `from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context` wrapping `main()` in the analytics context manager; found via codegraph `importers_of` seed, confirmed by grep, not previously enumerated [Agent 1 finding]
- `little_loops/cli/action.py:17-23` — also imports `record_review_event`, `record_verdict_event`, `skill_event_context`
- `little_loops/cli/compact_session.py:24` — also imports `compact_session`; `main_compact_session()` builds `args.db` from `DEFAULT_DB_PATH` as a `Path`-typed argparse default (`:44`) threaded into both `cli_event_context` and `compact_session()`
- `little_loops/cli/harness.py:48-54` — also imports `connect`, `record_attempt`, `record_harness_event`, plus 5 lazy inline `resolve_history_db` imports (`:238,1081,1992,2024,3338`)
- `little_loops/cli/messages.py:11,29` — module-scope pair plus lazy `detect_sessions`, `explain_no_sessions`
- `little_loops/cli/parallel.py:34,318` — module-scope pair plus lazy `SQLiteTransport`, `resolve_history_db`
- `little_loops/cli/sprint/run.py:25,657,796` — `record_orchestration_run`, `resolve_history_db` at module scope, plus two lazy `SQLiteTransport` imports
- `little_loops/cli/verify_kinds.py:22-23,48,56-57` — `from little_loops import session_store` (whole-module import) walking private attrs `session_store._MIGRATIONS`, `session_store._KIND_TABLE`, `session_store._KINDLESS_TABLES` — schema-internal access beyond the connect/ensure_db chokepoint
- `little_loops/cli/learning_tests.py:8,198` — module-scope pair plus lazy `record_learning_test_event`
- `little_loops/cli/history_context.py:43-48` — separate `ll-history-context` entry point (distinct from `cli/history.py`), module-scope `DEFAULT_DB_PATH, cli_event_context, connect, normalize_issue_id`
- `little_loops/cli/issues/set_status.py:151-158` — lazy import in `cmd_set_status`: `record_issue_event`, `record_issue_snapshot`, `resolve_history_db`
- `little_loops/cli/issues/research_triage.py:104` — lazy import in `cmd_research_triage`: `resolve_history_db`, `write_research_triage`
- `little_loops/cli/backfill_worker.py:52,70,78` — three lazy imports inside `main(argv)`: `REGISTERED_HOSTS`, `host_layout_for`, `backfill_incremental`; not previously named anywhere in the issue [Agent 1 finding]
- `little_loops/issue_history/{_utils.py,quality_regressions.py:169,workspace_activity.py,rework.py,evolution.py}` — additional `conn: sqlite3.Connection`-typed functions beyond the already-cited `_open_member_readonly()`/`_open_db()`: `_utils.orchestrator_labels()`, `quality_regressions` conn param, `workspace_quality._attach_limit/_union_view_sql/_open_union/_open_memory`, `workspace_activity._has_any_history()` + 3 window helpers, `rework._load_issue_events()`/`_load_commits()`, `evolution._get_session_ids_for_content()` [Agent 2 finding]
- `little_loops/history_reader/digest.py` — `_query_touched_files()`, `_query_completed_issues()`, `_query_recurring_corrections()`, all `conn: sqlite3.Connection`-typed [Agent 2 finding]
- `little_loops/loops/lib/cli.yaml:59-68` (`ll_history_summary` fragment, exit-code gate) — used via `from:` by `little_loops/loops/evaluation-quality.yaml:46` and `little_loops/loops/backlog-flow-optimizer.yaml:35`; both redirect stderr with `|| echo "(no history available)"`, but still depend on `ll-history summary` exiting 0 on a reachable-but-degraded remote backend [Agent 2 finding]
- `little_loops/loops/fleet-loop-improve.yaml:53,78,80` — parses `ll-logs fleet-review ... | tail -n 1` stdout as a report path; a backend-aware `ll-logs` must preserve this final-line-is-a-path contract [Agent 2 finding]

### Similar Patterns
- `little_loops/host_runner.py` `resolve_host()` (line 2535) is the existing
  single-chokepoint abstraction pattern for host CLI selection
  (`LL_HOST_CLI` / `orchestration.host_cli`) that this backend abstraction
  should mirror for `history.backend` selection.

### Tests
- New: `scripts/tests/test_session_store_backend.py` — adapter/config/error contracts
- Remote integration coverage for migration atomicity/concurrency, full migration
  chain, representative consumer reads/writes, read-only behavior, and failures;
  skip only for absent test configuration, not configured endpoint failures
- Extend transport, snapshot/export, doctor, and path-precedence coverage for the
  decisions and acceptance criteria below
- `scripts/tests/test_session_store_db.py`, `test_session_store_schema.py`,
  `test_session_store_lifecycle.py`, `test_session_store_queries.py`,
  `test_session_store_writers.py`
- `scripts/tests/test_history_reader_*.py` (11 files) — exercise reads
  through the new backend for at least the default `sqlite` path
- New: an integration test for the first remote backend that skips when
  that backend is unavailable (per Acceptance Criteria)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py:573-641` — per-key assertion suite enforcing `history`'s `additionalProperties: false`; needs a matching assertion block for `backend` following the pattern at lines 624-633 [Agent 2 finding]
- `scripts/tests/test_codequery_core.py` (`TestResolveProvider`, `TestProtocolConformance`) and `scripts/tests/test_host_runner.py:383,2366` (`TestResolveHost`, `TestResolveHostNamed`) — existing test-shape precedent for `resolve_backend()`: a parametrized "every registered kind resolves," an "unknown kind raises a typed error," and a protocol-conformance class applied to every registered instance [Agent 3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` (`TestPageStamps`, `TestBuildSnapshotDb`) and `scripts/tests/test_feat3323_sse_bridge.py` — break if `SCHEMA_VERSION`/`build_snapshot_db` change shape; cover the new `cli/artifact/dashboard.py` caller [Agent 3 finding]
- `scripts/tests/test_user_messages.py` — covers the new `user_messages.py` caller (`SessionHandle` import) [Agent 3 finding]
- `scripts/tests/test_codequery_codegraph.py`, `scripts/tests/test_queue_store.py`, `scripts/tests/test_cli_history.py`, `scripts/tests/test_ll_logs.py`, `scripts/tests/test_cli_doctor.py`, `scripts/tests/test_cli_doctor_full.py`, `scripts/tests/test_cli_doctor_install_checks.py`, `scripts/tests/test_cli_doctor_trim.py`, `scripts/tests/test_cli_ctx_stats.py`, `scripts/tests/test_issue_history_agent_quality.py`, `scripts/tests/test_feat3410_workspace_quality.py`, `scripts/tests/test_feat3418_workspace_quality.py`, `scripts/tests/test_evolution_triggers.py`, `scripts/tests/test_session_discovery.py` — existing coverage for the issue's already-known Files to Modify call sites; each becomes a break candidate if the backend wrapper's connect signature or return type diverges from raw `sqlite3.connect` [Agent 3 finding]
- No dedicated test file exists for `session_store/__init__.py`'s re-export surface itself — exercised only transitively through the tests above [Agent 3 finding]

_Second wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/{test_compaction,test_enh_2497_agent_type,test_enh_2505_subagent_runs,test_enh_2511_mcp_telemetry,test_enh_3166_qwen_normalizer,test_enh_3393_gemini_normalizer,test_enh_omp_normalizer,test_issue_collisions,test_issue_history_rework,test_ll_session,test_pytest_history_plugin,test_sweep_stale_refs,test_transport}.py` — genuinely session_store-coupled (call `ensure_db`/`connect` or a direct `sqlite3.connect(str(db))` bypassing the store's own `connect()`); `test_ll_session.py` is the heaviest, exercising `rebuild`/`compact`/`recompress`/`backfill` end-to-end [Agent 3 finding]
- New: dedicated test file for `little_loops/cli/compact_session.py`'s `main_compact_session()` — no existing test invokes the CLI wrapper; only the underlying `session_store.compact_session()` function is tested (`test_compaction.py`) [Agent 3 finding]
- `test_codequery_core.py::TestResolveProvider`/`TestProtocolConformance` and `test_host_runner.py::TestResolveHost`/`TestResolveHostNamed` remain the applicable test-shape precedent for `resolve_backend()`; `test_host_runner.py::test_does_not_mutate_os_environ` (`:2394`) is the stricter of the two and should be followed if `resolve_backend()` reads env vars [Agent 3 finding]
- New/extended (review pass 2026-09-23): per-machine watermark isolation (machine B's older un-ingested transcripts are still ingested after machine A advances its watermark); incremental materialization is additive (no `DELETE`) and idempotent on re-run; `session_start` under `libsql` spawns the worker against the remote target without `--rebuild`; `history.backend` set only in `.ll/ll.local.md` is honored; a malformed `ll.local.md` never raises on the hook path; the conftest session-wide `LL_HISTORY_DB` (`scripts/tests/conftest.py:974-981`) keeps the suite local — remote/config-resolution tests must `delenv("LL_HISTORY_DB")` explicitly
- `scripts/tests/test_feat3323_sse_bridge.py:1198-1201`, `test_hook_user_prompt_submit.py:143-146,302-305,604-607`, `test_ll_issues_research_triage.py:145-148`, `test_set_status_cli.py:1309-1312`, `test_hook_post_tool_use.py:190-193`, `test_feat3445_workspace_activity.py:92-98` — assert on `sqlite3.OperationalError`/`sqlite3.Error` specifically as the stand-in for "the history store failed," separate from the four catch sites already named in Program Design; each caller's best-effort/degradation contract needs re-verification against the new backend-neutral error taxonomy [Agent 2 finding]

### Documentation
- `docs/reference/` — new `history.backend` config keys and the env-var
  secret pattern (per Acceptance Criteria)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:608-662` (`### history`, `history.db_path` row at `:616`) — needs a new `history.backend` row/subsection documenting the config shape and secret env-var pattern [Agent 1 + Agent 2 finding]
- `docs/reference/API.md` — types session-store function signatures as `conn: sqlite3.Connection` throughout (e.g. `:9906`, `:10311`) and narrates FTS5/VACUUM behavior (`:4862-10331` range) — needs updating for a backend-neutral connection/cursor/row contracts [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-session search --fts` (`:4118`), `compact --and-prune` (`:4183`), `prune`/`recompress` (`:4087-4089`, `:4256-4258`), `ll-history-context` (`:4413`) FTS5 matching, `ll-queue list` (`:4342`) `sqlite3.OperationalError` — document unconditional SQLite behavior that needs a capability-gate caveat [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md:634` (VACUUM prose) and `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:251` (FTS5 caveat) [Agent 2 finding]
- `docs/ARCHITECTURE.md:89` (module-overview table: "Unified per-project SQLite + FTS5 history store"), `:636` (`SQLiteTransport` and migration prose (history uses `meta.schema_version`; correct any `PRAGMA user_version` claim)), `:832` (states `queue_store.py` "copies `session_store/schema.py`'s ... shape rather than sharing code, matching every other sqlite consumer in this codebase" — verify wording while retaining queue storage as local-only) [Agent 2 finding]
- `skills/compact-session/SKILL.md:15,68` and `skills/improve-claude-md/SKILL.md:206,209,293,308` — reference `session_store.compact_session`/`_summarize_block`/`resolve_history_db`/`record_retirement` in prose/example code [Agent 1 finding]

_Second wiring pass added by `/ll:wire-issue`:_
- `README.md:188`, `CONTRIBUTING.md:315` — describe `.ll/history.db` as a per-project SQLite file
- `docs/reference/HOST_COMPATIBILITY.md:93,543` — per-host compatibility table states `SQLiteTransport` writes to `.ll/history.db` "(same path)" for every host CLI
- `docs/reference/WORKTREES.md:19` — documents `LL_HISTORY_DB` being exported into descendant `os.environ` before worktree creation so worktrees share the main repo's local DB; doesn't describe remote-backend sharing, which wouldn't need this relay
- `docs/guides/MCP_SERVER_GUIDE.md:248,266,735` — `history_search` MCP tool documented in terms of local FTS5 over `.ll/history.db`, including a troubleshooting row keyed on the file being absent/empty
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:63,104,126,149,150,169,207,303,315,483,515,555` — hook-by-hook prose describing local `.ll/history.db` reads/writes
- `docs/kimi/hook-events.md:44,53` — kimi-specific mirror of the same PostToolUse description
- `hooks/adapters/codex/README.md:66` — troubleshooting tip querying `.ll/history.db` `hook_events` directly
- `docs/observability/des-audit.md:9`, `docs/observability/otel-mapping.md:6,61,110` — document event/usage tables in `history.db` as the local OTel/DES alternative
- `docs/guides/DECISIONS_LOG_GUIDE.md:445` — "Uses `.ll/history.db` when present for faster scanning"; user-facing doc for the `decisions.py:578` hardcoded-path gap above
- `docs/guides/LOOPS_REFERENCE.md:77,384,430`, `docs/reference/loops.md:217` — describe the `sft-corpus` loop's `enrich` step joining `history.db` session-quality metadata
- `scripts/little_loops/loops/README.md:159,198` — lists `.ll/history.db` as loop-interacted state; describes `fleet-loop-improve`'s `ll-logs fleet-review` usage
- `skills/configure/areas.md:1386-1509` (`## Area: history`) — the `/ll:configure` skill's `history.*` question/answer flow (`velocity_window`, `effort_fields`, `max_age_days`, `session_digest.*`, `evolution.*`, `go_no_go.*`, `capture_issue.*`); has no `backend` question today and is mirrored into `.qwen/skills/configure/areas.md`, `.kimi-code/skills/configure/areas.md`, `.gemini/skills/configure/areas.md` per the existing mirror-gate convention — all four need a matching update [Agent 2 finding]

### Configuration
- `history.backend.auth_token_env` — separate authentication-token reference; no committed token
- New: `.ll/learning-tests/libsql-remote.md` — required real remote driver/version
  evidence (`libsql.md` already exists as local-only evidence)
- New test env vars: `LL_TEST_LIBSQL_URL` + `LL_TEST_LIBSQL_AUTH_TOKEN` select the remote
  integration endpoint; absent → remote tests skip
- `.ll/ll-config.json` `history.backend` block; `LL_HISTORY_DB` /
  `history.db_path` remain the sqlite-only path override, unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `.ll/learning-tests/sqlite3.md` (proven, 15 assertions) is the existing Learning Test Registry precedent this issue's `learning_tests_required: [libsql]` frontmatter is modeled on; `little_loops/learning_tests/gate.py` enforces that frontmatter against a proven `libsql.md` entry as a gate-blocking prerequisite before implementation [Agent 2 finding]

_Second wiring pass added by `/ll:wire-issue`:_
- `little_loops/workspace.py::_config_manifest_path()` (~line 74) — reads `history.workspace_manifest_path`; its docstring explicitly contrasts its own `~`-expansion behavior against "`history.db_path`'s reader, which does not expand `~`" — an independent assumption about a sibling `history.*` key's resolver that needs re-verification if `history.db_path` resolution semantics shift [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- **Closer existing precedent than `resolve_host()`**: `resolve_provider()` (`codequery/core.py:103`) is a config-driven, pluggable-backend resolver — a `@runtime_checkable` Protocol + a lazy-import `name -> (module_path, class_name)` registry (`_PROVIDER_MAP`, `codequery/core.py:93-96`) + `"auto"` fallback that tries candidates in registry order. It explicitly documents mirroring `little_loops.adapters.core` (FEAT-2391, FEAT-2576). Unlike `resolve_host()`'s eagerly-imported class registry, `resolve_provider()`'s registry entries are resolved via `importlib.import_module` only on demand — the rationale given (`codequery/core.py:93-96`) is that concrete provider modules import back from `core.py`, so eager import would create a cycle. Whichever eager-vs-lazy shape is chosen for `session_store.backend`, the codebase currently holds both conventions, not one.
- **Config-schema shape for a discriminated backend selector**: a `"provider"`/`"kind"` string with a JSON Schema `"enum"` + `"default"` sits alongside a same-named nested settings object, even when only one provider currently exists (`sync.provider`, `config-schema.json:1390-1445`, `"enum": ["github"]` with a full nested `"github"` object) or several do (`code_query.provider`, `config-schema.json:1449-1484`, `"enum": ["auto", "codegraph", "fallback"]` with a nested `"codegraph"` settings object).
- **Existing degradation precedent is exception-based, not a `supports()` boolean check**: `Unsupported(CodeQueryError)` (`codequery/core.py:39-44`) is raised by a provider for a query kind outside its `capabilities()`; its docstring claims the resolver catches this to fall through to a fallback provider, but a repo-wide search found no `except Unsupported` anywhere outside `cli/code.py:146` — the only live catch site logs and exits (`return 2`), it does not fall through. `HostCapabilities` (`host_runner.py:294-318`) is the other existing capability-flag precedent: a frozen dataclass of plain booleans, with an unsupported capability silently dropped and a `CapabilityNotSupported(UserWarning)` emitted rather than raised.
- **`_apply_migrations` (`session_store/schema.py:1492-1567`) is single-dialect today**: it takes a live `sqlite3.Connection` directly (not a path or dialect token), `_MIGRATIONS` is an unconditional `list[str]` of raw SQL with no per-dialect branch, and locking is SQLite-specific (`BEGIN IMMEDIATE`, manual `isolation_level = None`, a custom `_split_sql_statements()` helper whose docstring explains it avoids `executescript()`'s implicit `COMMIT` that would release the write lock mid-migration). `_configure_connection()` (`schema.py:1443-1459`) applies WAL/`busy_timeout` pragmas wrapped in `try/except sqlite3.OperationalError` — today's one instance of graceful degradation in this file is per-pragma try/except, not a capability-flag check.
- _Superseded:_ `connect_readonly()` now exists (`session_store/backend.py`, ENH-3525). The duplicated read-only helpers `issue_history/evolution.py:30` and `codequery/codegraph.py:81` still exist; codegraph stays out of scope.
- **Optional-dependency extras** (`pyproject.toml:141-199`) follow `<name> = ["pkg<constraint>"]` under `[project.optional-dependencies]`, with an inline justification comment on any version bound — the `mcp` extra (`pyproject.toml:178-191`) is the fullest example, explaining both the exact pin and why it's an extra rather than a base dependency (16 mandatory transitive deps otherwise landing on every install). A repo-wide search found no existing reference to `postgres`, `libsql`, `psycopg`, or `sqlalchemy` anywhere in `scripts/pyproject.toml` or `scripts/little_loops/`.
- **No dialect abstraction exists anywhere in the codebase today**: a repo-wide search for `dialect` as a code identifier and for any `*Dialect` class found zero hits. `little_loops.session_store.backend` (the module this issue proposes) has no current counterpart in the tree.

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- A prior in-tree spike already implements this exact resolver shape: `scripts/tests/spike/session_store_backend_dialect/{backend.py,dialects.py}` defines a `Backend` Protocol (`kind`, `connect`, `connect_readonly`, `ensure_schema`, `supports`, `migrations`) and a `resolve_backend()`/`_BACKEND_MAP` registry structurally identical to `codequery.core`'s. Its plan (`.ll/spikes/spike-FEAT-3524.md`, "Promotion" section) describes folding it into `session_store/backend.py`/`schema.py` as a separate, manual step — it deliberately excludes `config-schema.json` changes and routing the production call sites.
- A third lazy-import registry precedent exists beyond `codequery.core.resolve_provider()` and `host_runner.resolve_host()`: `adapters.core.resolve_emitter()` (`adapters/core.py:47-81`) uses the identical `_EMITTER_MAP` `(module_path, class_name)` + `importlib.import_module` shape and typed-error message shape ("not registered... Available: {sorted(...)}"), with a documented cross-registry constraint — its docstring notes emitter keys must match their `host_runner` registry key where both exist, cross-checked by the `ll-verify-host-map` entry point.
- The lazy-vs-eager registry choice in this codebase tracks import-cycle risk, not a blanket rule: the spike's own docstring justifies choosing a lazy `importlib` registry because a `Backend` module and its dialect implementations would otherwise cycle "the same way `codequery` providers do" (concrete implementations importing shared types back from the core module); `host_runner.py` uses eager imports for its runner classes because no such cycle exists there. Which shape applies to `session_store.backend` depends on that module's own import graph, not a fixed convention.
- Registered-kind resolution is tested three distinct ways in this codebase: (1) parametrized "every registered name resolves + unknown name raises a typed error" (`test_codequery_core.py::TestResolveProvider`, `test_adapters.py::TestResolveEmitter`, `test_host_runner.py::TestResolveHostNamed::test_resolves_every_registered_host`); (2) a Protocol-conformance fixture class applied to one instance, with an explicit docstring invitation to extend it for a second implementation (`test_codequery_core.py::TestProtocolConformance`); (3) a distinct "every registry key has a row in every derived lookup table" set-equality gate (`test_host_conformance.py::test_stream_shape_covers_registry`) — relevant only if the backend's capability data grows beyond `supports()` into a separate derived table.
- The optional-driver-import convention in this codebase is a deferred `try: import X / except ImportError: raise RuntimeError("... pip install 'little-loops[extra]'") from exc` inside `__init__` (never at module scope, so importing the module itself never requires the optional package), paired with a `pyproject.toml` extras entry carrying an adjacent justification comment: `transport.py:1720-1730` (`OTelTransport`) and `:1884-1889` (`WebhookTransport`), extras declared at `pyproject.toml:192-199`.
- The read-only-open duplication this issue already names (3 sites: `workspace_quality.py`, `evolution.py`, `codegraph.py`) is an undercount: a repo-wide search finds 11 raw `sqlite3.connect(f"file:...?mode=ro"...)` call sites, including two in `cli/doctor.py` (`:485`, `:547`) and two in `session_store/sessions.py` (`:129`, `:695`) not previously listed. One of the 11, `session_store/queries.py`'s `_connect_readonly()` (`:191-200`), is already a named, documented wrapper whose docstring explains it deliberately bypasses the store's normal `connect()` because that path migrates-on-open (would mutate `history.db` as a side effect of generating an export artifact) and that `mode=ro` scopes read-only to the main database only (a writable scratch DB can still be `ATTACH`ed). This wrapper is local to `queries.py` and unused by the other 10 sites — it is the closest in-tree precedent for the proposed `connect_readonly()` chokepoint's contract, not merely another call site to migrate.

### Review corrections and additional findings — 2026-09-22

- SQL compatibility extends beyond opens: `session_store/writers.py` uses
  `INSERT OR IGNORE`, cursor insert IDs and affected-row counts;
  `session_store/lifecycle.py` uses `lastrowid`; `session_store/schema.py` uses
  SQLite DDL, explicit isolation control, and schema-inspection PRAGMAs. These
  representative dependencies justify a compatibility audit without treating
  unverified package-wide occurrence counts as scoped effort.
- `_apply_migrations` in `session_store/schema.py:1492` records versions in
  `meta.schema_version`, not `PRAGMA user_version`. Its lock/version/rollback
  sequence must be proven remotely; the existing spike only proves local mechanics.
- `SQLiteTransport` (`session_store/writers.py:2894`, constructed by
  `issue_manager.py:1742`) is already a listed consumer, but needs explicit work:
  it directly opens a connection with `check_same_thread=False`, serializes writes,
  catches `sqlite3.Error`, and disables/logs failed sinks. Driver error/thread
  semantics must preserve that best-effort contract.
- `session_store/queries.py:250` builds dashboard snapshots with `ATTACH DATABASE`
  to a local destination. `export_history` also checks `db_path.exists()`.
  Connection replacement alone cannot make those operations remote-aware.
- `session_store/schema.py:204` defines sessions with `session_id`, `jsonl_path`,
  `started_at`, and `project_path`; no machine provenance is present in its session
  migrations. Sharing must account for local paths and identity without assuming
  that adding a hostname alone solves collisions or source access.
- Official Python documentation distinguishes `libsql` direct remote mode from
  `turso_serverless` and shows separate `auth_token` configuration. Target one
  engine/driver explicitly; test capabilities rather than generalizing from the
  Turso name: https://github.com/tursodatabase/turso-docs/blob/main/sdk/python/quickstart.mdx

## Implementation Steps

0. Prerequisite: ENH-3525 merged (chokepoint, `HistoryError` taxonomy,
   `open_history()` / `open_history_readonly()`, path-bypass repairs).
1. Produce `.ll/learning-tests/libsql-remote.md` against a real remote endpoint
   with `proven_package`/`proven_version` recorded (Readiness Prerequisites lists
   the required and probe assertions, the endpoint plan, and the target deployment).
   Pin the tested driver/version as a justified extras entry. If any required
   assertion fails, stop here and re-scope (Proposed Design §2 contingency).
1a. SQLite-only target-type refactor (Proposed Design §1a), landable and testable
   before the adapter exists: introduce `HistoryTarget`, change `_resolve_once()` and
   the `Backend` protocol to take it, narrow the three entry points' return type to
   `HistoryConnection`. Full local suite passes with no behavior change.
2. Add `history.backend` config (`provider`, `url`/`url_env`, `auth_token_env`,
   `project_id`, `telemetry_timeout_ms`) to
   `config-schema.json` and the `/ll:configure` history area (+ mirrors). Encode the
   precedence rules from Proposed Design §1; reject unknown providers, two endpoint
   sources, or a missing token env with redacted diagnostics. The backend config
   reader merges `.ll/ll.local.md`, never raises on the hook path, and caches per
   process (§1 config reader).
3. Implement `LibsqlBackend`: connection/cursor/row adaptation (named-row access on
   top of the driver's plain tuples), narrow error wrapping around driver calls into
   the `HistoryError` taxonomy (default category `HistoryOperationError`), deferred
   `import libsql` inside `__init__` with the missing-extra `RuntimeError` message.
   `resolve_history_db()` / `ensure_db()` raise `HistoryBackendNotLocal` when the
   configured target is remote and no explicit local target was given.
4. Adapt connection setup and migrations using `meta.schema_version`. Verify the
   full migration chain, concurrent initialization, atomic rollback, schema-ahead
   behavior, and genuinely non-mutating reads against the remote driver. Do not
   promote the SQLite-backed spike as remote compatibility evidence. Under `libsql`,
   opens never migrate: add `ll-session` `migrate` and the schema-skew policy
   (Proposed Design §9), plus the project-identity stamp/check (§10).
4a. Worktree/env relay (Proposed Design §1b): `worktree_utils.py:336`,
   `hooks/session_start.py:146`, `pytest_history_plugin.py:45`.
5. Implement the shared-store operation matrix (Proposed Design §7): reject
   `rebuild` (including the worker's `--rebuild`), full `backfill`, `prune`,
   `compact --and-prune`, `recompress`, `VACUUM`, and `sweep_stale_refs` under
   `libsql` with `HistoryUnsupported` before any mutation, unless the specific
   operation's cross-machine safety is proven and tested in this issue. Implement the
   identity audit outcomes (machine ID, copied-session dedup, existence-checked
   foreign `jsonl_path`/`project_path`).
5a. Remote ingestion (Proposed Design §7a): per-machine `last_raw_event_ts` watermark,
   additive incremental materialization of `_REBUILD_TABLES` for newly ingested
   `raw_events`, and `hooks/session_start.py` + `cli/backfill_worker.py` routed to the
   remote target without `--rebuild` or migrate-on-open.
6. Implement capability gating for FTS5, WAL, VACUUM, `create_function` (Python UDFs —
   `history_reader/formatting.py` `ll_grep`'s `regexp_match`), and `ATTACH`. Snapshot
   export (`build_snapshot_db`) raises `HistoryUnsupported` under `libsql` before any
   `ATTACH`; local SQLite snapshot behavior is unchanged.
7. Failure policy: bounded network waits; event sinks (`SQLiteTransport`,
   `cli_event_context`) stay best-effort with rate-limited redacted warnings and
   catch `HistoryError` only; explicit reads/migrations/maintenance surface
   failures; never retry a write whose commit outcome is unknown. Implement the
   telemetry latency budget (Proposed Design §8): telemetry timeouts, per-process
   schema-ensured cache, the file-backed verification cache for hooks, and the
   unreachable-endpoint marker — both gitignored in `.gitignore` and
   `init/writers.py` `_GITIGNORE_ENTRIES`.
8. Add the explicit `ll-doctor` backend diagnostic (connectivity, auth, schema
   compatibility; timeout; no migrations/writes; redacted; flags `history.db_path`
   set alongside a remote provider).
9. Local regressions plus remote integration coverage (skip only on absent test
   configuration; a configured endpoint failure fails the test), then update
   configuration/API/CLI/guide docs and the `/ll:configure` mirrors.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `little_loops/cli/session.py` — make FTS5/VACUUM `help=` strings (`:117`, `:118`, `:269`, `:356`, `:368`) conditional or caveat them once these features are capability-gated
- _(`cli/doctor.py` `_schema_drift_data()`, `cli/history.py` `root` handler, and `issue_history/workspace_quality.py` `_open_member_readonly()` chokepoint routing: done by ENH-3525/ENH-3526.)_
- Add `scripts/tests/test_config_schema.py` assertion block for `history.backend` (pattern at `:624-633`)
- Update `docs/reference/CONFIGURATION.md:608-662`, `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/ARCHITECTURE.md:89,636,832`, `docs/guides/HISTORY_SESSION_GUIDE.md:634`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:251` — reflect the new backend, capability-gated FTS5/VACUUM caveats, and check the `queue_store.py`-mirrors-`session_store` description against the retained local-only queue scope in `docs/ARCHITECTURE.md:832`
- Audit and verify the ~20 downstream consumers of `session_store`'s public re-export surface listed under Dependent Files, to confirm they still work against the adapter contracts; change callers where path or connection assumptions require it

### Wiring Phase (added by second `/ll:wire-issue` pass)

_These additional touchpoints were identified by a second wiring pass and must be included in the implementation:_

- Update `little_loops/decisions.py::generate_from_completed()` (already routed through `resolve_history_db()` by ENH-3525/ENH-3526) to read the remote store under `provider: libsql` instead of falling back to filesystem scanning when `resolve_history_db()` raises `HistoryBackendNotLocal`
- _(`history_reader/_base.py` `_connect_readonly()` fold-in: done by ENH-3525/ENH-3526.)_
- Update `little_loops/cli/backfill_worker.py:52,70,78` — route the `REGISTERED_HOSTS`/`host_layout_for`/`backfill_incremental` lazy imports through the backend-aware path
- Audit the ~35 CLI modules that only import `DEFAULT_DB_PATH, cli_event_context` (Dependent Files) — confirm `cli_event_context`'s best-effort contract holds unchanged under the new backend; no code change expected unless `DEFAULT_DB_PATH`'s type itself changes
- Add: dedicated test coverage for `little_loops/cli/compact_session.py`'s CLI wrapper (currently untested at that layer)
- Update `skills/configure/areas.md` `## Area: history` (+ `.qwen/`, `.kimi-code/`, `.gemini/` mirrors) — add a `history.backend` configuration question

## Impact

- **Priority**: P3 — shared same-project history is useful; local history remains functional.
- **Effort**: Large after ENH-3525/ENH-3526 — the path-to-target refactor across the
  chokepoint's ~94 entry-point call sites (`open_history`/`open_history_readonly`/
  `connect_readonly`, counted 2026-09-23), per-machine ingestion and incremental
  derived-table materialization (§7a), cursor/row adaptation, migration
  compatibility and `ll-session` `migrate`, the telemetry latency budget, the operation
  matrix, the doctor check, and docs. The connection routing, error taxonomy, and path
  repairs already landed in ENH-3525/ENH-3526. Kept as one issue by decision
  (2026-09-22); Implementation Step 1a is the natural first commit. The 2026-09-23
  review added §7a (per-machine ingestion + incremental materialization), a
  self-contained workstream that is the natural candidate to split out if scope needs
  trimming.
  Postgres/MySQL dialect translation is separate work.
- **Risk**: Medium to high until real-driver proofs pass — partial migrations,
  ambiguous network write outcomes, and shared-store maintenance operations
  (`rebuild`/`backfill`/`prune`) can lose or misattribute other machines' history.
  The existing spike retires only local mechanics.
- **Breaking Change**: None for default SQLite users beyond the intentional
  changes already documented in ENH-3525. Remote support is opt-in; every rejected
  or unsupported remote operation is documented explicitly.

## Proposed Design

1. Configure one selected backend, for example:
   ```json
   {
     "history": {
       "backend": {
         "provider": "libsql",
         "url_env": "LL_HISTORY_URL",
         "auth_token_env": "LL_HISTORY_AUTH_TOKEN",
         "project_id": "acme-api"
       }
     }
   }
   ```
   `provider` is the selector (matching `sync.provider` and `code_query.provider`;
   `"enum": ["sqlite", "libsql"]`, default `"sqlite"`). Support a non-secret
   literal `url` or `url_env`, with exactly one endpoint source for libSQL. Never
   commit tokens; redact credentials from errors and diagnostics. Never silently
   fall back to a local history store after remote failure.

   **Path and precedence semantics (settled):**
   - Unset backend / `provider: sqlite`: unchanged. Resolution stays
     `explicit path > LL_HISTORY_DB > history.db_path > DEFAULT_DB_PATH`.
   - `provider: libsql`: default-shaped arguments (`DEFAULT_DB_PATH`, `None`) to
     `open_history()` / `open_history_readonly()` / `cli_event_context` select the
     configured remote store. A deliberate local target — an explicit non-default
     path argument, or `LL_HISTORY_DB` set — remains an explicit local SQLite
     target, exactly as the current code preserves deliberate overrides (BUG-3181,
     WORKTREES.md `LL_HISTORY_DB` relay). `history.db_path` is ignored under
     `libsql` and `ll-doctor` reports that both are set.
   - Legacy path-returning APIs (`resolve_history_db()`, `ensure_db()`) keep their
     SQLite behavior for explicit local targets and raise a typed
     `HistoryBackendNotLocal` when asked for the configured remote target. No
     fabricated filesystem path is ever returned for a remote store.
   - User docs recommend setting `history.backend` (especially a literal `url`) in
     `.ll/ll.local.md` rather than the committed `.ll/ll-config.json`, so a clone does
     not silently join a shared store.
   - **Config reader (settled, review 2026-09-23).** That recommendation only works if
     the backend reader applies the `ll.local.md` frontmatter deep-merge
     (`config/core.py` `parse_local_override_frontmatter` + `deep_merge`). The existing
     `_config_db_path()` (`db.py:35-69`) reads `ll-config.json` with raw `json.loads`
     and would silently ignore an `ll.local.md` endpoint — do not copy it. The reader
     must (a) merge local overrides, (b) never raise on the hook hot path (malformed
     config → treat as `provider: sqlite` plus a one-time warning, never a silent
     remote→local switch once a remote provider was readable), and (c) cache per
     process. `ll.local.md` is already in `worktree_copy_files`
     (`config/automation.py:102`), so worktrees inherit the endpoint.

   **1a. Target type (settled).** The shipped chokepoint is path-typed end to end:
   `Backend.connect(path: Path, *, check_same_thread)`, `connect_readonly(path)`,
   `ensure_schema(path)` (`session_store/backend.py:148-150`), `_resolve_once() -> Path`
   (`:233`), and `connect_readonly()`/`open_history()`/`open_history_readonly()` all
   return `sqlite3.Connection` (102 call sites). A remote store has no path, so:
   - `_resolve_once(target)` returns `HistoryTarget = LocalTarget(path: Path) |
     RemoteTarget(config: BackendConfig)` (frozen dataclasses). Default-shaped targets
     under `provider: libsql` yield `RemoteTarget`; explicit local targets and
     `LL_HISTORY_DB` yield `LocalTarget` (§1 precedence unchanged).
   - The `Backend` protocol methods take a `HistoryTarget`; `SqliteBackend` accepts only
     `LocalTarget`, `LibsqlBackend` only `RemoteTarget` (mismatch raises
     `HistoryUnsupported`). The backend is chosen from the target, not from a global
     default: `resolve_backend(provider: str = "sqlite")` keeps its signature and the
     entry points call it with the target's provider.
   - The three entry points' return annotation narrows to `HistoryConnection` (as the
     `Backend` docstring at `:135-141` already anticipates). Callers that genuinely
     need `sqlite3` specifics (`create_function`, `ATTACH`, `row_factory`) keep
     `sqlite3.Connection` and must gate on `supports()` before use.
   - This refactor is SQLite-only and lands first (Implementation Step 1a) with no
     behavior change.

   **1b. Env relay under `libsql` (settled).** `worktree_utils.py:336` exports
   `LL_HISTORY_DB=str(resolve_history_db())` into `os.environ` before worktree creation
   (WORKTREES.md) so descendants share the parent's local DB. Under `libsql`,
   `resolve_history_db()` raises `HistoryBackendNotLocal`, and an inherited
   `LL_HISTORY_DB` would make every ll-parallel/ll-sprint worker an explicit local
   target — silent split-brain. Rule: when the resolved target is `RemoteTarget`, the
   relay exports nothing (descendants resolve the same config and reach the same remote
   store); it neither raises nor exports a local path. If `LL_HISTORY_DB` is already
   set in the parent while `provider: libsql` is configured, the relay leaves it as-is
   (deliberate override) and `ll-doctor` reports the conflict. The same rule covers the
   direct `LL_HISTORY_DB` reader `pytest_history_plugin.py:45`.
   `hooks/session_start.py:145-200` is more than an env reader: it hardcodes
   `root / ".ll" / "history.db"` as the backfill worker's target and migrates on open to
   read `last_rebuild_version`. It is handled as an ingestion writer under §7a.
2. Select Python `libsql` direct remote connections, not embedded replicas or
   `turso_serverless`. Keep the driver behind a justified, version-bounded extras
   entry with a clear missing-extra error raised from `LibsqlBackend.__init__`
   (deferred import, per `transport.py` `OTelTransport`/`WebhookTransport`). Prove
   the selected version against the intended deployment before implementing
   production consumers. Official driver distinctions and token usage:
   https://github.com/tursodatabase/turso-docs/blob/main/sdk/python/quickstart.mdx

   **Step 1 failure contingency (settled, review 2026-09-23).** The design assumes the
   `libsql` Python package supports direct remote mode with settable connect/statement
   timeouts. If any *required* `libsql-remote` assertion fails — no direct remote mode
   (embedded-replica only), no bounded connect to an unreachable host, no usable
   transaction/isolation control, or unsafe cross-thread use with no per-thread
   alternative — implementation **stops** after Step 1: record the result, set this
   issue `blocked`, and re-scope (another driver, Hrana-over-HTTP client, or embedded
   replicas) in a follow-up decision. Do not switch drivers mid-implementation.
   **Triggered 2026-09-23** — bounded connect (F1/F2), statement timeout (F5), and
   post-connect isolation control (F3) failed; see
   [Step 1 Learning Test Result](#step-1-learning-test-result-2026-09-23).
3. Register `LibsqlBackend` in ENH-3525's lazy registry. Define connection, cursor,
   row, and transaction adaptation from consumer usage: the driver returns plain
   tuples with no row factory, so named-row access is adapted in the backend.
   Do not assume `sqlite3.Connection` inheritance or `sqlite3.Row` compatibility.
   Update annotations only for code that accepts multiple backends; retain SQLite
   types for truly local-only operations.

   **Error contract (settled):** the recorded learning test shows the driver
   raises plain `ValueError` for both bad SQL and UNIQUE violations, with no
   `libsql.Error` in the MRO. Classification by driver exception type is therefore
   impossible; backend-neutral errors remain the contract. `LibsqlBackend` wraps
   exceptions narrowly around each driver call (connect, execute, executemany,
   commit, rollback) and maps them to `HistoryOperationError` ("other database
   failure") unless a reliable classification is proven by the remote learning
   test — connect-time auth/unreachable failures are the only expected candidates
   for `HistoryUnavailable`. No message-pattern matching; no `except ValueError`
   around whole consumer operations; the driver exception is preserved as
   `__cause__`.
   The `libsql-remote` learning test (2026-09-23) confirms remote errors are also
   plain `ValueError`, with the Hrana/SQLite code present only in message text — no
   reliable type-based classification under the `libsql` driver.
4. History migration versioning uses `meta.schema_version`, not
   `PRAGMA user_version`. Reuse migration SQL where proven compatible; verify
   `BEGIN IMMEDIATE`/isolation control or an equivalent atomic locking sequence,
   rollback, version re-read under lock, full migrations, and schema-ahead checks.
   Read-only access and diagnostics must not create or migrate the remote store.
5. Determine capabilities from tested driver/deployment behavior. Gate WAL setup,
   FTS5, maintenance, and snapshot export as appropriate; a probe that shows FTS5
   or `ATTACH` is rejected remotely establishes an unsupported capability, it does
   not block basic remote support. Audit network round trips in migration/event
   paths rather than assuming local latency.
   **Python UDFs**: `_SQLITE_CAPABILITIES` already lists `"create_function"`
   (`backend.py`), and `history_reader/formatting.py:55` (`ll_grep`) registers a
   Python `regexp_match` via `conn.create_function` and calls it inside SQL. A remote
   server cannot execute a client-side Python function, so `LibsqlBackend` reports
   `supports("create_function") is False` and `ll_grep` under `libsql` fetches
   candidate rows with a plain SQL predicate (e.g. `LIKE`/`instr` prefilter, bounded)
   and applies the regex in Python. Capability names are a closed set defined once in
   `backend.py` (currently `attach`, `vacuum`, `create_function`; this issue adds
   `fts5` and `wal`), not free strings.
6. Preserve failure policy per operation: event telemetry is best-effort with
   bounded waits and rate-limited warnings; explicit reads/migrations/maintenance
   report failures. Define reconnect and ambiguous-commit handling. Doctor checks
   are explicitly invoked, bounded, non-mutating, and redact secrets.
7. **Shared-store mutation safety (hard gate).** Every maintenance operation is
   classified before it can run under `libsql`, and a rejected operation fails
   with `HistoryUnsupported` before any mutation:

   | Operation | Why it is unsafe on a shared store | First remote release |
   |---|---|---|
   | `rebuild()` (`lifecycle.py:955`) | `DELETE FROM <table>` on derived tables, then replays `raw_events` from the database — global deletion with no concurrency or completeness guarantee against other machines' concurrent writes | rejected (incl. the backfill worker's `--rebuild`) |
   | full `backfill` (`ll-session backfill`) | upserts sessions, issues, and loop state from this machine's local sources; can overwrite or interleave with other machines' rows | rejected |
   | `backfill_incremental` / `backfill_raw_events` (SessionStart worker) | `INSERT OR IGNORE` into `raw_events` — additive; unsafe only because of the single global `last_raw_event_ts` watermark | **supported** with a per-machine watermark and incremental materialization (§7a) |
   | `prune()` (`lifecycle.py:1283`) | deletes `raw_events` globally; gates on `db_path.stat().st_size`, which has no remote meaning | rejected |
   | `ll-session compact` / `compact --and-prune` / `recompress` | rewrites `raw_events` rows other machines may be reading or writing | rejected |
   | `VACUUM` / `sweep_stale_refs` | file-level or existence-based on a local path | rejected |
   | reads, event writes, `search` (if FTS5 proven), `ll-history`, `ll-logs`, digests, context-compaction (`little_loops.compaction`) reads/writes | additive or read-only | supported |
   | snapshot export | `ATTACH` to a local destination | probe; supported via bounded row transfer or explicitly unsupported |

   "Compaction" names two different things: context compaction
   (`little_loops.compaction`, additive — supported) and the `ll-session compact`
   raw-event rewrite (destructive — rejected). Docs, errors, and tests use the full
   names.

   An operation moves from "rejected" to "supported" or "provenance-scoped" only
   when this issue (or a follow-up) proves and tests its cross-machine safety.

   **Retention limitation (documented, not solved here).** With `prune`, `compact`, and
   `recompress` all rejected, a remote store has no retention path in the first release
   and grows without bound; hosted libSQL plans have storage quotas. User docs state
   this and how to check size; `ll-doctor`'s backend check reports row counts for the
   largest tables. A provenance-scoped prune is follow-up work and, like local prune,
   must stay manual-only — never triggered automatically.

   **Identity audit (settled, review 2026-09-23):** `sessions.session_id` is the host
   session UUID primary key, which avoids session-row collisions, but that alone does
   not establish event deduplication (`idx_issue_events_dedup`,
   `idx_corrections_dedup` are content keys, not machine keys), safe handling of a
   session JSONL copied between machines, or how readers treat a foreign
   `jsonl_path`/`project_path`. Decisions:
   - **Machine ID**: a stable random ID generated once and stored in a gitignored
     machine-local file (e.g. `~/.ll/machine-id`, not under the project so clones and
     worktrees on one machine share it). Used for the per-machine watermark (§7a) and
     nothing else in this release.
   - **Copied session JSONL**: `raw_events` dedups on `(source_path, line_no)`; a copy
     at a different path would double-ingest. Test it; if it double-ingests, add a
     content-stable dedup key (`session_id`, `line_no`) for remote ingestion rather than
     relying on the path.
   - **Foreign paths**: any reader that opens `jsonl_path`/`source_path` from the store
     checks existence first and treats a missing file as "recorded on another machine"
     (skip / label), never as an error or as local data.
   - **Provenance column**: not added unless the copied-session or dedup tests above
     prove it necessary. Machine-filtered analytics are not required.

7a. **Remote ingestion (settled, review 2026-09-23).** Session/transcript data — the
   Motivation's core value — enters the store only via the SessionStart backfill worker
   (`lifecycle.py` `backfill_incremental` → `backfill_raw_events`), and the derived `_REBUILD_TABLES`
   are materialized only by `rebuild()`. Rejecting both would leave a remote store
   with hook/CLI event rows and no session/usage data. Under `libsql`:
   - **Per-machine watermark**: `backfill_raw_events()` reads and writes
     `meta.last_raw_event_ts:<machine_id>` instead of the global key. With a global
     key, machine A advancing to T makes machine B skip its older, not-yet-ingested
     transcripts (`since_ts` filter) — silent data loss. SQLite keeps the global key
     unchanged.
   - **Incremental materialization**: after ingest, derive `_REBUILD_TABLES` rows for
     only the newly inserted `raw_events` rows (by rowid or `session_id`), additive and
     idempotent (`INSERT OR IGNORE`/upsert on existing keys; no `DELETE`). First verify
     which derived tables live hooks already write directly (`writers.py`,
     `hooks/post_tool_use.py` for `tool_events`, `fsm/continuity.py` for `sessions`) so
     materialization does not double-write them. Any derived table without a natural
     dedup key needs one (migration) before it is materialized remotely.
   - **SessionStart**: `hooks/session_start.py` resolves a `HistoryTarget`, passes the
     remote target to `cli/backfill_worker.py`, never appends `--rebuild`, and never
     opens with migrate-on-open. `backfill_worker` refuses `--rebuild` under `libsql`.
   - **Schema bumps** that would locally trigger a rebuild instead require an explicit,
     documented follow-up (out of scope here); until then `ll-session` `migrate` reports
     that derived tables for pre-bump rows are not re-materialized.
8. **Telemetry latency budget (settled).** Under `libsql`, every tool call's hooks
   (`hooks/hooks.json` gives most hooks `"timeout": 5`) and every `ll-*` CLI
   (`cli_event_context` wraps ~35 `main()`s) would pay a TLS connect, and
   `SqliteBackend.connect()`'s shape (ensure first, then open — two connections per
   call) plus the version read add more round trips. A slow or down endpoint must not
   make each invocation pay the full wait. Therefore:
   - Telemetry/best-effort paths (hooks, `cli_event_context`, `SQLiteTransport`) use a
     connect + statement timeout well under the hook timeout (default 1.5 s total per
     write, configurable as `history.backend.telemetry_timeout_ms`); explicit
     reads/maintenance use a longer bound (default 10 s).
   - `LibsqlBackend` caches "schema verified at version N" per process so a process
     pays the version check once, and never opens a second connection just to ensure.
   - **Hooks are one process per event**, so the per-process cache gives them nothing.
     Add a file-backed verification cache (review 2026-09-23): "endpoint hash H verified
     at schema version N, `project_id` P" with a short TTL (default 300 s), next to the
     unreachable marker. Telemetry writes within the TTL skip the version/`project_id`
     round trips; a write that fails with a schema/constraint error invalidates the
     cache. Explicit reads, migrations, and `ll-doctor` ignore it and always verify.
   - **Gitignore**: the unreachable marker and the verification cache must be ignored
     in this repo's `.gitignore` *and* in consuming projects via
     `init/writers.py` `_GITIGNORE_ENTRIES` — `.ll/` is tracked with per-file ignores.
     Either add explicit entries or name both files to match an existing ignored glob
     (e.g. `.ll/*.lock`).
   - **Success-path budget**: the `libsql-remote` learning test records cold-connect
     and warm-statement latency; implementation adds an AC bounding a hook-path
     telemetry write on a *healthy* endpoint (cache warm) well under the hook timeout,
     not only the unreachable case.
   - On a connect failure/timeout in a telemetry path, write a short-TTL (default 60 s)
     unreachable marker under `.ll/` (gitignored, keyed by endpoint hash, never the
     token); subsequent telemetry writes within the TTL skip immediately with no
     network attempt and no repeated warning. Explicit reads and `ll-doctor` ignore
     the marker and always try.
   - Dropped telemetry is not buffered or replayed in this release (documented).
9. **Mixed-version fleet / migration policy (settled).** Machines sharing one store
   can run different little-loops versions. Under migrate-on-open, the first upgraded
   machine migrates the shared store and older machines land in `_apply_migrations`'
   schema-ahead branch (`schema.py`, BUG-3255). Under `libsql`:
   - Opens never migrate. Schema changes happen only via an explicit command
     (`ll-session` `migrate`, added here; valid for both providers, no-op when current),
     which reports the before/after version.
   - Store behind client (`recorded < len(_MIGRATIONS)`): writes and `ensure=True`
     reads raise `HistoryUnsupported` naming `ll-session` `migrate`; telemetry paths
     degrade (warn once, skip). Strict reads proceed.
   - Store ahead of client (`recorded > len(_MIGRATIONS)`): reads proceed; writes are
     refused with an "upgrade little-loops" message; the BUG-3255 stamp self-heal
     (clamping the recorded version down) never runs against a remote store.
   - `ll-doctor` reports recorded vs installed version.
10. **Project identity guard (settled).** Multi-project sharing is out of scope, so
    it is prevented, not merely unsupported: `ll-session` `migrate` on an empty remote
    store stamps `meta.project_id` from `history.backend.project_id` (required when
    `provider: libsql`; config validation rejects its absence). Every remote open
    compares the two once per process (piggybacking on the §9 schema check) and raises
    `HistoryUnsupported` on mismatch; `ll-doctor` reports a mismatch.
11. Out of scope: Postgres/MySQL or a general SQL dialect layer; other Turso
   engines/drivers; embedded replicas/offline synchronization; migrating
   `queue.db` or codegraph databases; workspace-manifest aggregation over remote
   backends (`history.workspace_manifest_path` stays local-only); unrelated-project
   multitenancy and machine-filtered analytics; a remote retention/prune path;
   buffering or replaying dropped telemetry; **seeding a remote store from an existing
   local `history.db`** (a new remote store starts empty apart from what each
   machine's SessionStart ingestion backfills from its own transcripts — user docs
   state this explicitly); **snapshot export under `libsql`** (explicitly unsupported
   in the first release, see Readiness Prerequisites); re-materializing derived tables
   after a schema bump on a remote store.

## Program Design

### Types

- `BackendProvider: Literal["sqlite", "libsql"]`
- `BackendConfig: dataclass` (`provider: BackendProvider`, `url: str | None`,
  `url_env: str | None`, `auth_token_env: str | None`, `project_id: str | None`,
  `telemetry_timeout_ms: int`)
- `LocalTarget: frozen dataclass` (`path: Path`), `RemoteTarget: frozen dataclass`
  (`config: BackendConfig`), `HistoryTarget = LocalTarget | RemoteTarget` (§1a)
- Capability names: a closed `Literal`/frozenset in `backend.py` (`attach`, `vacuum`,
  `create_function`, `fts5`, `wal`)
- From ENH-3525: `Backend` protocol, `SqliteBackend`, `HistoryConnection`,
  `HistoryCursor`, `HistoryRow` protocols, and the `HistoryError` taxonomy
  (`HistoryUnavailable`, `HistoryIntegrityError`, `HistoryUnsupported`,
  `HistoryOperationError`). This issue adds `LibsqlBackend` and
  `HistoryBackendNotLocal(HistoryError)`.
- Required connection/cursor/row members, inventoried from consumers: `execute`,
  `executemany`, commit/rollback/close, `in_transaction`, cursor fetching and
  iteration, `description`, `lastrowid`, `rowcount`, and indexed/named row access.
  The libsql adapter supplies named access over the driver's plain tuples. A
  five-method connection protocol is insufficient.
- Adapter error wrapping is narrow (per driver call) and defaults to
  `HistoryOperationError`; only proven classifications map elsewhere. Causes are
  preserved; credentials are never included in messages.

### Signatures

- `resolve_backend(provider: str = "sqlite") -> Backend` — ENH-3525's lazy registry (signature as shipped, `backend.py:217`); this issue adds the `"libsql"` entry. Entry points call it with the resolved target's provider.
- `_resolve_once(target: Path | str | None) -> HistoryTarget` — was `-> Path`; BUG-3181 absolute-path-verbatim rule preserved (absolute path → `LocalTarget`)
- `LibsqlBackend.__init__(self)` — deferred `import libsql`; raises `RuntimeError("... pip install 'little-loops[libsql]'")` when absent. Configuration arrives on the `RemoteTarget`, keeping `resolve_backend()`'s zero-arg construction.
- `Backend.connect(self, target: HistoryTarget, *, check_same_thread: bool = True) -> HistoryConnection`
- `Backend.connect_readonly(self, target: HistoryTarget) -> HistoryConnection`
- `Backend.ensure_schema(self, target: HistoryTarget) -> None` — under `libsql` this only verifies (version + `project_id`), never migrates (§9)
- `Backend.supports(self, capability: str) -> bool`
- `open_history(target: Path | str | None = None, *, check_same_thread: bool = True) -> HistoryConnection` — default-shaped target selects the configured backend; explicit local target opens SQLite
- `connect_readonly(target=None) -> HistoryConnection`, `open_history_readonly(target=None, *, ensure=False) -> HistoryConnection` — same target rule
- `resolve_history_db(...) -> Path` / `ensure_db(...) -> Path` — unchanged for explicit local targets; raise `HistoryBackendNotLocal` when the configured target is remote
- `migrate_history(target: Path | str | None = None) -> tuple[int, int]` — backs `ll-session` `migrate`; returns (before, after) version; the only path that migrates a remote store and stamps `meta.project_id`

### Call Path

Project configuration + explicit-target policy -> `resolve_backend` ->
`LibsqlBackend` -> `open_history()` / `open_history_readonly()` -> history
consumer. Under `sqlite`, write initialization invokes `ensure_schema` and the
existing migration sequence; under `libsql`, `ensure_schema` only verifies and
`migrate_history()` (`ll-session` `migrate`) is the sole migration path. Read-only/doctor
paths never migrate. Maintenance
commands consult the operation matrix (`supports()`) before touching the store.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- No backend-neutral error-category wrapper exists to model the "unavailable/auth, integrity, unsupported-operation, other" categories on: `session_store/schema.py`, `queries.py`, `lifecycle.py`, `writers.py` all catch and branch on raw `sqlite3.OperationalError`/`sqlite3.IntegrityError` directly at each call site (e.g. `schema.py:1458`, `:1485`; `queries.py:56`, `:212`, `:379`; `lifecycle.py:1447`), with no wrapped-exception hierarchy anywhere in the codebase. This taxonomy is new design, not a shared abstraction to reuse.
- No existing convention masks a specific env-var-sourced credential value in error messages or diagnostic output. `pii.py`'s `redact_pii`/`CREDENTIAL_RULES` scans free-text corpora for embedded secrets (email/token/key regex patterns) for SFT training-data export (`cli/logs.py::_redact_input_context` is its only other caller) — it is not wired into any error-message or `ll-doctor`-style diagnostic path today. `host_runner.py`'s `CREDENTIAL_SCOPES` controls which env vars a child process inherits rather than masking a value for display — a different concern (access control, not display redaction). `auth_token_env` redaction in error/diagnostic output has no in-tree pattern to extend.
- The closest structural analog for the `ll-doctor` backend diagnostic is `doctor.py`'s existing `_history_db_data()`/`@register_check _history_db_check()` pair (`doctor.py:444-513`): a pure `_xxx_data()` function that never raises and never creates the resource it probes (explicitly checks `Path.exists()` before calling `connect()`/`ensure_db()`, since both create-on-demand), returning a dict adapted by a thin `@register_check`-decorated function into `CheckResult(status: Literal["full","partial","unsupported"], note, severity: Literal["error","informational"])`. No existing doctor check in this codebase probes a network resource — every one of the currently registered checks operates on local filesystem/SQLite state, so there is no in-tree precedent for the connectivity/timeout half of the new check beyond this local-probe shape.
- Selector naming (resolved 2026-09-22): the codebase's two existing discriminated-backend-selector precedents both name the key `provider` (`sync.provider`, `code_query.provider`; `config-schema.json:1390`, `:1449`) and no schema block uses `kind`. This issue uses `provider` / `BackendProvider` throughout (examples, types, schema, configure flow, mirrors); the spike's `kind` attribute is renamed on promotion.

## Use Case

**Who**: A little-loops maintainer running work across several machines and
a self-hosted CI runner (including the Thinky runner).

**Context**: Each machine currently writes its own local `.ll/history.db`,
so `ll-history` / `ll-logs` analytics, session digests, and compaction
context are fragmented per machine with no way to sync without shipping
`.db` files around.

**Goal**: Point machines running the same logical project at one shared remote
libSQL database through `history.backend` via `.ll/ll-config.json`, so all machines write to
and read from the same store.

**Outcome**: `ll-history` and `ll-logs` see session/usage data from every
machine, session digests and compaction context stay consistent regardless
of which machine ran a session, and database consumers can read the same store. Existing dashboard artifact
export remains subject to the explicit snapshot capability decision below; local
JSONL paths are not assumed accessible from other machines.

## Readiness Prerequisites

Settled: libSQL first (Postgres/MySQL excluded); extras-entry policy; explicit
doctor diagnostic; `provider` selector name; path/precedence semantics (Proposed
Design §1); target type (§1a); env relay (§1b); error contract (§3); UDF gating (§5);
shared-store operation matrix and retention limitation for the first release (§7);
identity audit (§7); remote ingestion (§7a); telemetry latency budget and hook
verification cache (§8); mixed-version migration policy (§9); project identity
guard (§10); config reader merging `ll.local.md` (§1); Step 1 failure contingency
(§2); snapshot export unsupported under `libsql`; ENH-3525 as the SQLite-only
prerequisite. No design decisions remain open; only driver proof (Step 1) gates
implementation.

**Learning-test endpoint plan.** The `libsql-remote` learning test is produced as
Implementation Step 1 of this issue (not split out). Run it against **both**:
- a local `turso dev` / `sqld` server — the real Hrana-over-HTTP remote protocol with
  no cloud account; this is also the endpoint the remote integration tests use via
  `LL_TEST_LIBSQL_URL`/`LL_TEST_LIBSQL_AUTH_TOKEN`, following the testing policy of
  skipping when the tool/config is absent;
- the named target deployment, **Turso Cloud**, because hosted capability surface
  (ATTACH, FTS5, extensions, `VACUUM`) may differ from a local `sqld`. Record probe
  results per endpoint; where they differ, the Turso Cloud result governs
  `LibsqlBackend.supports()`.

**Learning-test gate (enforceable).** `.ll/learning-tests/libsql.md` is
local-driver evidence only: all seven assertions use a bare path or `:memory:`,
none exercise remote mode, no `proven_package`/`proven_version` is recorded, and
the driver is not installed in the test interpreter. It stays as local evidence.
Remote compatibility is a separate registry target, `libsql-remote`, added to
`learning_tests_required` in this issue's frontmatter so
`little_loops.learning_tests.gate` blocks implementation until
`.ll/learning-tests/libsql-remote.md` exists with `status: proven`, a real
`url`/`auth_token_env` endpoint, and `proven_package`/`proven_version` set. The
assertion "raises `libsql.Error`" has `result: fail`; it is accepted as a known
driver divergence (plain `ValueError`) and is the basis for the error contract in
Proposed Design §3 — do not re-run it expecting a pass.

`libsql-remote.md` **required** assertions (a `fail` blocks the adapter):
- connect with `url` + auth token succeeds; wrong token and unreachable host fail
  with recorded exception type and bounded time
- `BEGIN IMMEDIATE` / manual `isolation_level` / `in_transaction` behave as the
  migration sequence needs; rollback after a mid-migration failure leaves
  `meta.schema_version` unchanged
- full `_MIGRATIONS` chain applies from empty; repeat initialization is a no-op;
  two concurrent initializers serialize
- `PRAGMA table_info` and `meta.schema_version` reads work (schema-ahead check)
- `INSERT OR IGNORE`, `executemany`, `lastrowid`, `rowcount`, `description`
- one connection used from a second thread under a lock (the `SQLiteTransport`
  serialized cross-thread pattern), or a per-thread connection if the driver
  forbids sharing — record which
- a write whose commit outcome is interrupted is detectable (ambiguous-commit rule)
- connect and statement timeouts are settable, and a connect to an unreachable host
  returns within the configured bound (the §8 telemetry budget depends on it); record
  cold-connect and warm-statement latency to both endpoints

**Probe** assertions (a `fail` records an unsupported capability, does not block):
- FTS5 virtual table creation and `MATCH`
- `PRAGMA journal_mode = WAL`, `PRAGMA query_only = ON`, `busy_timeout`
- `ATTACH DATABASE` to a local file
- `VACUUM`
- `conn.create_function` (Python UDF) — expected unsupported remotely; confirms §5

Previously open decisions, settled in the 2026-09-23 review:
- Identity audit outcomes: machine ID for the per-machine watermark, copied-session
  dedup test, existence-checked foreign paths, provenance column only if tests
  require it (Proposed Design §7).
- Snapshot export: **explicitly unsupported under `libsql` in this first cut** —
  `build_snapshot_db` raises `HistoryUnsupported` with a clear message before any
  `ATTACH`; bounded row transfer is follow-up work. Do not imply remote `ATTACH`
  creates a local file.
- Remote ingestion: `backfill_incremental` supported with a per-machine watermark and
  additive incremental materialization; `rebuild`/full `backfill` rejected (§7a).
- Config reader merges `.ll/ll.local.md` (§1); hooks use a file-backed verification
  cache (§8); Step 1 failure stops and re-scopes (§2).

## Acceptance Criteria

- [ ] ENH-3525 is `done`; `.ll/learning-tests/libsql-remote.md` is `status: proven`
  with every required assertion passing, probe results recorded, and
  `proven_package`/`proven_version` set; the `libsql` extra pins that version. No
  Postgres/MySQL support or `psycopg` dependency is included.
- [ ] Config supports `history.backend.provider: sqlite|libsql` (schema enum,
  `/ll:configure` history area and its three mirrors), `url`/`url_env`,
  `auth_token_env`, `project_id`, and `telemetry_timeout_ms`. Unknown provider, two
  endpoint sources, missing token env, missing `project_id` under `libsql`, missing
  extra, and auth errors produce redacted diagnostics. Default SQLite path/env
  precedence tests remain unchanged. `history.backend` set only in
  `.ll/ll.local.md` is honored; a malformed config never raises on the hook path.
- [ ] Target-type refactor (§1a) lands with the full local suite green and no SQLite
  behavior change: `_resolve_once()` returns `HistoryTarget`, the `Backend` protocol
  takes it, the three entry points return `HistoryConnection`, and the BUG-3181
  absolute-path-verbatim tests still pass. A `SqliteBackend`/`RemoteTarget` or
  `LibsqlBackend`/`LocalTarget` mismatch raises `HistoryUnsupported`.
- [ ] Env relay (§1b): under `libsql`, worktree setup neither raises nor exports
  `LL_HISTORY_DB`, and a worktree child writes to the remote store (test); a
  pre-set `LL_HISTORY_DB` is preserved and reported by `ll-doctor`.
- [ ] Under `provider: libsql`, default-shaped targets select the remote store;
  an explicit path argument or `LL_HISTORY_DB` still opens that local SQLite file;
  `resolve_history_db()`/`ensure_db()` raise `HistoryBackendNotLocal` for the
  remote target and never return a fabricated path. Each rule has a test. Remote
  failures never silently switch history to a local database.
- [ ] `LibsqlBackend` wraps only driver calls, defaults to `HistoryOperationError`,
  preserves `__cause__`, and maps to another category only where the remote
  learning test proved the classification. Tests assert no `except ValueError`
  or driver-type catch exists around consumer operations.
- [ ] Connection/cursor/row and transaction contracts are exercised for both
  adapters, including named/indexed rows, fetching, insert IDs, affected-row counts,
  and error mapping used by consumers.
- [ ] Real remote tests cover the full migration chain using `meta.schema_version`,
  repeat initialization, concurrent initialization, rollback after failure, and
  schema compatibility. Read-only access does not create or migrate the store.
- [ ] Mixed-version policy (§9): under `libsql` no open migrates; `ll-session` `migrate`
  is the only migration path and reports before/after versions; a store behind the
  client refuses writes naming `ll-session` `migrate` (telemetry degrades); a store
  ahead of the client allows reads, refuses writes, and never has its stamp clamped
  down. Each branch has a test.
- [ ] Project identity (§10): `ll-session` `migrate` stamps `meta.project_id`; an open
  with a different `project_id` raises `HistoryUnsupported` before any read or write;
  `ll-doctor` reports the mismatch.
- [ ] **Remote ingestion (§7a)**: under `libsql` the SessionStart worker ingests into
  the remote store (never a local file, never with `--rebuild`, never migrating on
  open); the watermark is per machine, and a test proves machine B's older
  un-ingested transcripts are still ingested after machine A advances its watermark;
  incremental materialization populates the derived tables for new `raw_events`
  without any `DELETE`, is idempotent on re-run, and does not double-write rows live
  hooks already wrote. SQLite keeps the global watermark and existing rebuild
  behavior unchanged.
- [ ] **Shared-store mutation safety**: the operation matrix in Proposed Design §7
  is implemented; `rebuild`, full `backfill`, `prune`, `compact --and-prune`,
  `recompress`, `VACUUM`, and `sweep_stale_refs` are rejected with
  `HistoryUnsupported` before any mutation under `libsql`, each with a test that
  proves no row was deleted or written; any operation promoted to supported or
  provenance-scoped has a cross-machine safety test.
- [ ] Identity audit is implemented: a stable machine ID is generated once and kept
  machine-local; same-project sessions/events from two machines remain correctly
  attributed and deduplicated; a copied session JSONL does not double-ingest;
  readers existence-check `jsonl_path`/`source_path` so foreign-machine paths do not
  masquerade as local readable sources; any provenance the tests require is added.
- [ ] `ll-history`, `ll-logs`, session digests, and compaction reads/writes work
  against the remote store. `SQLiteTransport` lifecycle and serialized cross-thread
  writes work through the adapter, catch `HistoryError` only, and remain
  best-effort under remote failure. `ll-history summary` exits 0 on a degraded
  remote store; `ll-logs fleet-review` keeps its final-line-is-a-path contract.
- [ ] Network operations have bounded waits. Event-sink failures warn without
  aborting the observed operation; explicit reads/migrations/maintenance report
  failure. Tests cover failure policy, redaction, and the ambiguous-write no-retry
  rule.
- [ ] Telemetry latency budget (§8): with an unreachable endpoint, a hook-path event
  write returns within `telemetry_timeout_ms` (well under the 5 s hook timeout);
  after the first failure, subsequent telemetry writes within the marker TTL make no
  network attempt and emit no repeated warning; the marker never contains the token;
  explicit reads and `ll-doctor` ignore it. A process verifies schema/`project_id` at
  most once, and hook processes within the verification-cache TTL skip the check
  entirely (a schema/constraint failure invalidates the cache). On a healthy endpoint
  with a warm cache, a hook-path telemetry write stays within a bound derived from
  the learning test's recorded latency. The marker and verification cache are
  ignored by this repo's `.gitignore` and by the `ll-init` gitignore entries. Tests
  cover each.
- [ ] `ll_grep` (`history_reader/formatting.py`) works under `libsql` without
  `create_function` (Python-side regex over a bounded SQL prefilter), and every other
  `create_function` caller is gated on `supports("create_function")`.
- [ ] Unsupported search/maintenance/export capabilities produce clear messages.
  Snapshot export under `libsql` raises `HistoryUnsupported` before any `ATTACH`
  (tested); local snapshot export is unchanged.
- [ ] An explicit `ll-doctor` check diagnoses connectivity/authentication/schema
  compatibility with a timeout, no migrations/writes, and redacted output, and
  reports when `history.db_path` and a remote provider are both set.
- [ ] Remote integration tests skip only when test configuration is absent;
  failures with a configured endpoint fail the tests. Local regressions pass.
- [ ] User docs cover backend selection (recommending `.ll/ll.local.md` for the
  endpoint), extras installation, secrets, precedence, same-project sharing and
  `project_id`, `ll-session` `migrate` and the upgrade order across machines, the
  rejected-operation list (distinguishing context compaction from `ll-session
  compact`), the no-retention limitation, dropped-telemetry behavior, failure
  behavior, diagnostics, and capability limitations. They also state that a new
  remote store starts empty — existing local `history.db` contents are not seeded —
  and that snapshot export is unavailable under `libsql`.

## Spike Results

_Added by `/ll:spike` on 2026-09-22_

**Locally proven mechanics (not remote compatibility)**

| Risk (from standalone analysis of Proposed Solution) | Proven by | Result |
|----------------------------------|-----------|--------|
| (a) Zero precedent: dialect abstraction driving `_apply_migrations`'s `BEGIN IMMEDIATE`/manual-isolation/split-statement locking sequence with per-dialect DDL | `TestDialectMigration::test_sqlite_backend_migrates_with_existing_locking_sequence`, `test_stub_remote_backend_uses_dialect_specific_ddl`, `test_rerunning_ensure_schema_is_idempotent` | ✓ pass |
| (a) Concurrent migration race under a dialect-parameterized chokepoint | `TestConcurrentMigration::test_concurrent_migration_race_still_serializes` | ✓ pass |
| (b) No existing test exercises capability-gated degradation for SQLite-only features | `TestCapabilityGate::test_capability_check_gates_unsupported_feature`, `test_capability_check_passes_for_supported_feature` | ✓ pass |
| isolation guard | `TestSpikeIsolation::test_spike_does_not_import_production_session_store` | ✓ pass |

**Spike location**: `scripts/tests/spike/session_store_backend_dialect/`
**Verification**: 7 tests pass across 2 commands (spike AC suite + `test_session_store_schema.py` regression, 193 tests, both untouched).
**Original spike exclusions**: real remote connectivity and backend selection were not tested. The review now selects libSQL; actual driver/deployment compatibility remains gated by `learning_tests_required`. Both spike implementations use SQLite, so passing DDL/locking tests do not establish remote behavior.
**Promotion**: reuse only the mechanics validated by real-driver learning tests; do not promote a general dialect layer for this narrowed scope. New: `scripts/little_loops/session_store/backend.py`. New: `scripts/tests/test_session_store_backend.py`. Adapt existing `scripts/little_loops/session_store/schema.py` and promote appropriate tests in the implementation PR.

**Formatting verification**: `ll-issues format-check FEAT-3524` still flags the
three explicitly marked new files (backend module, backend tests, and libSQL
learning-test registry entry) as untracked `stale_file_ref` entries. These are
planned artifacts, not missing existing dependencies; the `New:` label does not
suppress this gate's findings. Do not create empty placeholders to silence it.

## Verification Notes

_Collapsed 2026-09-23 review. Full pass-by-pass records are in git history
(`/ll:verify-issues` 2026-09-22 ×2, 2026-09-23 ×2)._

- ENH-3525 and ENH-3526 are `done` and verified in code: `session_store/backend.py`
  defines `Backend`, `SqliteBackend`, `resolve_backend()`, `connect_readonly()`,
  `open_history()`, `open_history_readonly()`, and the `HistoryError` taxonomy.
  `BackendProvider = Literal["sqlite"]`; no `history.backend` schema key yet.
- Raw `sqlite3.connect(` remains in 7 files: `queue_store.py`,
  `codequery/codegraph.py` (out of scope), `session_store/backend.py` (the chokepoint),
  and `session_store/{schema,sessions,queries}.py` + `issue_history/workspace_quality.py`.
- `.ll/learning-tests/libsql.md` is local-only evidence (bare path / `:memory:`); its
  `libsql.Error` assertion `fail` is an accepted driver divergence that drives the §3
  error contract. `libsql-remote.md` does not exist yet and gates implementation.
- Spike results cover local mechanics only (`spike_attempted`/`spike_completed` are
  accurate for that scope).
- `ll-verify-evidence`: `ok: true`. Decisions log: no active required rules.

_Review — 2026-09-23 (manual):_ found that §7 rejected the only session-ingestion
path (`backfill_incremental`), that `hooks/session_start.py` hardcodes a local target
for the backfill worker, that the config reader pattern ignores `.ll/ll.local.md`,
that the per-process schema cache does not help one-process-per-event hooks, and that
the §8 marker was not gitignored. Added §7a, the §1 config-reader rule, the §8
verification cache + gitignore rule, the §2 Step 1 contingency; settled the identity
audit and snapshot-export decisions; corrected Current Behavior and the call-site
count (~94).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Blocked** | Created: 2026-09-22 | Priority: P3 | Blocked 2026-09-23: Step 1
`libsql-remote` learning test failed required assertions; awaiting re-scope decision
(see [Step 1 Learning Test Result](#step-1-learning-test-result-2026-09-23)).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-23_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Learning Test Hard Override)
**Outcome Confidence**: 43/100 → LOW

### Concerns
- `blocked_by` still lists ENH-3525/ENH-3526 in frontmatter although both are `done` (`format-check`: `stale_prose_dep`, `soft_dep_hard_edge`) — harmless to the Dependencies gate, but stale; clear them.

### Gaps to Address
- **Update 2026-09-23:** `libsql-remote.md` now exists (`proven`, `libsql` 0.1.11) but 7 required assertions failed, triggering the §2 contingency — re-scope decision required before any further confidence check.
- ~~`.ll/learning-tests/libsql-remote.md` does not exist (`ll-learning-tests check libsql-remote` → "no record found")~~, so the Learning Test Hard Override forces STOP regardless of aggregate. Remedy: produce it as Implementation Step 1 against a local `sqld`/`turso dev` server and Turso Cloud, with every required assertion recorded and `proven_package`/`proven_version` set. Auto-provision via `/ll:explore-api` was not run: it needs a real remote endpoint/token and the driver is not installed.
- `libsql` is `proven` with 1 failing claim (`libsql.Error` assertion). Accepted driver divergence that drives the §3 error contract — costs Criterion 1 the −5 modifier, not a new gap.

### Outcome Risk Factors
- Broad enumeration across ~94 chokepoint entry-point call sites plus ~20 downstream modules and ~35 CLI modules to audit — Complexity Breadth 0/12; Change Surface 0/25 (11+ dependents, site-specific judgment).
- Deep per-site complexity: target-type refactor (`_resolve_once()` → `HistoryTarget`, `Backend` protocol change), mixed-version migration policy (§9), project-identity guard (§10), and remote ingestion with per-machine watermark (§7a) are contract changes, not mechanical edits — Complexity Depth 0/13.
- Remote-driver behavior (transactions, timeouts, cross-thread use) is unproven until `libsql-remote.md` passes; §7a is a self-contained workstream and the natural split candidate to cut scope.
- Design decisions are now settled (Ambiguity 18/25); residual ambiguity is only whether a provenance column proves necessary.

## Session Log
- `/ll:decide-issue` - 2026-09-24T00:43:19 - `037fa15a-ec40-4d82-9ee3-839372456150.jsonl`
- `/ll:confidence-check` - 2026-09-23T19:50:48 - `cf354bec-9945-4c26-8202-11a55059cbe8.jsonl`
- `/ll:verify-issues` - 2026-09-23T19:34:44 - `9cdcff0a-0bc1-428a-980c-013e7aa2e589.jsonl`
- `/ll:confidence-check` - 2026-09-23T01:16:53 - `ca2bbd8f-3da0-4e15-879e-719591e63547.jsonl`
- `/ll:verify-issues` - 2026-09-23T00:54:56 - `6dfad5ef-a609-4642-b1de-e08c59354d9f.jsonl`
- `/ll:verify-issues` - 2026-09-22T23:39:48 - `719ed6d0-2e4e-41db-ae76-8176f4dcd29a.jsonl`
- `/ll:review-issue` - 2026-09-22T20:23:55 - `a4d36fa6-881b-478d-9b3a-16179bad6635.jsonl`
- `/ll:verify-issues` - 2026-09-22T19:21:07 - `6cde693c-199f-46be-be94-59e50bb11494.jsonl`
- `/ll:wire-issue` - 2026-09-22T16:47:36 - `48d447aa-e589-42cb-96ec-cab26ee6a78c.jsonl`
- `/ll:refine-issue` - 2026-09-22T16:30:06 - `49a7e360-74a8-4694-abcb-c3e17b0da6de.jsonl`
- `/ll:wire-issue` - 2026-09-22T16:11:57 - `d11b4d88-e05e-48db-9617-b48caee451f5.jsonl`
- `/ll:spike` - 2026-09-22T16:01:14 - `69316b42-0fe0-49ed-a8dc-481387700cff.jsonl`
- `/ll:refine-issue` - 2026-09-22T15:53:02 - `24e361bf-844f-4527-b6ee-85c86b44db2a.jsonl`
- `/ll:format-issue` - 2026-09-22T15:43:55 - `f8344c01-034b-4d86-8218-d0d7fb43cbd5.jsonl`
- `/ll:capture-issue` - 2026-09-22T15:39:46 - `eaf98e36-fcf5-4247-8879-8cd909331a2a.jsonl`
