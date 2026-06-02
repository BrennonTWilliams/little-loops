---
captured_at: '2026-05-02T19:56:20Z'
completed_at: '2026-05-02T20:44:33Z'
discovered_date: '2026-05-02'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
---

# ENH-1332: `--queue` waiters execute in non-deterministic order

## Summary

When two or more `ll-loop run --queue` processes are waiting for the same scope, they are all released simultaneously when the running loop finishes. They race to call `acquire()`, so execution order is determined by OS scheduling, not by the time each process was enqueued. The `.queue/*.json` entries record queue membership for dashboard display but are never consulted to enforce FIFO ordering.

## Motivation

Users who start queued loops expect them to run in the order they were submitted — especially in scripted pipelines or multi-tab workflows where the submission sequence has semantic meaning (e.g., "run A, then B, then C" in that order). The current race-based dispatch violates that expectation silently.

## Current Behavior

1. Loop A holds the scope lock.
2. Loops B and C start with `--queue`; both enter `wait_for_scope`, polling every second.
3. Loop A finishes; `release()` removes its lock file.
4. On the next poll tick, B and C both see `conflict is None` and both call `acquire()`.
5. `acquire()` uses `fcntl.flock(LOCK_EX)` on `.acquire.lock` — one wins, one retries.
6. Which one wins is determined by OS lock-grant order, not enqueue time.

The comment at `cli/loop/run.py:246` acknowledges this: *"when N waiters are released simultaneously, only one wins acquire(); losers loop back and wait again rather than exiting."*

## Expected Behavior

Waiters acquire the scope lock in the order they were enqueued (FIFO). The process that called `wait_for_scope` first should be the first to run after the active loop finishes.

## Success Metrics

- FIFO ordering: Loop B (enqueued first) always runs before Loop C (enqueued second) after Loop A finishes — 100% deterministic, verified by new test in `test_cli_loop_queue.py`
- No regression: All existing `test_cli_loop_queue.py` tests continue to pass
- Overhead: Per-poll overhead increase bounded to one `.queue/` directory scan + sort per waiter per second

## Proposed Solution

Use the existing `.queue/<id>.json` files (already written at `run.py:231–242`) as the ordering source:

1. Each queue entry already contains `enqueuedAt` (ISO 8601 timestamp).
2. Before calling `acquire()`, each waiter reads all `.queue/*.json` files, sorts by `enqueuedAt`, and checks whether its own `entry_id` is the earliest entry.
3. If it is the earliest, it attempts `acquire()`.
4. If it is not, it sleeps and retries — yielding to the earlier waiter.

This keeps the lock mechanism unchanged and adds only a lightweight file-read + sort step to the retry loop. No new files or infrastructure needed.

> **Selected:** Primary pre-acquire FIFO check — pre-acquire ordering read has direct codebase templates and zero infrastructure cost (reuse score 3/3); scores 11/12 vs 3/12 for the alternative.

### Alternative

A simpler approximation: after winning `acquire()`, sleep briefly (e.g., 50 ms) and re-check whether any queue entry with an earlier `enqueuedAt` exists. If so, release and re-queue. This is less rigorous but avoids the coordination read on every poll tick.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-02.

**Selected**: Primary pre-acquire FIFO check

**Reasoning**: The primary option directly reuses the `glob("*.json") + json.load + except` pattern from `concurrency.py:find_conflict` and the ISO 8601 sort convention from `persistence.py:list_run_history`, making it a zero-new-infrastructure addition. The alternative has no "acquire-then-release" template anywhere in the codebase, conflicts with `cmd_run`'s linear post-acquire control flow, and introduces an orphan-window race with no existing guard.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Primary pre-acquire FIFO check | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Alternative post-acquire re-queue | 1/3 | 1/3 | 1/3 | 0/3 | 3/12 |

**Key evidence**:
- Primary: `concurrency.py:find_conflict` provides the exact glob+json+exception template; `entry_id` and `queue_dir` are already in scope at the insertion point in `cmd_run`; `_is_earliest_waiter` is a pure function testable with just `tmp_path` writes and no mocking.
- Alternative: No "acquire then conditionally release" pattern exists anywhere; `wait_for_scope` returns `True` immediately after release creating a tight busy-loop; existing `TestQueueRetryOnRace` asserts `acquire.call_count == 3` which conflicts with a release-and-reacquire sequence.

