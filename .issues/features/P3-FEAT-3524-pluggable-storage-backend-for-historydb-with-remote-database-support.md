---
id: FEAT-3524
type: FEAT
title: Pluggable history.db backend with remote libSQL support
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-22'
captured_at: '2026-09-22T15:39:38Z'
learning_tests_required:
  - libsql
spike_attempted: true
spike_completed: true
verify_verdict: NON_VALID
---

# FEAT-3524: Pluggable history.db backend with remote libSQL support

## Summary

Allow little-loops users to share a history store across machines running the same
project by configuring a remote libSQL database through `history.backend` in
`.ll/ll-config.json`. Preserve local SQLite as the unchanged default. This issue
implements SQLite and the Python `libsql` driver's direct remote mode only;
Postgres, MySQL, other Turso engines/drivers, and embedded-replica synchronization
are out of scope.

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

An unset `history.backend` or `kind: sqlite` preserves today's local behavior.
With `kind: libsql`, `ll-history`, `ll-logs`, session digests, compaction reads and
writes, and event sinks use the configured remote history store. Unsupported
FTS5/maintenance/export operations report a clear capability limitation rather
than crashing or silently using a different local store. Compatibility is proven
for the selected remote driver and deployment, not inferred from SQLite syntax.

Best-effort telemetry must not abort the operation it observes; explicit reads,
migrations, and maintenance must expose actionable failures. `ll-doctor` provides
an explicit, bounded, non-mutating connectivity/authentication/schema diagnostic.

## Motivation

Teams running little-loops across several machines or CI runners (e.g. the self-hosted runner) have no way to share one history/analytics store. A remote backend enables cross-machine `ll-history` / `ll-logs` analytics, session digests, and compaction context without syncing `.db` files, and unblocks hosted dashboards reading the same store.

## Proposed Solution

Introduce `history.backend` with `kind: sqlite|libsql`, endpoint settings
`url`/`url_env`, and `auth_token_env`. Implement a lazy-loaded backend resolver
following `codequery.core.resolve_provider`, with connection, cursor, row,
transaction, and error contracts derived from actual history consumers. Route
history-store connections through it while preserving deliberately local stores
and scratch artifacts.

Reuse compatible SQL and the existing migration sequence only after real-driver
learning tests prove it. Capability handling must cover connection setup,
read-only access, search, maintenance, and local snapshot export. A connection
chokepoint is necessary but does not remove SQL, filesystem, transaction, or
network-latency assumptions. See Proposed Design and the remaining readiness
questions below.

## Integration Map

### Files to Modify
- New: `scripts/little_loops/session_store/backend.py` — resolver and adapter contracts
- `scripts/pyproject.toml` — justified optional `libsql` extra after driver proof
- `little_loops/session_store/__init__.py` — preserve public connection/path contracts
- `little_loops/issue_manager.py` and other `SQLiteTransport` constructors — target resolution and lifecycle
- `little_loops/session_store/db.py` (`_resolve_db_path`, `resolve_history_db`)
- `little_loops/session_store/schema.py` (`ensure_db`, `_configure_connection`, `_apply_migrations`)
- `little_loops/session_store/{sessions,queries,lifecycle,writers}.py`
- `little_loops/history_reader/_base.py`
- `little_loops/issue_history/*`
- `little_loops/cli/{history,logs,doctor,doctor_trim,ctx_stats}.py`
- `little_loops/queue_store.py`, `little_loops/codequery/codegraph.py` — audit only to distinguish history consumers from independent local stores; do not migrate `queue.db` or codegraph databases
- `little_loops/config-schema.json` (`history` block, line 2138 — add `backend`)

