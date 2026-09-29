---
id: ENH-3666
type: ENH
title: Batch backfill --rebuild commits to shorten history.db write lock
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T15:29:40Z'
---

# ENH-3666: Batch backfill --rebuild commits to shorten history.db write lock

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

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — `ll-session rebuild` and `ll-session backfill --rebuild`
- `scripts/little_loops/session_store/lifecycle.py` — `backfill()` and the refresh path call `rebuild(db, config=config, ...)` when `also_rebuild` is set
- `scripts/little_loops/cli/backfill_worker.py` — detached `--rebuild` worker spawned from `scripts/little_loops/hooks/session_start.py` (`handle`)
- `scripts/little_loops/session_store/usage_refresh.py` — documents `rebuild(db)` as the follow-up when `needs_rebuild` is set

### Similar Patterns
- `scripts/little_loops/session_store/schema.py` — migration runner wraps its sequence in one `BEGIN IMMEDIATE` (same lock-window trade-off)
- `backfill_snapshots()` in `lifecycle.py` — single-commit backfill without a wipe phase

### Tests
- `scripts/tests/test_session_store_lifecycle.py` — existing `rebuild()` coverage; add concurrent-writer test here
- `scripts/tests/test_enh_omp_normalizer.py`, `scripts/tests/test_session_store_incremental_usage.py`, `scripts/tests/test_backfill_worker_usage_trigger.py` — must keep passing

### Documentation
- `docs/guides/HISTORY_SESSION_GUIDE.md` — `ll-session rebuild` / `backfill --rebuild` notes (lines ~198–220); describe new lock/in-progress behavior
- `docs/reference/CLI.md`, `docs/reference/API.md` — `rebuild` reference

### Configuration
- N/A

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

1. Decide the atomicity strategy (shadow tables + short swap vs. per-phase commits with an in-progress `meta` marker) and record it in the issue.
2. Restructure `rebuild()` so no single transaction spans the whole wipe + replay; commit/yield between batches.
3. Defer `last_rebuild_version` and `_set_usage_derive_checkpoint` until every phase has completed; make an interrupted rebuild detectable and resumable.
4. Add a test where a second connection writes (e.g. a `cli_events` insert) during `rebuild()` and succeeds within `_BUSY_TIMEOUT_MS`.
5. Run `python -m pytest scripts/tests/test_session_store_lifecycle.py scripts/tests/test_backfill_worker_usage_trigger.py` and update `docs/guides/HISTORY_SESSION_GUIDE.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Outcomes to hold whatever route is chosen (constraints, not a recipe): (1) no `rebuild()` write transaction outlasts `_BUSY_TIMEOUT_MS`, checked with a test that runs a second-connection `cli_events` insert during `rebuild()` (thread + barrier shape, post-state assertion — no wall-clock bound); (2) readers see full-old or full-new derived data or a detectable in-progress state — decide explicitly what happens to the two existing rollback tests (`test_rebuild_rolls_back_replacement_when_replay_fails`, `test_rebuild_failure_rolls_back_usage_delete`) since a per-phase-commit design cannot satisfy them as written; (3) `last_rebuild_version` and the usage-derive checkpoint are stamped only after every phase, and the checkpoint's `raw_events` high-water mark must be the id actually replayed, not `MAX(id)` at the end, if `raw_events` can grow while the lock is yielded; (4) `usage_events` `channel = 'live'` rows and `search_index` rows outside `_REBUILD_SEARCH_KINDS` survive, and `rebuild()` output stays equivalent to the incremental derive oracle in `test_session_store_incremental_usage.py`.
- Decide, and record in the issue, how the other `BEGIN IMMEDIATE` derivers of `usage_events` (`backfill_usage_incremental`, `refresh_usage_source`, `refresh_raw_events`) are excluded or reconciled during a yielded rebuild, and how the `_compact_sessions` path (host-CLI subprocess and `_maybe_soft_threshold_summary` writer thread) fits the lock-window budget.

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

- During `--rebuild` on a large DB, no single write transaction holds the lock longer than `_BUSY_TIMEOUT_MS`.
- A concurrent `ll-*` command during a rebuild logs no `database is locked` warning and records its `cli_events` row.
- An interrupted or failed rebuild leaves readers with either the full old or the full new derived data (or a detectable in-progress state), never a silent partial set.
- Existing rebuild tests pass; add one covering concurrent writer during rebuild.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-29T17:21:15 - `529a7815-065c-4e6d-81e5-103be1433280.jsonl`
- `/ll:format-issue` - 2026-09-29T17:15:20 - `65eead6e-6648-47e3-bb45-1774131ddd9c.jsonl`
- `/ll:capture-issue` - 2026-09-29T15:29:47 - `85fc47a8-e1b6-45fa-ba9d-e5941d3c8ece.jsonl`