## Implementation Steps

1. Add `_is_earliest_waiter(entry_id: str, queue_dir: Path) -> bool` to `scripts/little_loops/cli/loop/_helpers.py`. Follow the `glob("*.json") + json.load(f) + except (json.JSONDecodeError, KeyError, FileNotFoundError)` pattern from `concurrency.py:LockManager.find_conflict`. Sort by `data["enqueuedAt"]` (ISO strings sort lexicographically); check `earliest["id"] == entry_id`. Return `True` if this waiter is first (or if the queue directory is empty/unreadable).
2. In `cmd_run` (`scripts/little_loops/cli/loop/run.py` lines ~249–263), after `wait_for_scope` returns `True` and *before* calling `lock_manager.acquire()`, call `_is_earliest_waiter(entry_id, queue_dir)`. If `False`, `time.sleep(1)` and `continue` without calling `acquire()`.
3. Add a test class (e.g., `TestQueueFifoOrdering`) to `scripts/tests/test_cli_loop_queue.py`. Reuse `_make_args()`, `_make_loop(tmp_path)`, `_conflict()`. Write two `.queue/<uuid>.json` files directly with distinct `enqueuedAt` values via `(loops_dir / ".queue" / f"{uid}.json").write_text(json.dumps(...))`, then assert `_is_earliest_waiter` returns `True` only for the earlier-timestamped entry.
4. No changes to `layout.py` — it contains no queue display code.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis:_