_Wiring pass added by `/ll:wire-issue`:_
- `little_loops/cli/session.py` — `help=` strings hardcode SQLite feature names for FTS5/VACUUM (`:117`, `:118`, `:269`, `:356`, `:368`); must stay accurate or become conditional once these features are capability-gated on non-sqlite backends [Agent 2 finding]
- `little_loops/cli/doctor.py:547` — `_schema_drift_data()` opens its own `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`, bypassing the proposed `connect_readonly()` chokepoint; also resolves `db_path` via `Path.cwd() / DEFAULT_DB_PATH` (`:542`) rather than `resolve_history_db()` [Agent 2 finding]
- `little_loops/cli/history.py:793-802` — a fourth ad-hoc `sqlite3.connect(str(db_path))` inside the `root` subcommand handler, separate from the module's already-known connect sites [Agent 2 finding]
- `little_loops/issue_history/workspace_quality.py:108-120` — `_open_member_readonly()` is a third independently-duplicated read-only-open helper (raw `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`), beyond the two already cited in Codebase Research Findings (`issue_history/evolution.py:30`, `codequery/codegraph.py:81`) [Agent 2 finding]

_Second wiring pass added by `/ll:wire-issue`:_
- `little_loops/decisions.py:578-605` (`generate_from_completed()`) — hardcodes `project_root / ".ll" / "history.db"` and gates on `.exists()`, bypassing `resolve_history_db()`/`LL_HISTORY_DB`/`history.backend` entirely; under `kind: libsql` this path never exists, so the function silently and permanently falls back to filesystem scanning instead of ever reading the remote backend — a real behavioral gap, not a deliberately-local store [Agent 2 finding]
- `little_loops/issue_history/parsing.py` — `scan_completed_issues_from_db()` and `HistoryDbUnavailable`, called from the `decisions.py` coupling above; previously covered only implicitly by the `issue_history/*` wildcard [Agent 1 finding]
- `little_loops/history_reader/_base.py:60` — `_connect_readonly()` is a distinct fourth readonly-open duplicate (opens `file:{db_path}?mode=ro`); its docstring documents that it deliberately does NOT re-resolve `db_path` through `ensure_db()`'s env/config chain, to avoid silently redirecting an already-root-anchored absolute path (BUG-3181) — a contract the new `connect_readonly()` chokepoint must preserve [Agent 2 finding]

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
- New: `.ll/learning-tests/libsql.md` — required real remote driver/version evidence
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
- **No existing `connect_readonly()` counterpart anywhere in the tree** (repo-wide search, zero hits). The closest analog is two independently-duplicated private `_open_db()` helpers — `issue_history/evolution.py:30` and `codequery/codegraph.py:81` — both opening `file:{path}?mode=ro` with `uri=True` and `PRAGMA query_only = ON`, never raising (`except sqlite3.Error: return None`). The `codegraph.py` copy's docstring states it explicitly mirrors the `evolution.py` one rather than sharing a common module — i.e. the current convention for a read-only SQLite open is duplication-by-mirroring, not a shared function.
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

1. Complete the `libsql` learning-test gate against a real remote endpoint: pin
   the tested driver/version as a justified optional extra; prove connection,
   cursor/row, transaction, read-only, error, authentication, and timeout behavior.
   Resolve the readiness questions below before committing to the adapter design.
2. Add `history.backend` config and resolver contracts. Define endpoint/env and
   explicit-local-path precedence without changing SQLite defaults; reject
   unsupported kinds and invalid combinations with redacted diagnostics.
3. Implement the backend adapter and route history consumers through it. Include
   public re-exports and `SQLiteTransport` construction, serialized cross-thread
   writes, shutdown, and error handling; audit filesystem existence checks and
   local-path assumptions as well as direct connection sites.
4. Adapt connection setup and migrations using `meta.schema_version`. Verify the
   full migration chain, concurrent initialization, atomic rollback, schema-ahead
   behavior, and genuinely non-mutating reads against the remote driver. Do not
   promote the SQLite-backed spike as remote compatibility evidence.
5. Implement capability handling and the chosen snapshot/export behavior.
   Preserve local scratch SQLite output for supported dashboard snapshots; if
   remote export is deferred, explicitly gate it and document the limitation.
   Preserve same-project identity and foreign-machine source-path behavior as
   settled in the readiness decisions.
