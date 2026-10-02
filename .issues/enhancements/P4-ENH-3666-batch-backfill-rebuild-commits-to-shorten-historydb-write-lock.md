---
id: ENH-3666
type: ENH
title: Batch backfill --rebuild commits to shorten history.db write lock
priority: P4
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T15:29:40Z'
verify_verdict: VALID
confidence_score: 85
outcome_confidence: 54
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
size: Large
blocked_by:
- ENH-3699
relates_to:
- ENH-3679
deferred_by: human
deferred_date: '2026-09-30T01:00:27Z'
deferred_reason: blocked_by_unmet
---

# ENH-3666: Batch backfill --rebuild commits to shorten history.db write lock

> **Re-scoped 2026-09-30** after a `/ll:advise` (Opus) review. **This banner supersedes conflicting text below** (title left as-is for link stability; the design is now a shadow-build, not per-phase commits).
>
> **Premise correction.** The trigger is `last_rebuild_version < SCHEMA_VERSION` (`hooks/session_start.py:~213`): ~20 bumps since June, several changing no `_REBUILD_TABLES` derivation, each forcing a full multi-GB replay, with no single-flight guard. Fix the trigger and the dropped-telemetry symptom first: ENH-3678 (derive-version gate), ENH-3698 (size gate + pending notice) and **blocked_by ENH-3699** (single-flight flock + cooldown; itself `blocked_by` ENH-3678; split from ENH-3678 2026-10-02); ENH-3679 (short phase budgets + drop counter for CLI telemetry; spool separately deferred) is `relates_to` only. Dissent recorded: the incident bumps (09-23, 09-24, 09-29) *did* change usage derivation, so ENH-3678 alone would not have prevented that rebuild; this structural fix stays necessary. Consider also rebuilding `usage_events` only via the existing incremental `_USAGE_DERIVE_VERSION` path and making the other tables' rebuild per-table and derive-versioned, which may shrink this issue further; evaluate after ENH-3678 lands. Priority may drop to P4 until rebuilds still hurt after ENH-3678.
>
> **2026-09-30 update (`/ll:advise` Opus): deferred at P4.** Blocked only by ENH-3699 (the single-flight lock slice of the former ENH-3678; the derive-version gate stays in ENH-3678) (ENH-3679 is a symptom mitigation, not a prerequisite). Opus overruled the dissent below: a store at `last_rebuild_version == 58` was already rebuilt under current code, and ENH-3678 sends usage-only derivation changes through `_USAGE_DERIVE_VERSION`, so the incident bumps would not recur. Re-open and re-score only if rebuilds still hurt after ENH-3678 and ENH-3698 ship. Open items to resolve first when reactivated: whether hook-written `tool_events`/`skill_events`/`message_events`/`sessions` rows always have a `raw_events` counterpart (unverified), FTS5 `search_index` handling, and taking `_compact_sessions` out of `rebuild()`.
>
> **Decision (Implementation Step 1 is settled; no `/ll:decide-issue` needed): shadow-build with bounded batches, then a rename-only swap.**
> - *Rejected:* per-phase commits + `rebuild_in_progress` marker (readers see empty/half tables and none check the marker; `project_digest` runs at SessionStart right after the worker spawns; usage/cost reports would show zero); id-range chunking (parsers depend on cross-range order: `usage_order` sorts by `source_path, ordinal`, session aggregates and `mine_corrections` need whole sessions); `wal_autocheckpoint`/`nice` (do not help a single long txn / lengthen the hold).
> - *Parse outside the lock* is a component of the shadow design: read `raw_events WHERE id <= H` in a read snapshot (no lock under WAL), write into `<table>__rb` tables in batched txns. Create indexes on the empty shadow tables before inserting.
> - *Swap:* rename live→`_old` and `__rb`→live in one short txn; **never DROP a GB table inside the swap txn**; drain `_old` in batched deletes afterwards, then drop when empty. The swap txn contains only the renames (assert by statement count, not wall time).
> - *`search_index`* is a shared FTS5 table and cannot be swapped as a unit: select target rowids from a read snapshot, then delete+insert in rowid batches; document that search for the rebuilt kinds is briefly inconsistent.
> - **`H`:** capture `MAX(raw_events.id)` once at start; every replay cursor is `WHERE id <= H`; `_set_usage_derive_checkpoint` records `H` (not `MAX(id)` at call time, which would mark mid-rebuild `raw_events` as derived and lose them permanently); rows `id > H` are then replayed incrementally after the swap.
> - **Live-writer rows:** hooks insert directly into `tool_events` (`hooks/post_tool_use.py:~202`), `skill_events` (`writers.py:~328/743/4558`), `message_events` (`writers.py:~4360`) and `sessions` (`fsm/continuity.py:~61`) with no dedup key. **First verify** whether hook-written rows always have a `raw_events` counterpart. If yes, replay `id > H` after the swap covers them; if not, copy rows with `ts >= build_start` from old to new inside the swap txn. Either way assert no loss and no duplicate in a test.
> - **Hold the existing `<db>.usage-refresh.lock` flock** (`backfill_worker.py:~48`) for the rebuild's whole run so the usage-trigger worker (every Stop hook), `backfill_usage_incremental`, `refresh_usage_source` and `refresh_raw_events` cannot interleave.
> - **Take `_compact_sessions` out of `rebuild()`** (it holds the txn across a host-CLI subprocess and opens a second writer connection) and decide whether `summary_nodes`/`summary_spans` leave `_REBUILD_TABLES` (they hold non-reproducible LLM output that a wipe discards). Either changes rebuild's documented contract; check the 9-key return dict consumers.
> - **Batch budget:** commit at 2,000 rows or 250 ms, then sleep ~50 ms before re-acquiring (SQLite's busy handler is unfair; commit-then-immediately-`BEGIN IMMEDIATE` can starve waiters even with short txns).
> - **Acceptance criterion rewrite:** replace "no txn holds the lock longer than `_BUSY_TIMEOUT_MS`" (unachievable for a bare `DELETE`/`DROP` on GB tables) with "a concurrent writer at the production busy timeout always succeeds", tested with an injected between-batches hook (thread + barrier, post-state assertions, no wall-clock).
> - **Rollback tests keep their intent, renamed and re-asserted:** `test_rebuild_rolls_back_replacement_when_replay_fails` → `test_rebuild_failure_preserves_live_tables` (live tables untouched, shadow tables cleaned up, meta and checkpoint unchanged); `test_rebuild_failure_rolls_back_usage_delete` → the same for non-live `usage_events`.
> - **New tests:** concurrent `cli_events` insert between batches succeeds; `raw_events` inserted mid-build keeps `usage_derive_raw_id == H` and is picked up incrementally; live `tool_events` insert mid-build has the defined outcome; interrupted build leaves old tables intact plus a detectable leftover `__rb`/marker that the next run cleans up; `project_digest` returns old data during the build.
> - **Size:** stays Large; re-score confidence after the `H`/live-writer verification.

## Summary

`rebuild()` in `scripts/little_loops/session_store/lifecycle.py` wipes and re-derives all JSONL-sourced cache tables inside one `BEGIN IMMEDIATE` transaction, so `history.db` is write-locked for the whole replay. On a large store this exceeds the 5000 ms `_BUSY_TIMEOUT_MS` (`session_store/schema.py`) that every other `ll-*` process waits, and their telemetry writes fail.

## Current Behavior

`rebuild()` runs `BEGIN IMMEDIATE`, deletes every `_REBUILD_TABLES` row (plus `search_index` rows for `_REBUILD_SEARCH_KINDS`), replays all `raw_events` through the `_backfill_*` parsers, runs `mine_corrections_from_messages` and `_compact_sessions`, writes `last_rebuild_version` and the usage-derive checkpoint, and issues a single `conn.commit()` at the end. The write lock is held for the entire replay. Other `ll-*` writers wait only `_BUSY_TIMEOUT_MS` (5000 ms) and then fail with `database is locked`, dropping their telemetry rows.

## Expected Behavior

`rebuild()` holds the write lock in short bursts (each under `_BUSY_TIMEOUT_MS`) so concurrent writers interleave and succeed, while readers still never observe a silently partial derived-table set, and `last_rebuild_version` / the usage-derive checkpoint are set only after the whole rebuild completes.

## Motivation

Observed 2026-09-29 with a ~9.6 GB `history.db` and a ~1 GB WAL: a detached `little_loops.cli.backfill_worker ... --rebuild` (spawned from the session-start hook) held the write lock for minutes. A concurrent `ll-issues list --group-by epic` logged `cli_event_context: enter failed for 'll-issues' (OperationalError: database is locked)` (`session_store/writers.py`, `cli_event_context`), dropped its `cli_events` row, and took ~12s wall time. Every ll-* command and loop run during a rebuild is affected, not just this one.

## Proposed Solution

Shorten the write-lock window of `rebuild()` without exposing a partially replaced table set. Options to evaluate:

- Build derived tables into shadow tables (or a side DB) in batched transactions, then swap in one short transaction.
- Commit per `_backfill_*` phase with a "rebuild in progress" meta marker so readers/next start can detect and resume an incomplete rebuild.
- Yield the lock between batches (commit + brief sleep) so waiting writers can interleave.

## Scope Boundaries

- **In scope**: batching/yielding the write lock inside `rebuild()`; an atomic-visibility or explicit in-progress mechanism for the derived tables; one concurrent-writer test.
- **Out of scope**: the `database is locked` warning severity, the telemetry-insert timeout, and raising `_BUSY_TIMEOUT_MS` (see Constraints).

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/lifecycle.py` — `rebuild()` (transaction structure, `_REBUILD_TABLES` wipe, meta/checkpoint writes)
- `scripts/little_loops/session_store/writers.py` — `_backfill_*` parsers and `mine_corrections_from_messages` if they need to commit/yield per batch

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/__init__.py` — only if a new public helper is introduced; `rebuild`, `backfill_incremental`, `_REBUILD_TABLES`, `_REBUILD_SEARCH_KINDS`, `_BUSY_TIMEOUT_MS`, `_compact_sessions`, `mine_corrections_from_messages` are already re-exported in `__all__`; `_backfill_sessions`/`_backfill_tool_events`/`_backfill_skill_events`/`_backfill_usage_events`/`_backfill_prompt_opt`/`_set_usage_derive_checkpoint` are **not** re-exported (tests patch them on `lifecycle`) [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py` — `_compact_sessions` / `_maybe_soft_threshold_summary` / `_call_llm_for_summary`: the single host-CLI `subprocess` spawn in this file is pinned by `test_enh3184_spawn_site_guard.py` (`(1, 0)`); do not add a spawn or exemption when restructuring [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — `ll-session rebuild` and `ll-session backfill --rebuild`
- `scripts/little_loops/session_store/lifecycle.py` — `backfill()` and the refresh path call `rebuild(db, config=config, ...)` when `also_rebuild` is set
- `scripts/little_loops/cli/backfill_worker.py` — detached `--rebuild` worker spawned from `scripts/little_loops/hooks/session_start.py` (`handle`)
- `scripts/little_loops/session_store/usage_refresh.py` — documents `rebuild(db)` as the follow-up when `needs_rebuild` is set

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/usage_stop.py` — in `handle`, spawns `little_loops.cli.backfill_worker ... --usage-trigger` on every Claude/Codex Stop; it writes `usage_events` + the `usage_derive_*` checkpoint and today serialises behind `rebuild()`'s lock, so it is a live interleaving writer once the lock is yielded (`backfill_worker.main` rejects `--usage-trigger` with `--rebuild`, so it never rebuilds itself) [Agent 2 finding]
- `scripts/little_loops/cli/backfill_worker.py` — in `_refresh_usage_source`, calls `refresh_usage_source` (a `BEGIN IMMEDIATE` deriver, same hazard class as `_run_usage_trigger`) [Agent 1 finding]
- `scripts/little_loops/cli/session.py` — in `main_session`, `refresh_raw_events` call (~ `refresh` branch) and the "Run ll-session rebuild to re-derive usage and cache tables." hint (~840); argparse `--rebuild` help/epilog text (~15, ~101-103, ~231, ~260-280) [Agent 1/2 finding]
- `scripts/little_loops/cli/ctx_stats.py` — in `_compute_cache_rate_from_usage`, calls `usage_source_freshness`, which reads `usage_derive_version`/`usage_derive_raw_id`; a yielded rebuild that stamps the checkpoint late/early changes what it reports (a `rebuild_in_progress` marker would need a decision here) [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py` — in `usage_source_freshness` and `_derive_usage_incremental_conn`, readers of the `usage_derive_*` checkpoint that `_set_usage_derive_checkpoint` writes; `backfill_usage_incremental` and `refresh_usage_source`/`_refresh_codex_usage_source` also write it [Agent 1/2 finding]
- `scripts/little_loops/session_store/backend.py` — `refuse_on_remote` refusal-reason map has a `"rebuild"` entry ("deletes derived tables globally with no concurrency guarantee"); must remain the first call in `rebuild()` (pinned by `test_remote_operation_matrix.py`), and its reason text becomes stale if rebuild gains concurrency guarantees [Agent 1 finding]
- `scripts/little_loops/session_store/schema.py` — in the `meta` seed DDL (~504-505, `last_rebuild_version` seeded NULL) and `_apply_migrations`; writing `rebuild_in_progress` **inline** (upsert, like `last_rebuild_version`) needs no migration, seed, `SCHEMA_VERSION` bump, or `schema_manifest.json` change — `_schema_manifest()` reads `sqlite_master`/`table_info` only, never `meta` rows [Agent 2 finding]
- Readers named in the conditional-branch analysis (`history_reader/*`, `cli/history.py`, `cli/logs.py`, `issue_history/*`, `cli/doctor.py`) have **no** hit for any rebuild/`usage_derive_*` meta key today; they become touchpoints only if the chosen design has readers check an in-progress marker (`cli/doctor.py` reads `SCHEMA_VERSION` via `_schema_manifest`, not `meta` rows) [Agent 1 finding, inferred]

### Similar Patterns
- `scripts/little_loops/session_store/schema.py` — migration runner wraps its sequence in one `BEGIN IMMEDIATE` (same lock-window trade-off)
- `backfill_snapshots()` in `lifecycle.py` — single-commit backfill without a wipe phase

### Tests
- `scripts/tests/test_session_store_lifecycle.py` — existing `rebuild()` coverage; add concurrent-writer test here
- `scripts/tests/test_enh_omp_normalizer.py`, `scripts/tests/test_session_store_incremental_usage.py`, `scripts/tests/test_backfill_worker_usage_trigger.py` — must keep passing

_Wiring pass added by `/ll:wire-issue`:_

Tests likely to break / re-scope:
- `scripts/tests/test_session_store_lifecycle.py` — `TestCompactSession` (~1341-1496) calls `_compact_sessions(conn, config); conn.commit()` directly and patches `little_loops.session_store.subprocess.run`; a signature change to `_compact_sessions` (e.g. a commit/yield callback) breaks these, in `TestCompactSession` [Agent 3 finding]
- `scripts/tests/test_session_store_lifecycle.py` — existing coverage, update in `TestRebuild::test_rebuild_updates_last_rebuild_version` (~1890): natural home for asserting `last_rebuild_version` is stamped only after every phase [Agent 3 finding]
- `scripts/tests/test_session_store_incremental_usage.py` — in `test_catchup_failure_rolls_back_rows_and_checkpoint` (~189, patches `lifecycle._backfill_usage_events`), `test_failed_append_derive_leaves_committed_cursor_stale`, `test_normalizer_version_change_replays_historical_rows`: not `rebuild()` tests but pin the phase-patching seam (phase functions looked up on `lifecycle` at call time — keep that if phase calls move into helpers) [Agent 3 finding]
- `scripts/tests/test_session_store_usage_refresh.py` — in `test_refresh_recovers_stripped_usage_and_rebuild_is_stable` (~67): asserts `COUNT(*) FROM meta WHERE key LIKE 'usage_derive_%' == 0` after `refresh_raw_events`; a new marker key must not live in the `usage_derive_` namespace (`rebuild_in_progress` is safe) [Agent 3 finding]
- `scripts/tests/test_session_store_schema.py` — in `test_meta_seeds_present` (~900), `test_schema_version_matches_migrations_length`, and the `_REBUILD_TABLES`/`_REBUILD_SEARCH_KINDS` membership guards: break only if the design adds a seeded meta key, a migration-created shadow table, or changes those constants [Agent 2/3 finding]
- `scripts/tests/test_remote_operation_matrix.py` — in `TestRejectedOperations::test_raises_naming_the_operation_before_any_network_call`: requires `refuse_on_remote(db, "rebuild")` to stay first in `rebuild()` [Agent 1/3 finding]
- `scripts/tests/test_hook_session_start.py` — in `TestSessionStartRebuild::test_rebuild_flag_added_on_fresh_db` / `test_rebuild_flag_omitted_when_already_current`: pin the `last_rebuild_version < SCHEMA_VERSION` gate; unchanged if stamp-on-success is preserved [Agent 3 finding]
- `scripts/tests/test_history_store_chokepoint_gate.py` — AST gate forbidding raw `sqlite3.connect(` in `scripts/little_loops/` (only `_ALLOWLIST` entries exempt); a shadow/side-DB design must open connections via `_pkg.connect()`/`open_history()`, not `sqlite3.connect` [Agent 2 finding]
- `scripts/tests/test_enh3184_spawn_site_guard.py` — pins `session_store/lifecycle.py` to `(1, 0)` spawn sites/exemptions [Agent 2 finding]
- Broad `rebuild(` oracle users that must keep passing (output equivalence): `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_session_discovery.py`, `test_enh3534_host_usage_dispatch.py`, `test_enh3543_usage_coverage.py`, `test_claude_usage_producer.py`, `test_ll_session.py` (~1208-1240, ~1549), `test_assistant_messages.py`, `test_enh_2511_mcp_telemetry.py`, `test_enh_2497_agent_type.py`, `test_workflow_sequence_analyzer.py` [Agent 3 finding]
- `scripts/tests/test_ll_session_refresh.py` — in `test_refresh_from_original_and_rebuild_on_request` (~74): real end-to-end `refresh --all --rebuild --json`, asserts `rebuild_counts["usage_events"] == 1`; the 9-key return dict must stay stable [Agent 2/3 finding]

New tests to write (no existing precedent for a *real* held lock):
- `scripts/tests/test_session_store_lifecycle.py` — concurrent-writer test in `TestRebuild`: model the thread shape on `test_session_store_writers.py::TestRecordAttemptAndAdmitRetry::test_allocation_serialises_across_connections` and the "no `locked` in stderr" assertion on `test_worktree_utils.py::test_concurrent_writers_share_one_db_without_locking_errors` (~401, subprocess writers); use `threading.Event`/`Barrier` to fire the `cli_events` insert mid-replay [Agent 3 finding]
- Commit-count / lock-window assertion: wrap the connection via `patch.object(writers._pkg, "connect", fake_connect)` with a counting `commit()` — models: `test_enh_2505_subagent_runs.py::_TracingConnection` (~893) and `test_session_store_writers.py::_FailUpdateConn` (~572, has `__getattr__` passthrough, the more complete form). No existing commit-counting convention (`set_progress_handler`, `total_changes`, `set_trace_callback`: 0 hits) [Agent 3 finding]
- Interrupted/resume test: closest template is `test_session_store_incremental_usage.py::test_catchup_failure_rolls_back_rows_and_checkpoint` (inject failure via `monkeypatch` of `lifecycle._backfill_usage_events`, assert marker + state, re-run to completion); `test_normalizer_version_change_replays_historical_rows` models a version-keyed marker forcing replay [Agent 3 finding]
- Mid-phase failure asserting `last_rebuild_version` not advanced and no partial derived set visible (replaces the deliberately re-scoped rollback tests) [Agent 3 finding]
- Large-store seeding: `TestRebuild._seed_raw_events` is class-local and inserts one row; `test_remote_ingestion_telemetry.py::_transcript(..., n=450)` is the nearest bulk generator. No shared many-row raw_events fixture exists [Agent 3 finding]
- Unmocked `ll-session backfill --rebuild` / worker `--rebuild` coverage is thin: `test_ll_session.py::test_backfill_reports_messages_count` mocks `cli.session.backfill`; `test_enh_3166_qwen_normalizer.py::test_flags_are_position_insensitive` (~685) is the only in-process `backfill_worker.main(... --rebuild)` test; `TestSessionStartRebuild` fakes `Popen` [Agent 3 finding]

### Documentation
- `docs/guides/HISTORY_SESSION_GUIDE.md` — `ll-session rebuild` / `backfill --rebuild` notes (lines ~198–220); describe new lock/in-progress behavior
- `docs/reference/CLI.md`, `docs/reference/API.md` — `rebuild` reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md:~190-204` — describes `rebuild` in the "Since ENH-2581" callout under `Getting Started: Backfill` ("wipes and re-derives … safe and repeatable") [Agent 2 finding]
- `docs/reference/CLI.md:~4501` — states "Repeating `--rebuild` is safe if an earlier rebuild failed" in the `ll-session refresh` safety text; also `backfill` flags (`--rebuild` row ~4484), `rebuild` flags ("Wipes and re-derives … Idempotent", ~4514-4525), command table rows (~4388, ~4397) [Agent 2 finding]
- `docs/reference/API.md:~10150-10158` — `rebuild()` block ("Updates the `last_rebuild_version` meta key to `SCHEMA_VERSION`") and the `raw_events / rebuild / compact` intro (~10116-10118); `cli_event_context` paragraph (~10185) documents the 5000 ms `busy_timeout` and the `enter failed` warning (cites `schema.py:1405` by raw line number — stale-line risk) [Agent 2 finding]
- `docs/ARCHITECTURE.md:~695` — `raw_events` table row states `last_rebuild_version` "gates the SessionStart hook's opt-in-on-migration `--rebuild` pass"; sequence diagram (~772) `backfill_incremental()` "--rebuild only when SCHEMA_VERSION > last_rebuild_version"; v53 row (~723) [Agent 2 finding]
- `docs/codex/usage.md:~131-139` — "A rebuild preserves live rows and replaces …" rollout-rows semantics [Agent 2 finding]
- `CHANGELOG.md` — new entry goes in a concrete `## [X.Y.Z]` section at release prep, never `[Unreleased]` (see memory: feedback_changelog_no_unreleased) [Agent 2 finding]
- Audience gate: these are `docs/guides|reference` files — write for the end user (no `scripts/tests/` or `scripts/little_loops/` paths; cite `little_loops.session_store.lifecycle`) (`test_docs_audience_gate.py`)

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- No config key needed. If a batch-size/lock-budget key is added anyway: `scripts/little_loops/config-schema.json` (`history` block, `additionalProperties: false`), its dataclass in `scripts/little_loops/config/features.py`, `scripts/tests/test_config_schema.py::_DATACLASS_SECTION_MAP` + `TestDataclassSectionMapCompleteness` (fail on any unmapped dataclass), and `docs/reference/CONFIGURATION.md`; `RetentionConfig` is the precedent for a config `lifecycle.py` loads raw [Agent 2 finding]
- `hooks/hooks.json`, `.claude-plugin/plugin.json`, `.claude/CLAUDE.md`, `skills/`, `commands/`, `agents/`, and all loop YAMLs: searched, no reference to `rebuild`/`backfill_worker`/`last_rebuild_version` — no registration wiring needed. `backfill_worker` is run as `python -m` (no `pyproject.toml` entry point) [Agent 1/2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Transaction shape today** (`lifecycle.py:rebuild`, ~1487-1566): one `BEGIN IMMEDIATE` (~1519) → wipe `_REBUILD_TABLES` (`usage_events` only `WHERE channel IS NOT 'live'`, via `_REBUILD_TABLE_PREDICATES`) + `search_index` rows for `_REBUILD_SEARCH_KINDS` → replay phases in order `_backfill_sessions` (lifecycle.py), then `_backfill_tool_events`, `_backfill_messages`, `_backfill_assistant_messages`, `_backfill_skill_events`, `_backfill_usage_events` (`usage_order=True`) (all `writers.py`), then `mine_corrections_from_messages`, `_compact_sessions`, `_backfill_prompt_opt` (UPDATE-only, deliberately outside the wipe list) → `last_rebuild_version` upsert (~1553) → `_set_usage_derive_checkpoint(conn)` (~1558) → single `commit()` (~1559); `except Exception` → `rollback()` + re-raise; `finally` closes.
- **No callee commits.** None of the `_backfill_*` parsers, `mine_corrections_from_messages`, or `_compact_sessions` calls `commit()`/`BEGIN`/`SAVEPOINT`; the caller owns the transaction. Any per-batch commit therefore lives in `rebuild()` (or new helpers it calls), and later phases read earlier phases' rows on the same connection (`mine_corrections_from_messages` reads `message_events`; `_backfill_usage_events` reads `loop_runs` via `_load_loop_run_windows`).
- **Corrections to the sections above:** (a) `scripts/little_loops/session_store/backend.py` is **not** a caller — `refuse_on_remote(db, "rebuild")` is the first line of `rebuild()` (and is also called by `backfill_incremental()`); rebuild refuses remote stores, so the remote/libsql path is out of scope. (b) The detached-worker path is `backfill_worker.main` → `backfill_incremental(..., also_rebuild=...)` (`lifecycle.py` ~1744) → `rebuild()`, not `backfill()`; `backfill()` (~1680) is reached from `ll-session backfill --rebuild`. `backfill_incremental` is a caller missing from Dependent Files. (c) `_backfill_tool_events` / `_backfill_usage_events` live in `writers.py`; only `_backfill_sessions` is in `lifecycle.py`.
- **Callers do not depend on cross-call atomicity:** `backfill()`/`backfill_incremental()` commit and close their own connections before calling `rebuild()` and only `counts.update(...)` its returned dict; `cli/session.py` (`refresh` ~819, `rebuild` ~1016) sums/prints the dict; `backfill_worker.main` discards it and catches only `HistoryUnsupported`. The return dict's 9 keys must stay stable.
- **Lock mechanics:** `connect()` (`schema.py` ~1725) applies `_configure_connection` (`busy_timeout = _BUSY_TIMEOUT_MS` = 5000 at `schema.py` ~130, `journal_mode = WAL`); no `wal_autocheckpoint`/`synchronous` tuning exists anywhere, so a single long write transaction also grows the WAL unchecked (the ~1 GB WAL in Motivation). The `rebuild()` connection keeps default `isolation_level` and issues explicit `BEGIN IMMEDIATE`. The losing writer in the Motivation, `cli_event_context` (`writers.py` ~531), takes the lock implicitly at its first `INSERT INTO cli_events` (~606) and waits at most the 5000 ms busy timeout; its docstring says no separate timeout is configured. Telemetry writers connect → DML → `commit()` → close.
- **Readers see the pre-rebuild snapshot today** (WAL: readers never block on the writer and see old rows until the one commit). Any design that commits between phases changes this: readers (`history_reader/*`, `cli/logs.py`, `cli/history.py`, `issue_history/*`, `compaction/result.py`, …) would otherwise observe wiped or half-replayed tables. That is the guarantee the AC "full old or full new (or detectable in-progress)" protects.
- **Rebuild-needed / resume signal already exists:** `hooks/session_start.py` `handle` (~192-214) reads `meta.last_rebuild_version` (NULL/missing → 0) and adds `--rebuild` to the detached worker argv when `< SCHEMA_VERSION` (suppressed for remote stores and under `LL_NON_INTERACTIVE`). Because `last_rebuild_version` is stamp-on-success, an interrupted rebuild is *already* re-detected and restarted from scratch at the next SessionStart; what does not exist is any marker that a rebuild *started*, or any partial-resume. `usage_refresh.py` (`RefreshResult` docstring, ~35) states "no durable rebuild-pending state is stored".
- **Other writers of the same derived data (interleaving hazards if the lock is yielded)** — inferred from the code above, not exercised: `backfill_usage_incremental` (`lifecycle.py` ~1116), `refresh_usage_source` (~1293), `_refresh_codex_usage_source` (~1138), `_derive_usage_incremental_conn` (~1067) and `refresh_raw_events` (`usage_refresh.py` ~100-247, deletes `usage_derive_*` meta keys ~221) all run `BEGIN IMMEDIATE` and write `usage_events`, `search_index` kind `usage`, and/or the `usage_derive_*` checkpoint. Today they serialise behind `rebuild()`'s lock; the `<db>.usage-refresh.lock` `fcntl.flock` in `backfill_worker._run_usage_trigger` (~46-115) serialises only usage-trigger workers, not `rebuild()`. `_set_usage_derive_checkpoint` records `MAX(raw_events.id)` at call time (~1053-1064), which equals the replayed high-water mark only while nothing appends to `raw_events` mid-rebuild — true under the single lock, not true once the lock is yielded.
- **`_compact_sessions` opens a second writer connection.** When `history.compaction.enabled` (default false), `_maybe_soft_threshold_summary` (`lifecycle.py` ~455-527) spawns a daemon thread that calls `_pkg.connect(db)` and commits `summary_nodes`; under the current single transaction that thread is blocked by rebuild's own lock. `_compact_sessions` can also shell out to a host CLI (`_call_llm_for_summary`, ~155, `subprocess.run` with timeout) while holding the transaction. Both bear on any "no transaction longer than `_BUSY_TIMEOUT_MS`" claim.
- **Replay cursor is a live SELECT on the writing connection** (`_raw_events_cursor`, ~1529-1537: `raw_events` ordered by `id`, or `source_path, COALESCE(ordinal, line_no), line_no, id` when `usage_order=True`); the `_iter_events*` helpers (`writers.py` ~3507-3568) iterate it while the same connection inserts. A commit inside that iteration must keep the cursor valid and ordering stable.
- **Names free:** `_yield_write_lock` and `rebuild_in_progress` appear nowhere in code or tests (only this issue).

### Conventions in Force
- **Derived-table rewrites are all-or-nothing:** every operation that replaces derived rows together with a version/cursor marker takes `BEGIN IMMEDIATE` first, writes the marker last, commits once, and rolls back on any exception — evidence: `rebuild()`, `backfill_usage_incremental` (~1116-1129), `refresh_usage_source`, `refresh_raw_events`, `_apply_migrations` (`schema.py` ~1574). No existing function combines batched commits with wipe-and-replay.
- **The one batching precedent is `recompress_raw_events` (`lifecycle.py` ~941-998):** short per-batch `BEGIN`/`commit()` (default `batch_size` 2000), no sleep, idempotent and resumable by a data predicate (`typeof(...)='text'`), justified because "a partially-recompressed table always reads correctly" (`writers.py` ~84-90). Contrast: `rebuild()` justifies its single transaction by "must not expose a partially replaced rollout set". Two opposite justifications are both in force; a batched rebuild must say which property it relies on.
- **`meta` markers are inline SQL, no shared helper:** `INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value`; reads are `SELECT value FROM meta WHERE key = ?`; values are strings cast with `int(...)` at the read site; missing/NULL = "never done"; version-shaped keys gate a full replay (`last_rebuild_version`, `usage_derive_version`/`usage_derive_raw_id`). Also `usage_source_cursors.status` uses a table-based cursor (`complete`/`partial`/`pending_append`/`source_changed`).
- **Shadow-table swap exists only inside a schema migration** (`verdict_events_new` → `RENAME`, `schema.py` ~1220-1245, run statement-by-statement via `_split_sql_statements` because `executescript`'s implicit COMMIT would release the write lock). `search_index` is an FTS5 virtual table that `rebuild()` wipes by `kind`, not by table replacement — a swap design must account for FTS5 shadow tables (`_schema_manifest` excludes `search_index_*`).
- **Lock contention is handled by serialising on `busy_timeout`, not by retry:** `record_attempt` docstring (`writers.py` ~1489-1500) explicitly rejects a bounded-retry loop; no retry-on-locked wrapper exists. Telemetry writers fail open (log + drop).
- **Concurrency tests assert post-state, not timing:** `threading.Thread` + `Barrier` against a pre-created DB (`test_session_store_schema.py::TestConcurrencyHardening::test_concurrent_ensure_db_on_fresh_path`; `test_session_store_writers.py::TestRecordAttemptAndAdmitRetry::test_allocation_serialises_across_connections`; `test_session_store_incremental_usage.py::test_two_concurrent_catchup_workers_commit_one_observation_set`). Locked-DB behaviour is simulated with stubs raising `sqlite3.OperationalError("database is locked")` (`test_session_store_schema.py` `_LockedConn`, ~149-164). No test holds a real lock and asserts a wait bound.
- **Failure injection by monkeypatching a phase:** `monkeypatch.setattr(lifecycle, "_backfill_usage_events", ...)` raising `RuntimeError` then asserting rows/meta unchanged (`test_session_store_incremental_usage.py::test_catchup_failure_rolls_back_rows_and_checkpoint`).

### Tests (existing coverage that pins the current guarantees — must keep passing or be deliberately re-scoped)
- `test_enh3532_codex_rollout_usage.py::test_rebuild_rolls_back_replacement_when_replay_fails` (~349) — patches `lifecycle._backfill_usage_events` to raise and asserts `usage_events` rows are identical to before; pins that the earlier-phase wipes are undone when a later phase fails (a per-phase-commit design breaks this unless replaced by an equivalent old-or-new guarantee).
- `test_session_store_lifecycle.py::TestBackfillUsageEvents::test_rebuild_failure_rolls_back_usage_delete` (~2162) — patches `_backfill_sessions` (first phase after the wipe) to raise; asserts the pre-existing `transcript` + `live` rows survive (count 2).
- `test_session_store_lifecycle.py::TestRebuild` (~1828): `test_rebuild_materializes_from_raw_events_without_original_files`, `test_rebuild_is_idempotent`, `test_rebuild_updates_last_rebuild_version`, `test_rebuild_does_not_touch_out_of_scope_tables`; plus `test_rebuild_preserves_live_usage_rows` (~2086), `test_rebuild_replaces_rollout_channel_rows` (~2146), `test_rebuild_is_idempotent_for_usage` (~2062), `test_repeated_rebuild_is_idempotent` (~3206), `test_also_rebuild_materializes_messages_and_sessions` (~952).
- `test_hook_session_start.py::TestSessionStartRebuild` (~366) — `--rebuild` present on fresh DB (NULL < `SCHEMA_VERSION`), absent after `rebuild()`; pins the `last_rebuild_version` stamp-on-success contract.
- `test_session_store_incremental_usage.py` (~39-78) uses `rebuild(db)` as the equivalence oracle for incremental usage derivation — output equivalence of `rebuild()` must be preserved.
- `rebuild(` is called ~107 times across 16 test files; `test_session_store_usage_refresh.py` and `test_ll_session.py` cover `needs_rebuild`. No existing test opens a second connection during `rebuild()`; the new concurrent-writer test has no in-file precedent for a *real* held lock, only the thread/stub shapes above. Fixtures: `_seed_raw_events(tmp_path, db)` in `TestRebuild`, `tests/fixtures/claude/`, `tests/fixtures/codex/`; `test_session_store_lifecycle.py` overrides `tmp_path` with a module-scoped parent (ENH-2529, macOS file-churn).

## Program Design

### Types

- `rebuild_in_progress`: `meta` key (value: `SCHEMA_VERSION` string) marking an incomplete rebuild; cleared on success

### Signatures

- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]` — unchanged public contract, new internal locking
- `_yield_write_lock(conn: sqlite3.Connection) -> None` — commit the current batch and release the lock so waiting writers can proceed

### Call Path

`main` (`little_loops.cli.backfill_worker`) -> `backfill` -> `rebuild` -> `_backfill_sessions` / `_backfill_tool_events` / `_backfill_usage_events`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Call Path correction:** the detached-worker chain is `main` (`little_loops.cli.backfill_worker`) -> `backfill_incremental` (`lifecycle.py`) -> `rebuild` (`lifecycle.py`) -> `_backfill_sessions` (`lifecycle.py`) / `_backfill_tool_events` / `_backfill_usage_events` (`writers.py`); the `backfill` -> `rebuild` edge belongs to `ll-session backfill --rebuild` (`main_session`), and `ll-session rebuild` / `refresh --rebuild` call `rebuild` directly.
- **Signature facts:** `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]` returns 9 counter keys that callers merge/print; `_set_usage_derive_checkpoint(conn: sqlite3.Connection) -> None` (`lifecycle.py` ~1053) writes `usage_derive_version` (= `_USAGE_DERIVE_VERSION`, "enh3651-v1") and `usage_derive_raw_id` (= `MAX(raw_events.id)` at call time). `meta` values are strings; an in-progress marker keyed like `last_rebuild_version` follows the same inline-upsert convention.
- **Decision Rules gap:** the issue introduces new decision logic (how an in-progress rebuild is detected and what a reader/next-start does with it; how batch size / lock-hold budget relates to `_BUSY_TIMEOUT_MS`) but pins no exact inputs or values. Not pinned by research: the batch boundary (per phase vs per N `raw_events` rows), the marker's value shape, and how concurrent live writes to `_REBUILD_TABLES` rows are reconciled with the replay — these are implementer decisions to record in the issue before coding.

## Implementation Steps

> ⚠ Superseded (2026-09-30): steps 1-3 are settled by the re-scope banner at the top (shadow-build + rename-only swap, `H`-bounded cursors, batched `search_index`); implement in that shape, after ENH-3699 (and its ENH-3678 prerequisite). ENH-3679 is an independent symptom mitigation.

1. Decide the atomicity strategy (shadow tables + short swap vs. per-phase commits with an in-progress `meta` marker) and record it in the issue.
2. Restructure `rebuild()` so no single transaction spans the whole wipe + replay; commit/yield between batches.
3. Defer `last_rebuild_version` and `_set_usage_derive_checkpoint` until every phase has completed; make an interrupted rebuild detectable and resumable.
4. Add a test where a second connection writes (e.g. a `cli_events` insert) during `rebuild()` and succeeds within `_BUSY_TIMEOUT_MS`.
5. Run `python -m pytest scripts/tests/test_session_store_lifecycle.py scripts/tests/test_backfill_worker_usage_trigger.py` and update `docs/guides/HISTORY_SESSION_GUIDE.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Outcomes to hold whatever route is chosen (constraints, not a recipe): (1) no `rebuild()` write transaction outlasts `_BUSY_TIMEOUT_MS`, checked with a test that runs a second-connection `cli_events` insert during `rebuild()` (thread + barrier shape, post-state assertion — no wall-clock bound); (2) readers see full-old or full-new derived data or a detectable in-progress state — decide explicitly what happens to the two existing rollback tests (`test_rebuild_rolls_back_replacement_when_replay_fails`, `test_rebuild_failure_rolls_back_usage_delete`) since a per-phase-commit design cannot satisfy them as written; (3) `last_rebuild_version` and the usage-derive checkpoint are stamped only after every phase, and the checkpoint's `raw_events` high-water mark must be the id actually replayed, not `MAX(id)` at the end, if `raw_events` can grow while the lock is yielded; (4) `usage_events` `channel = 'live'` rows and `search_index` rows outside `_REBUILD_SEARCH_KINDS` survive, and `rebuild()` output stays equivalent to the incremental derive oracle in `test_session_store_incremental_usage.py`.
- Decide, and record in the issue, how the other `BEGIN IMMEDIATE` derivers of `usage_events` (`backfill_usage_incremental`, `refresh_usage_source`, `refresh_raw_events`) are excluded or reconciled during a yielded rebuild, and how the `_compact_sessions` path (host-CLI subprocess and `_maybe_soft_threshold_summary` writer thread) fits the lock-window budget.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/session_store/lifecycle.py` `rebuild()` — keep `refuse_on_remote(db, "rebuild")` as the first line; keep the 9-key return dict; open any new connection via `_pkg.connect()`, never `sqlite3.connect` (`test_history_store_chokepoint_gate.py`)
- Update `scripts/little_loops/session_store/lifecycle.py` `_compact_sessions` — keep the direct `_compact_sessions(conn, config)` signature callable (`TestCompactSession`) and add no `subprocess` spawn (`test_enh3184_spawn_site_guard.py`)
- Decide interleaving with `hooks/usage_stop.py` `handle` → `backfill_worker` `_run_usage_trigger` / `_refresh_usage_source` and the `BEGIN IMMEDIATE` derivers (`backfill_usage_incremental`, `refresh_usage_source`, `refresh_raw_events`); record the decision (exclude via lock/marker vs reconcile) in the issue
- Write `rebuild_in_progress` inline (meta upsert); do not seed it or add a migration (avoids `SCHEMA_VERSION` bump, `test_meta_seeds_present`, `test_schema_version_matches_migrations_length`, `schema_manifest.json`); do not name it `usage_derive_*`
- Re-scope `test_session_store_lifecycle.py::TestBackfillUsageEvents::test_rebuild_failure_rolls_back_usage_delete` and `test_enh3532_codex_rollout_usage.py::test_rebuild_rolls_back_replacement_when_replay_fails` to the chosen old-or-new/in-progress guarantee
- Update `scripts/little_loops/cli/ctx_stats.py` `_compute_cache_rate_from_usage` (and any other `usage_source_freshness` reader) if the design makes `usage_derive_*` state ambiguous mid-rebuild
- Update `scripts/little_loops/session_store/backend.py` `refuse_on_remote` reason text for `"rebuild"` only if it stops being accurate
- Add tests to `scripts/tests/test_session_store_lifecycle.py` — concurrent-writer (real second connection), commit-count/lock-window wrapper, interrupted-then-resume, `last_rebuild_version` stamped only after all phases
- Update `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/CLI.md` (~4501, ~4514-4525), `docs/reference/API.md` (~10150-10158, ~10185), `docs/ARCHITECTURE.md` (~695, ~772), `docs/codex/usage.md` (~131-139) — lock/in-progress behavior and the "repeating `--rebuild` is safe" claim
- Update `scripts/little_loops/cli/session.py` `main_session` `--rebuild` help/epilog and the refresh hint (~840) if user-visible behavior changes

## Impact

- **Priority**: P3 - Degrades telemetry on large stores during rebuild; no data loss and a workaround exists (avoid running during active work)
- **Effort**: Medium - Restructuring the single-transaction replay while preserving atomic visibility touches `rebuild()` and its phase helpers
- **Risk**: Medium - The single transaction is the current partial-set safety guarantee; a batching bug could expose a partial derived-table set
- **Breaking Change**: No

## Constraints

- The current single transaction is deliberate: the `except` branch comment says "A failed replay must not expose a partially replaced rollout set." Any batching design must preserve that atomic-visibility guarantee or replace it with an explicit in-progress marker.
- `last_rebuild_version` and `_set_usage_derive_checkpoint` must only be set once the whole rebuild has completed.
- Related but separate: the `database is locked` warning severity and the telemetry-insert timeout are not in scope here.

## Acceptance Criteria

> ⚠ Superseded (2026-09-30): the first criterion below is replaced by "a concurrent writer at the production busy timeout always succeeds" (see the re-scope banner); the batch budget is 2,000 rows or 250 ms with a ~50 ms yield.

- During `--rebuild` on a large DB, no single write transaction holds the lock longer than `_BUSY_TIMEOUT_MS`.
- A concurrent `ll-*` command during a rebuild logs no `database is locked` warning and records its `cli_events` row.
- An interrupted or failed rebuild leaves readers with either the full old or the full new derived data (or a detectable in-progress state), never a silent partial set.
- Existing rebuild tests pass; add one covering concurrent writer during rebuild.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Deferred** | Created: 2026-09-29 | Priority: P4


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-29_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 54/100 → LOW

### Concerns
- The atomicity strategy is still undecided (shadow-table swap vs per-phase commits with a `rebuild_in_progress` marker vs lock yielding). Implementation Step 1 is itself "decide and record", and the repo convention (all-or-nothing derived-table rewrites) is deliberately being departed from without a chosen justification.
- The two existing rollback tests (`test_rebuild_rolls_back_replacement_when_replay_fails`, `test_rebuild_failure_rolls_back_usage_delete`) cannot pass unchanged under a per-phase-commit design, so they must be re-scoped.

### Outcome Risk Factors
- Unresolved design decision: the atomic-visibility strategy, the batch boundary (per phase vs per N `raw_events` rows), and the `rebuild_in_progress` marker's value shape and reader behavior are all open. Needs `/ll:decide-issue` before coding.
- Deep per-site complexity: restructuring the single `BEGIN IMMEDIATE` transaction changes the partial-set safety contract, and the usage-derive checkpoint must record the replayed `raw_events` high-water mark, not `MAX(id)` at the end.
- Wide change surface: interleaving writers (`backfill_usage_incremental`, `refresh_usage_source`, `refresh_raw_events`, `usage_stop` worker), `_compact_sessions` (host-CLI subprocess and writer thread) and the `usage_source_freshness` readers must be reconciled with a yielded lock.

## Session Log
- `/ll:confidence-check` - 2026-09-29T17:31:21 - `6954bfd1-9884-42d0-92b6-2f9281481f9e.jsonl`
- `/ll:verify-issues` - 2026-09-29T17:30:08 - `b91509d0-b878-4a4b-8a91-f007479a3527.jsonl`
- `/ll:wire-issue` - 2026-09-29T17:28:22 - `895f2500-d57c-473f-8b79-7862769ce029.jsonl`
- `/ll:refine-issue` - 2026-09-29T17:21:15 - `529a7815-065c-4e6d-81e5-103be1433280.jsonl`
- `/ll:format-issue` - 2026-09-29T17:15:20 - `65eead6e-6648-47e3-bb45-1774131ddd9c.jsonl`
- `/ll:capture-issue` - 2026-09-29T15:29:47 - `85fc47a8-e1b6-45fa-ba9d-e5941d3c8ece.jsonl`
