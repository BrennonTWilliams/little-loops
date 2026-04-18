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

`ParallelRunner.run()` gains an optional `on_worker_complete: Callable[[int, dict, str], None] | None` callback invoked as each worker's future resolves. The callback receives `(item_index, worker_captures, verdict)` so the caller can persist it immediately.

### 2. Incremental checkpoint writes from `PersistentExecutor`

When `FSMExecutor` is a `PersistentExecutor` and is executing a parallel state, it registers `on_worker_complete` with `ParallelRunner`. Each time a worker completes, `PersistentExecutor` appends the worker's result to a parallel-state-specific section of the checkpoint file:

```json
{
  "current_state": "fan_out",
  "captured": { ... },
  "parallel_progress": {
    "fan_out": {
      "completed": [
        {"item_index": 0, "captures": {...}, "verdict": "yes"},
        {"item_index": 2, "captures": {...}, "verdict": "yes"}
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
- If `items_hash` differs: log a warning and re-run from scratch (safer than running against stale progress)
- If absent: normal fresh execution

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
- `items_hash` mismatch on resume produces a warning and falls back to full re-run
- `parallel_progress` entry is cleared from the checkpoint after the parallel state completes
- Tests cover: interrupt at 50% completion + clean resume; `items_hash` mismatch path; multiple parallel states in one loop resume independently
- Existing non-parallel `PersistentExecutor` behavior is unchanged (no `parallel_progress` entries written when no parallel state is active)

## Impact

- **Priority**: P3 — Production quality-of-life for long orchestrator runs; not a correctness blocker for v1 parallel ship. Ship once FEAT-1076 lands and real usage patterns confirm mid-run interrupts are common.
- **Effort**: Medium — 3-file change with subtle resume semantics; needs integration tests against real `PersistentExecutor`
- **Risk**: Medium — Checkpoint schema additions are backwards-compatible (old checkpoints without `parallel_progress` fall through to full re-run), but the resume path has more edge cases than typical state resume
- **Breaking Change**: No — additive; absence of `parallel_progress` means status quo behavior

## Labels

`fsm`, `parallel`, `persistence`, `checkpoint`, `resume`

---

## Session Log
- `parallel-fsm-review` - 2026-04-18T00:00:00Z - spawned during parallel feature review discussion

---

**Open** | Created: 2026-04-18 | Priority: P3