6. Normalize backend errors. Bound network waits; keep event sinks best-effort
   with rate-limited redacted warnings, but surface explicit read/migration/
   maintenance failures. Specify reconnect/retry behavior without blindly
   retrying writes whose commit outcome is unknown.
7. Add an explicit `ll-doctor` backend diagnostic that checks connectivity,
   authentication, and schema compatibility without migrations or writes.
8. Add focused local regressions and remote integration coverage, then update
   configuration/API/CLI docs. Remote tests skip only when their required test
   configuration is absent; a configured endpoint failure fails the test.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `little_loops/cli/session.py` — make FTS5/VACUUM `help=` strings (`:117`, `:118`, `:269`, `:356`, `:368`) conditional or caveat them once these features are capability-gated
- Update `little_loops/cli/doctor.py:547` — route `_schema_drift_data()`'s raw readonly connect through the new `connect_readonly()` chokepoint instead of its own `sqlite3.connect(...mode=ro...)`; also resolve `db_path` via `resolve_history_db()` rather than `Path.cwd() / DEFAULT_DB_PATH` (`:542`)
- Update `little_loops/cli/history.py:793-802` — route the `root` subcommand's ad-hoc `sqlite3.connect(str(db_path))` through the new chokepoint
- Update `little_loops/issue_history/workspace_quality.py:108-120` — fold `_open_member_readonly()` into the shared `connect_readonly()` chokepoint rather than a third independent duplicate
- Add `scripts/tests/test_config_schema.py` assertion block for `history.backend` (pattern at `:624-633`)
- Update `docs/reference/CONFIGURATION.md:608-662`, `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/ARCHITECTURE.md:89,636,832`, `docs/guides/HISTORY_SESSION_GUIDE.md:634`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:251` — reflect the new backend, capability-gated FTS5/VACUUM caveats, and check the `queue_store.py`-mirrors-`session_store` description against the retained local-only queue scope in `docs/ARCHITECTURE.md:832`
- Audit and verify the ~20 downstream consumers of `session_store`'s public re-export surface listed under Dependent Files, to confirm they still work against the adapter contracts; change callers where path or connection assumptions require it

### Wiring Phase (added by second `/ll:wire-issue` pass)

_These additional touchpoints were identified by a second wiring pass and must be included in the implementation:_

- Route `little_loops/decisions.py::generate_from_completed()` through `resolve_history_db()`/the backend chokepoint instead of its hardcoded `.ll/history.db` path check, so it doesn't permanently and silently fall back to filesystem scanning under `kind: libsql`
- Fold `little_loops/history_reader/_base.py:60` (`_connect_readonly()`) into the shared `connect_readonly()` chokepoint while preserving its documented no-re-resolve contract (BUG-3181)
- Update `little_loops/cli/backfill_worker.py:52,70,78` — route the `REGISTERED_HOSTS`/`host_layout_for`/`backfill_incremental` lazy imports through the backend-aware path
- Audit the ~35 CLI modules that only import `DEFAULT_DB_PATH, cli_event_context` (Dependent Files) — confirm `cli_event_context`'s best-effort contract holds unchanged under the new backend; no code change expected unless `DEFAULT_DB_PATH`'s type itself changes
- Add: dedicated test coverage for `little_loops/cli/compact_session.py`'s CLI wrapper (currently untested at that layer)
- Update `skills/configure/areas.md` `## Area: history` (+ `.qwen/`, `.kimi-code/`, `.gemini/` mirrors) — add a `history.backend` configuration question

## Impact

- **Priority**: P3 — shared same-project history is useful; local history remains functional.
- **Effort**: Large — connection routing plus cursor/row contracts, transaction and
  migration compatibility, error normalization, local-file operations, and remote
  round-trip costs. Package-wide SQLite-idiom counts include excluded stores and
  are not an effort estimate. Postgres/MySQL dialect translation is separate work.
