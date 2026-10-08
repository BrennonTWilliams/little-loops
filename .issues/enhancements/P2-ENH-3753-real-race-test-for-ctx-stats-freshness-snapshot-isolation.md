---
id: ENH-3753
title: Real race test for ctx_stats freshness snapshot isolation (ENH-3746 AC #5 deeper)
type: ENH
priority: P2
status: open
captured_at: "2026-10-06T00:00:00Z"
parent: ENH-3746
relates_to:
- ENH-3746
- BUG-3736
labels:
- testing
- race
- snapshot-isolation
- ctx-stats
---

# ENH-3753: Real race test for ctx_stats freshness snapshot isolation (ENH-3746 AC #5 deeper)

## Summary

ENH-3746 shipped a connection-sharing pattern between the admission, selection, and freshness reads in `_compute_cache_rate_from_usage` (commit e864ea225; follow-up f48aab03a added docstring-correction tests at 4683d980a). The shipped tests verify that the freshness field reflects the latest committed cursor state but **do not exercise a concurrent writer committing between the selection and freshness reads**.

QA review (2026-10-08) explicitly tested this by removing the `conn=conn` keyword from the `usage_source_freshness` call at `cli/ctx_stats.py:544` — both `TestEnH3746FreshnessSnapshotIsolation` tests still pass. The tests are pass-through, not regression guards. The connection-sharing change has no real guard today.

## Current Behavior

`cli/ctx_stats.py::_compute_cache_rate_from_usage` shares a single `sqlite3.Connection` (the readonly one returned by `connect_readonly(db_path)`) across:

1. `_has_verified_retained_ingestion(conn, ...)` — replay-admission probe
2. `_has_ingested_raw(conn, ...)` — raw-path admission probe
3. `select_usage_coverage(conn, ...)` — figure selection
4. `usage_source_freshness(..., conn=conn)` — freshness read

SQLite's WAL mode gives each statement a fresh snapshot in autocommit; the readonly connection has `PRAGMA query_only=ON`. Sharing a connection does not achieve snapshot isolation in WAL mode without an explicit transaction — a concurrent `refresh_usage_source` commit between reads 3 and 4 would still be visible to read 4.

To achieve snapshot isolation:
- `BEGIN IMMEDIATE` holds a write lock for the duration of the transaction — blocks writers but the readonly connection cannot enter BEGIN IMMEDIATE (PRAGMA query_only=ON blocks writes including transaction-control writes).
- A writable connection (without `PRAGMA query_only=ON`) can `BEGIN IMMEDIATE` and read with snapshot isolation.

## Expected Behavior

A regression test that catches a removal of the `conn=` keyword by failing when:
- A writer thread (or process) commits a cursor bump at a precise moment between `select_usage_coverage` and `usage_source_freshness` reads
- The pre-fix code path opens a separate connection for the freshness read and sees the post-bump cursor
- The post-fix code path shares the connection; depending on transaction semantics, behavior differs:
  - Without `BEGIN IMMEDIATE`: still sees the post-bump cursor (the WAL-mode bug)
  - With `BEGIN IMMEDIATE`: sees the pre-bump cursor (true snapshot isolation)

The test design must inject the writer commit at the precise moment. Two viable strategies:

### Strategy A: Separate-process test (preferred for race correctness)

Spawn a child Python process via `multiprocessing` that runs the function under test, holding a barrier-released cursor-bump write that fires between the selection and freshness reads. Avoids pytest's threading-join deadlocks (Builder hit one during the prototype) by using real OS process boundaries.

### Strategy B: Writable connection with `BEGIN IMMEDIATE` (preferred for clarity)

Open a writable connection and wrap the reads in `BEGIN IMMEDIATE` ... `COMMIT`. The connection won't issue writes to history.db (no writers in the path), but `BEGIN IMMEDIATE` holds the write lock. The test asserts:
- A second connection attempting `BEGIN IMMEDIATE` blocks until the function's COMMIT
- `as_of_offset` reflects the pre-bump cursor (read inside the function's transaction)
- `rate` is unchanged by the bump (figure is independent of cursor)

Strategy B is cleaner but requires changing the production code. Builder's prototype of Strategy B confirmed `BEGIN IMMEDIATE` works on a non-`query_only` writable connection; the change is small.

## Implementation Steps

1. Choose Strategy A or Strategy B.
2. If Strategy B: change `_compute_cache_rate_from_usage` to open `connect_existing_writable(db_path)` instead of `connect_readonly`, wrap reads in `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`, ensure the function still respects the existing `HistoryError` mapping. Run the existing 17 tests to confirm no regressions.
3. Add `test_concurrent_writer_sees_pre_bump_cursor` that spawns a writer thread/process committing the cursor bump after the function enters the transaction but before the freshness read; asserts `as_of_offset` equals the pre-bump value.
4. Add `test_writer_blocks_on_begin_immediate` (Strategy B only) that asserts a concurrent writer's `BEGIN IMMEDIATE` blocks until the function's COMMIT completes.
5. Confirm: removing `BEGIN IMMEDIATE` (or removing `conn=conn`) makes the new tests fail.

## Acceptance Criteria

- [ ] New regression test fails when `conn=conn` is removed from the `usage_source_freshness` call (Strategy A) or when `BEGIN IMMEDIATE`/`COMMIT` are removed (Strategy B).
- [ ] New regression test passes with the current shipped fix.
- [ ] Test runtime stays under 5 seconds (Strategy A subprocess overhead excluded from the wall-clock budget).
- [ ] Strategy B's production change passes all 17 existing tests in `test_enh3656_stored_cache_rate.py`.
- [ ] Connection lifecycle is correct: a writable connection raised on error closes; the `HistoryError`/`unreadable_store` mapping still applies.

## Out of Scope

- Migration to a non-WAL journal mode (would change production behavior).
- Replacing the connection-sharing pattern with a row-level lock (different design).
- Fixing the underlying SQLite WAL-mode race semantics (engine-level).