5. (Optional) Update `docs/reference/CLI.md` — "Queue entries (`.loops/.queue/`)" section: add note that `enqueuedAt` is used to enforce FIFO ordering, not just for display; update field description from observer-only to active ordering input
6. (Optional) Update `docs/guides/LOOPS_GUIDE.md` — add FIFO ordering guarantee to the `--queue` flag description and the "Running multiple loops concurrently" section

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — add earliest-waiter check in `cmd_run` retry loop (after `wait_for_scope` returns `True`)
- `scripts/little_loops/cli/loop/_helpers.py` — add `_is_earliest_waiter()` helper
- `scripts/tests/test_cli_loop_queue.py` — add FIFO ordering test

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:224,257` — calls `lock_manager.acquire()` (initial attempt + retry after `wait_for_scope`)
- `scripts/little_loops/cli/loop/run.py:253` — calls `lock_manager.wait_for_scope()`; the new earliest-waiter check gates entry after this returns `True`
- `scripts/tests/test_cli_loop_queue.py` — mocks `LockManager.wait_for_scope` and `LockManager.acquire` in `TestQueueRetryOnRace`; new FIFO test belongs here
- `scripts/tests/test_concurrency.py` — unit tests for `LockManager.acquire()` and `LockManager.wait_for_scope()` directly; no changes needed, but confirms those methods are stable targets

### Similar Patterns
- `scripts/little_loops/cli/loop/layout.py` — **no queue display code exists here**; the file contains only FSM diagram rendering. No changes needed.
- `scripts/little_loops/fsm/concurrency.py:LockManager.find_conflict` — canonical `glob("*.lock") + json.load(f) + except (json.JSONDecodeError, KeyError, FileNotFoundError)` pattern to follow in `_is_earliest_waiter`
- `scripts/little_loops/fsm/persistence.py:list_run_history` — canonical sort-by-ISO-string pattern: `states.sort(key=lambda s: s.started_at)` — ISO 8601 strings are lexicographically sortable without parsing

### Tests
- `scripts/tests/test_cli_loop_queue.py` — add test with two waiters and distinct `enqueuedAt` values asserting the earlier one acquires first

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_queue.py::TestQueueRetryOnRace::test_retries_acquire_after_losing_race` — passes only if `_is_earliest_waiter` returns `True` when `queue_dir` is missing or empty (the test creates no `.queue/*.json` files and uses a mocked `LockManager`); verify the implementation handles this case or the `acquire.side_effect = [False, False, True]` sequence will be disrupted [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — "Queue entries (`.loops/.queue/`)" section describes `.queue/*.json` files as observer-only; after this change they are actively read to enforce FIFO ordering — update `enqueuedAt` field description and add a note on ordering [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — "Running multiple loops concurrently" section and `--queue` flag description omit the FIFO ordering guarantee; add a note that waiters acquire in submission order [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **JSON key is `"id"`, not `"entry_id"`** — `_is_earliest_waiter` must compare `data["id"] == entry_id` (the variable in `run.py` is `entry_id`, but the JSON field is `"id"`)
- **`enqueuedAt` is written at `run.py:234`** as `datetime.now(UTC).isoformat()`. ISO 8601 strings sort lexicographically in chronological order — no `datetime.fromisoformat()` parsing needed; `sorted(..., key=lambda d: d["enqueuedAt"])` works directly
- **`_helpers.py` exists and has no queue helpers** — safe to add `_is_earliest_waiter(entry_id: str, queue_dir: Path) -> bool` following the `_process_alive(pid: int) -> bool` style in `concurrency.py` (module-level, underscore prefix, explicit return type, one-sentence docstring)
- **`wait_for_scope` polls every 1 second, fixed** (`time.sleep(1)` in `concurrency.py:236`) — all N waiters wake within the same ~1 s window after the lock drops, confirming the race window
- **Test scaffolding to reuse**: `TestQueueRetryOnRace` in `test_cli_loop_queue.py` has `_make_args()`, `_make_loop(tmp_path)`, and `_conflict()` factories. Write `.queue/<uuid>.json` files directly via `(loops_dir / ".queue" / f"{uuid}.json").write_text(json.dumps({...}))` to simulate multiple waiters with known `enqueuedAt` values
- **`acquire()` result is unreachable for the losing-waiter check** — the new check must happen *before* calling `acquire()` (not after), otherwise the losing waiter holds no lock but still consumed an `fcntl.flock` cycle

## Scope Boundaries

- **In scope**: FIFO ordering for waiters competing for the same scope lock; using existing `.queue/*.json` `enqueuedAt` timestamps as the ordering source; lightweight file-read + sort per poll tick
- **Out of scope**: Priority-based (non-FIFO) scheduling; cross-scope ordering; distributed lock fairness; changes to the `fcntl.flock` lock mechanism itself; queue persistence across process restarts

## Acceptance Criteria

- When loops B (enqueued first) and C (enqueued second) are both waiting behind loop A, B always runs before C after A finishes.
- When only one loop is queued, behavior is unchanged.
- Existing `test_cli_loop_queue.py` tests continue to pass.

## Impact

- **Priority**: P4 — cosmetic correctness; non-deterministic ordering rarely causes failures in practice
- **Effort**: Small — adds a file-read/sort step to an existing retry loop
- **Risk**: Low — no change to the lock mechanism itself
- **Breaking Change**: No

## Labels

`loop`, `queue`, `concurrency`, `reliability`

## Resolution

Implemented `_is_earliest_waiter(entry_id, queue_dir)` in `cli/loop/_helpers.py` following the `concurrency.py:find_conflict` glob+json+except pattern. Added a pre-acquire FIFO check in `cmd_run`'s retry loop (`run.py:257-259`) that reads `.queue/*.json`, sorts by `enqueuedAt`, and skips `acquire()` if this waiter is not the earliest, sleeping 1s before retrying. Added `TestQueueFifoOrdering` (4 tests) to `test_cli_loop_queue.py`; all 10 queue tests pass.

## Status

**Completed** | Created: 2026-05-02 | Completed: 2026-05-02 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-05-02T20:41:29 - `b84dc8a5-211b-4016-9274-f01ca9f1ed9f.jsonl`
- `/ll:decide-issue` - 2026-05-02T20:39:16 - `89261ec9-d524-456a-ad4c-b18059d10b93.jsonl`
- `/ll:confidence-check` - 2026-05-02T21:00:00 - `9e78efbb-4296-4a05-9998-5e07a96a3607.jsonl`
- `/ll:wire-issue` - 2026-05-02T20:33:04 - `2f97d5b7-6e6d-41b5-b904-07ee8b3b54df.jsonl`
- `/ll:refine-issue` - 2026-05-02T20:27:58 - `3751cb4e-6a67-4b00-ab9c-72103e3b916f.jsonl`
- `/ll:format-issue` - 2026-05-02T19:59:45 - `d469eb33-2332-43d1-ae05-da1005adf370.jsonl`
- `/ll:capture-issue` - 2026-05-02T19:56:20Z - `5c7505b5-ede1-476a-a6b7-a18e3c4c8571.jsonl`
- `/ll:manage-issue` - 2026-05-02T20:44:33Z - `current.jsonl`