- **Risk**: Medium to high until real-driver proofs pass — routing mistakes,
  partial migrations, ambiguous network write outcomes, and shared-store identity
  can lose or misattribute history. The existing spike retires only local mechanics.
- **Breaking Change**: No intended change for default SQLite users; remote support
  is opt-in and any unsupported remote operations must be documented explicitly.

## Current State

- `history.db_path` (config-schema.json, `history` block) only overrides the **local filesystem path** of `history.db`; relative paths resolve against the project root and the `LL_HISTORY_DB` env var takes precedence (ENH-2623). Resolution lives in `little_loops.session_store.db._resolve_db_path` / `resolve_history_db`.
- The storage layer is hardcoded to `sqlite3`. `little_loops.session_store.schema.ensure_db` opens `sqlite3.connect(str(db_path))` and applies `_configure_connection` (busy_timeout, `PRAGMA journal_mode = WAL`) plus `_apply_migrations`.
- `sqlite3.connect(` appears at roughly 28 call sites across ~15 modules (session_store/{schema,sessions,queries,lifecycle,writers}.py, history_reader/_base.py, issue_history/*, cli/{history,logs,doctor,doctor_trim,ctx_stats}.py, queue_store.py, codegraph.py). Many use `file:{path}?mode=ro` URI connections, PRAGMAs, and FTS5 — SQLite-specific features.
- `history.workspace_manifest_path` (FEAT-3409) aggregates **multiple local** `history.db` files across repos declared in a workspace manifest; it is not a live remote connection.

## Proposed Design

1. Configure one selected backend, for example:
   ```json
   {
     "history": {
       "backend": {
         "kind": "libsql",
         "url_env": "LL_HISTORY_URL",
         "auth_token_env": "LL_HISTORY_AUTH_TOKEN"
       }
     }
   }
   ```
   Support a non-secret literal `url` or `url_env`, with exactly one endpoint
   source for libSQL. Never commit tokens; redact credentials from errors and
   diagnostics. Unset backend / `kind: sqlite` preserves `db_path` and
   `LL_HISTORY_DB`. Specify remote-mode interactions with explicit local paths
   and SQLite-only overrides before implementation; never silently fall back to
   a local history store after remote failure.
2. Select Python `libsql` direct remote connections, not embedded replicas or
   `turso_serverless`. Keep the driver behind a justified, version-bounded optional
   extra with a clear missing-extra error. Prove the selected version against the
   intended deployment before implementing production consumers. Official driver
   distinctions and token usage: https://github.com/tursodatabase/turso-docs/blob/main/sdk/python/quickstart.mdx
3. Resolve adapters lazily. Define connection, cursor, row, transaction, and error
   contracts from consumer usage. Do not assume `sqlite3.Connection` inheritance,
   `sqlite3.Row` compatibility, or identical exception classes. Update annotations
   only for code that accepts multiple backends; retain SQLite types for truly
   local-only operations.
4. History migration versioning uses `meta.schema_version`, not
   `PRAGMA user_version`. Reuse migration SQL where proven compatible; verify
   `BEGIN IMMEDIATE`/isolation control or an equivalent atomic locking sequence,
   rollback, version re-read under lock, full migrations, and schema-ahead checks.
   Read-only access and diagnostics must not create or migrate the remote store.
5. Determine capabilities from tested driver/deployment behavior. Gate WAL setup,
   FTS5, maintenance, and snapshot export as appropriate; SQLite dialect support
   does not prove all PRAGMAs or file operations work remotely. Audit network
   round trips in migration/event paths rather than assuming local latency.
6. Preserve failure policy per operation: event telemetry is best-effort with
   bounded waits and rate-limited warnings; explicit reads/migrations/maintenance
   report failures. Define reconnect and ambiguous-commit handling. Doctor checks
   are explicitly invoked, bounded, non-mutating, and redact secrets.
7. Sharing is limited to machines running the same logical project. Before
   implementation, settle project/session/event identity and how machine-local
   `jsonl_path`/`project_path` values are represented and consumed. Add provenance
   only if needed for correctness; machine-filtered analytics are not required.
8. Out of scope: Postgres/MySQL or a general SQL dialect layer; other Turso
   engines/drivers; embedded replicas/offline synchronization; migrating
   `queue.db` or codegraph databases; workspace-manifest aggregation over remote
   backends; unrelated-project multitenancy and machine-filtered analytics.

## Program Design

### Types

- `BackendKind: Literal["sqlite", "libsql"]`
- `BackendConfig: dataclass` (`kind: BackendKind`, `url: str | None`,
  `url_env: str | None`, `auth_token_env: str | None`)
- New: `HistoryConnection`, `HistoryCursor`, and `HistoryRow` protocols in the
  proposed backend module. Inventory required methods/properties from consumers:
  `execute`, `executemany`, commit/rollback/close, transaction/isolation semantics,
  cursor fetching/iteration, `lastrowid`, `rowcount`, and indexed/named row access.
  Adapt row-factory behavior internally; finalize exact signatures after driver
  learning tests. A five-method connection protocol is insufficient.
- Backend-neutral error categories distinguish unavailable/authentication,
  integrity, unsupported operation, and other query/migration failures; adapters
  preserve causes without leaking credentials.

### Signatures

- `resolve_backend(config: dict) -> Backend` — lazy registry following `resolve_provider`
- `Backend.connect(self) -> HistoryConnection`
- `Backend.connect_readonly(self) -> HistoryConnection`
- `Backend.ensure_schema(self) -> None`
- `Backend.supports(self, capability: str) -> bool`

### Call Path

Project configuration + explicit target policy -> `resolve_backend` -> connection
adapter -> history consumer. Write initialization invokes `ensure_schema` and the
proven migration sequence; read-only/doctor paths must not invoke migrations.
Preserve public local-path APIs where needed: `ensure_db()` currently returns a
`Path`, so a remote target must not be represented as a fabricated filesystem path.
Finalize that integration contract before changing callers.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- No backend-neutral error-category wrapper exists to model the "unavailable/auth, integrity, unsupported-operation, other" categories on: `session_store/schema.py`, `queries.py`, `lifecycle.py`, `writers.py` all catch and branch on raw `sqlite3.OperationalError`/`sqlite3.IntegrityError` directly at each call site (e.g. `schema.py:1458`, `:1485`; `queries.py:56`, `:212`, `:379`; `lifecycle.py:1447`), with no wrapped-exception hierarchy anywhere in the codebase. This taxonomy is new design, not a shared abstraction to reuse.
- No existing convention masks a specific env-var-sourced credential value in error messages or diagnostic output. `pii.py`'s `redact_pii`/`CREDENTIAL_RULES` scans free-text corpora for embedded secrets (email/token/key regex patterns) for SFT training-data export (`cli/logs.py::_redact_input_context` is its only other caller) — it is not wired into any error-message or `ll-doctor`-style diagnostic path today. `host_runner.py`'s `CREDENTIAL_SCOPES` controls which env vars a child process inherits rather than masking a value for display — a different concern (access control, not display redaction). `auth_token_env` redaction in error/diagnostic output has no in-tree pattern to extend.
- The closest structural analog for the `ll-doctor` backend diagnostic is `doctor.py`'s existing `_history_db_data()`/`@register_check _history_db_check()` pair (`doctor.py:444-513`): a pure `_xxx_data()` function that never raises and never creates the resource it probes (explicitly checks `Path.exists()` before calling `connect()`/`ensure_db()`, since both create-on-demand), returning a dict adapted by a thin `@register_check`-decorated function into `CheckResult(status: Literal["full","partial","unsupported"], note, severity: Literal["error","informational"])`. No existing doctor check in this codebase probes a network resource — every one of the currently registered checks operates on local filesystem/SQLite state, so there is no in-tree precedent for the connectivity/timeout half of the new check beyond this local-probe shape.
- The Proposed Design's and this section's chosen selector key name (`"kind": "libsql"`, `BackendKind`) diverges from this codebase's only two existing discriminated-backend-selector precedents, both of which name the key `provider` rather than `kind`: `sync.provider` and `code_query.provider` (`config-schema.json:1390`, `:1449`). A repo-wide search of `config-schema.json` found no existing schema block using `kind` as a selector property name. This is a naming-convention deviation to make knowingly, not an error.

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

## Open Questions

The backend choice is resolved: libSQL first; Postgres/MySQL are excluded. The
optional-extra policy and explicit doctor diagnostic are also resolved.

The following remain readiness blockers, to be answered with driver learning tests
and caller analysis rather than hidden by closing this section:

- What exact driver version, adapter contracts, and transaction/read-only mechanism
  pass the real remote compatibility checks, including the full migration chain?
- How do explicit local-path arguments, `LL_HISTORY_DB`, and `history.db_path`
  interact with a configured remote backend while preserving local scratch stores
  and the existing `ensure_db() -> Path` / `resolve_history_db() -> Path` APIs?
- What same-project/session/event identity rules prevent collisions across machines,
  and how should readers handle foreign-machine source paths? Is provenance needed
  for correctness, and if so how are existing rows handled?
- Will remote dashboard snapshots be materialized into local SQLite via bounded
  row transfer, or explicitly unsupported in this first cut? Preserve filtering
  and redaction if supported; do not imply remote `ATTACH` creates a local file.

## Acceptance Criteria

- [ ] Readiness questions above are resolved and recorded; the `libsql` learning
  gate proves the selected version and remote mode. No Postgres/MySQL support or
  `psycopg` dependency is included.
- [ ] Config supports `sqlite|libsql`, endpoint env references, and a separate token
  env reference. Invalid combinations, missing extras, and auth errors produce
  redacted diagnostics. Default SQLite path/env precedence tests remain unchanged.
- [ ] All in-scope history connections use the backend adapter; independent local
  stores and scratch artifacts remain local. Explicit-path precedence and public
  path-returning APIs have regression coverage; remote failures never silently
  switch history to a local database.
- [ ] Connection/cursor/row and transaction contracts are exercised for both
  adapters, including named/indexed rows, fetching, insert IDs, affected-row counts,
  and error mapping used by consumers.
- [ ] Real remote tests cover the full migration chain using `meta.schema_version`,
  repeat initialization, concurrent initialization, rollback after failure, and
  schema compatibility. Read-only access does not create or migrate the store.
- [ ] `ll-history`, `ll-logs`, session digests, and compaction reads/writes work
  against the remote store. `SQLiteTransport` lifecycle and serialized cross-thread
  writes work through the adapter and remain best-effort under remote failure.
- [ ] Network operations have bounded waits. Event-sink failures warn without
  aborting the observed operation; explicit reads/migrations/maintenance report
  failure. Tests cover failure policy, redaction, and ambiguous-write retry rules.
- [ ] Same-project sessions/events from two machines remain correctly attributed;
  foreign-machine paths do not masquerade as local readable sources. Implement
  and test any provenance needed by the documented identity decision.
- [ ] Unsupported search/maintenance/export features produce clear capability
  messages. Supported snapshot export preserves filtering/redaction and creates
  a local SQLite artifact; otherwise its remote limitation is explicit and tested.
- [ ] An explicit `ll-doctor` check diagnoses connectivity/authentication/schema
  compatibility with a timeout, no migrations/writes, and redacted output.
- [ ] Remote integration tests skip only when test configuration is absent;
  failures with a configured endpoint fail the tests. Local regressions pass.
- [ ] User docs cover backend selection, optional installation, secrets, precedence,
  same-project sharing, failure behavior, diagnostics, and capability limitations.

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

_Added by `/ll:verify-issues` — 2026-09-22:_

Verdict: NEEDS_UPDATE. Graph checks used `provider=codegraph`, `freshness=fresh`
(§2B.0), so anchor/negative-claim results below are treated as confirmed, not leads.

- **Spot-checked file:line citations** across Files to Modify, both wiring passes,
  and Program Design (`schema.py:1492,1443`; `codequery/core.py:103,93-96,39-44`;
  `host_runner.py:2535,294-318`, ~15 total) — all accurate, no drift.
- **Spike Results table** — confirmed real:
  `scripts/tests/spike/session_store_backend_dialect/{backend.py,dialects.py}` and
  `.ll/spikes/spike-FEAT-3524.md` exist; all 7 named tests
  (`TestDialectMigration::*`, `TestConcurrentMigration::*`, `TestCapabilityGate::*`,
  `TestSpikeIsolation::*`) ran and passed, matching the claimed result.
- **Negative/dead-code claims** (no `connect_readonly()`, no `dialect`
  abstraction, `except Unsupported` only at `cli/code.py:146`, no
  `postgres|libsql|psycopg|sqlalchemy` in `pyproject.toml`) — all still hold as of
  today.
- **Proposal-vs-code (check B6)** — no new inconsistency found; the
  `ensure_db() -> Path` fabricated-path tension is already self-flagged under Open
  Questions, not a silent defect.
- **`## Blocked By`/`## Blocks`** — neither section exists; no dependency
  references to validate.
- **Gap found — `.ll/learning-tests/libsql.md`**: frontmatter `status: proven`
  gates `learning_tests_required: [libsql]` mechanically, but the artifact does not
  substantiate what the issue's own Acceptance Criteria and Implementation Steps
  require. All 7 assertions connect via a bare local path or `:memory:`; none
  exercise `url`/`auth_token_env`/network/timeout/remote-mode behavior (the last
  assertion explicitly tests the *local*-only case). AC #1 requires the gate to
  prove "the selected version **and remote mode**" — it currently proves neither.
  Separately, one assertion ("invalid SQL and constraint violations raise
  `libsql.Error`, not `sqlite3.Error` or a subclass of it") has `result: fail`,
  yet the record's overall `status` is still `proven` with no note reconciling
  the two.

Remaining: this readiness blocker is not auto-correctable by this command (it
requires a real remote endpoint to re-run the learning test) — `.ll/learning-tests/libsql.md`
needs remote-mode assertions added and the `fail` result triaged (fixed, or
explicitly accepted and documented as a known driver divergence) before the
Open Questions / AC #1 readiness gate can be considered resolved. `spike_completed:
true` and `spike_attempted: true` in frontmatter remain accurate for what they
claim (local spike mechanics only) and are not affected.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-22 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-22T19:21:07 - `6cde693c-199f-46be-be94-59e50bb11494.jsonl`
- `/ll:wire-issue` - 2026-09-22T16:47:36 - `48d447aa-e589-42cb-96ec-cab26ee6a78c.jsonl`
- `/ll:refine-issue` - 2026-09-22T16:30:06 - `49a7e360-74a8-4694-abcb-c3e17b0da6de.jsonl`
- `/ll:wire-issue` - 2026-09-22T16:11:57 - `d11b4d88-e05e-48db-9617-b48caee451f5.jsonl`
- `/ll:spike` - 2026-09-22T16:01:14 - `69316b42-0fe0-49ed-a8dc-481387700cff.jsonl`
- `/ll:refine-issue` - 2026-09-22T15:53:02 - `24e361bf-844f-4527-b6ee-85c86b44db2a.jsonl`
- `/ll:format-issue` - 2026-09-22T15:43:55 - `f8344c01-034b-4d86-8218-d0d7fb43cbd5.jsonl`
- `/ll:capture-issue` - 2026-09-22T15:39:46 - `eaf98e36-fcf5-4247-8879-8cd909331a2a.jsonl`
