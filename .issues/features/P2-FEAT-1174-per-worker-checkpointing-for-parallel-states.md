---
discovered_date: "2026-04-18"
discovered_by: parallel-fsm-review
depends_on: [FEAT-1075, FEAT-1076]
---

# FEAT-1174: Per-Worker Checkpointing and Resume for Parallel States

## Summary

Extend `PersistentExecutor` and `ParallelRunner` to serialize per-worker completion state incrementally so that a `parallel:` state interrupted mid-fan-out resumes only the workers that did not complete, instead of re-running every worker from scratch.

## Current Behavior (as of FEAT-1076)

`FSMExecutor._execute_parallel_state()` writes `self.captured[state_name] = {"results": [...]}` **only after** `ParallelRunner.run()` returns. `PersistentExecutor._save_state()` serializes `captured` + `current_state` after every state transition — but there is no transition emitted mid-fan-out. If the process is killed while 2 of 4 workers have completed and 2 are mid-execution, the checkpoint on disk has no record of the parallel state being in progress. On resume, the executor re-enters `_execute_parallel_state()` from scratch and re-runs all 4 workers.

For short parallel runs this is fine. For long orchestrator runs (e.g., `recursive-refine` fanning out over 20+ issues at `max_workers: 4`) a mid-run interrupt forces hours of rework, and in thread mode may double-apply non-idempotent side effects.

## Expected Behavior

A `parallel:` state interrupted mid-fan-out can be resumed such that:
- Workers that completed successfully are not re-run
- Workers that were in progress at interrupt time are re-run (their side effects were partial anyway)
- Pending workers (not yet started) are run as normal
- `ParallelResult.all_captures` on resume is the union of previously-completed + newly-completed worker captures, in item order

## Use Case

**Who**: An automation engineer running a long orchestrator loop (e.g., `recursive-refine` over a backlog) that they may need to interrupt and resume.

**Context**: A 2-hour parallel fan-out is 45 minutes in when the user hits Ctrl-C (per ENH-1165) to add a fix. They want to resume from where it left off, not from scratch.

**Goal**: `ll-loop resume <run-id>` re-enters the parallel state, detects which workers already completed, and runs only the remaining ones.

**Outcome**: Wall-clock time on resume is `(remaining_items / max_workers) × item_duration`, not the full original duration.

## Proposed Solution

Three coordinated changes:

### 1. Per-worker completion events from `ParallelRunner`

`ParallelRunner.run()` gains an optional `on_worker_complete: Callable[[ParallelItemResult], None] | None` callback invoked as each worker's future resolves. The callback receives the completed `ParallelItemResult` (see FEAT-1075) so the caller can serialize the full per-worker record — `item`, `item_index`, `verdict`, `terminated_by`, `captures`, `error` — directly into the checkpoint.

### 2. Incremental checkpoint writes from `PersistentExecutor`

When `FSMExecutor` is a `PersistentExecutor` and is executing a parallel state, it registers `on_worker_complete` with `ParallelRunner`. Each time a worker completes, `PersistentExecutor` appends the worker's result to a parallel-state-specific section of the checkpoint file:

```json
{
  "current_state": "fan_out",
  "captured": { ... },
  "parallel_progress": {
    "fan_out": {
      "completed": [
        {"item": "FEAT-1042", "item_index": 0, "verdict": "yes", "terminated_by": "terminal", "captures": {...}, "error": null},
        {"item": "FEAT-1044", "item_index": 2, "verdict": "yes", "terminated_by": "terminal", "captures": {...}, "error": null}
      ],
      "total_items": 4,
      "items_hash": "<sha256 of items list>"
    }
  }
}
```

`items_hash` is the hash of the resolved `items` list at fan-out time; resume validates that the current `items` still hash to the same value (detects list drift — e.g., if the input changed between runs).

### 3. Resume-aware fan-out in `_execute_parallel_state()`

On resume, before calling `ParallelRunner.run()`, `FSMExecutor._execute_parallel_state()` checks `parallel_progress[state_name]`:
- If present and `items_hash` matches: build a filtered items list (only items not in `completed`), pass it to `ParallelRunner` with a starting `item_index` offset so captures land at the right positions
- If `items_hash` differs: log a **WARNING-level** message and re-run the full parallel state from scratch (see "items_hash mismatch is a surprise" note below)
- If absent: normal fresh execution

### items_hash mismatch is a surprise — make it loud

A silent "we quietly re-ran everything because your inputs changed between suspend and resume" is a footgun. The log line MUST:

1. Be emitted at `logging.WARNING` level (not DEBUG, not INFO).
2. Name both hash values — the hash at suspend time (from the checkpoint) and the hash at resume time (computed from current items). Example:
   ```
   WARNING: parallel state 'fan_out' items_hash mismatch on resume.
     suspend-time hash: a3f2c1b5...
     resume-time hash:  7e4d9a02...
     action: full re-run of parallel state 'fan_out' — N prior completions discarded
   ```
3. Name the specific action taken (`full re-run of parallel state '<state>' — N prior completions discarded`) so the operator can decide whether to abort instead.
4. Be echoed in the end-of-run summary printed by `ll-loop resume` — not only during state execution — so an operator who resumes in the background and checks later still sees it.

### Worker-to-parent checkpoint separation (thread-safety contract)

The parent loop's checkpoint file and each worker's internal state MUST NOT race:

- Workers do NOT write to the parent loop's checkpoint file. `on_worker_complete` is invoked in the worker thread but only enqueues the result; a single main-thread serializer dequeues and writes to the parent checkpoint under a Python-level lock. Use `queue.Queue` + a daemon writer thread pattern OR `threading.Lock` around the write — whichever is simpler to test.
- Each worker's own checkpoint (if the worker's sub-loop is itself a `PersistentExecutor`) MUST be written to a worker-scoped path, not the parent's. Proposed path: `<run-dir>/workers/<state>-<item_index>.json`. The parent's checkpoint at `<run-dir>/<run-id>.json` is written exclusively by the main thread.
- A test `test_parent_checkpoint_not_written_from_worker_thread` instruments `_save_state()` with `threading.get_ident()` and asserts only the main thread writes the parent file. This aligns with FEAT-1075's thread-safety contract and FEAT-1077's `TestParallelRunnerSingletonSafety` suite.

Failure mode to test: if two workers complete at nearly the same instant, the single-writer serializer must append both results to `parallel_progress[state].completed` without data loss and without one overwriting the other's entry. Covered by `test_concurrent_worker_completions_all_persist`.

After `ParallelRunner.run()` returns, merge the resumed results with the previously-completed results (by `item_index`) to produce the final `all_captures` in item order, then clear `parallel_progress[state_name]` and write the final `{"results": [...]}` capture as today.

## Files to Modify

- `scripts/little_loops/fsm/parallel_runner.py` — add `on_worker_complete` callback param, add `starting_item_index` offset param
- `scripts/little_loops/fsm/persistence.py` — add `parallel_progress` section to checkpoint schema, write-on-worker-complete hook
- `scripts/little_loops/fsm/executor.py` — `_execute_parallel_state()` reads and filters against `parallel_progress` on resume, clears on completion

## Dependencies

- **Hard blockers**: FEAT-1075, FEAT-1076 (this FEAT extends them; they must be stable first)
- **Soft**: ENH-1165 (cancellation) — interacts with resume semantics but does not block this issue

## Acceptance Criteria

- A parallel state interrupted mid-fan-out (simulated by SIGTERM partway through) resumes without re-running completed workers
- `items_hash` mismatch on resume produces a **WARNING-level** log line naming both hashes and the action taken, AND the same line appears in the end-of-run summary printed by `ll-loop resume`
- `parallel_progress` entry is cleared from the checkpoint after the parallel state completes
- Tests cover: interrupt at 50% completion + clean resume; `items_hash` mismatch path (including WARN-level assertion and resume-summary assertion); multiple parallel states in one loop resume independently
- `test_parent_checkpoint_not_written_from_worker_thread` asserts the parent's checkpoint file is written exclusively from the main thread during fan-out (single-writer serializer + main-thread dispatch)
- `test_concurrent_worker_completions_all_persist` asserts two near-simultaneous worker completions both land in `parallel_progress[state].completed` with no data loss
- Existing non-parallel `PersistentExecutor` behavior is unchanged (no `parallel_progress` entries written when no parallel state is active)

## Impact

- **Priority**: P2 — v1 parallel must not regress sequential-loop checkpoint guarantees. `PersistentExecutor._save_state` fires after every `state_enter` today (`persistence.py:436`); losing up to N minutes of completed fan-out work on SIGKILL is a regression of that contract. Bundle with or immediately after FEAT-1076.
- **Effort**: Medium — 3-file change with subtle resume semantics; needs integration tests against real `PersistentExecutor`
- **Risk**: Medium — Checkpoint schema additions are backwards-compatible (old checkpoints without `parallel_progress` fall through to full re-run), but the resume path has more edge cases than typical state resume
- **Breaking Change**: No — additive; absence of `parallel_progress` means status quo behavior

## Labels

`fsm`, `parallel`, `persistence`, `checkpoint`, `resume`

---

## Session Log
- `parallel-fsm-review` - 2026-04-18T00:00:00Z - spawned during parallel feature review discussion

---

**Open** | Created: 2026-04-18 | Priority: P2 (promoted 2026-04-20)
