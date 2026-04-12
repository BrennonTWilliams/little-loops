---
discovered_date: "2026-04-12"
discovered_by: capture-issue
---

# FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Summary

Add a first-class `parallel:` state type to the FSM schema and executor that fans out sub-loop execution over a list of items concurrently, with selectable worktree or thread isolation modes. Results from all workers are merged back into the parent loop's captured context, and aggregate outcome routes via `on_yes` (all succeeded), `on_partial` (mixed), or `on_no` (all failed).

## Current Behavior

FSM loops execute states sequentially. Orchestrator loops that process multiple items (e.g., `recursive-refine`, `sprint-refine-and-implement`, `harness-multi-item`) must dequeue one item at a time, run its sub-loop to completion, then move to the next. There is no mechanism to express concurrent fan-out within a loop YAML — parallelism requires external orchestration tools (`ll-parallel`, `ll-sprint`) which cannot be composed inside a loop definition.

## Expected Behavior

A new `parallel:` state type in `StateConfig` enables concurrent fan-out:

```yaml
refine_batch:
  parallel:
    items: "${captured.queue.output}"   # newline-delimited list
    loop: refine-to-ready-issue
    max_workers: 4
    isolation: worktree                 # "worktree" | "thread"
    fail_mode: collect                  # "collect" | "fail_fast"
    context_passthrough: true
  route:
    on_yes: collect_children            # all workers reached "done"
    on_partial: collect_children        # mixed results
    on_no: done                         # all failed
```

Given a list of items, the executor spawns N sub-loop instances simultaneously (up to `max_workers`), each processing one item. Workers run with either:
- `isolation: worktree` — each worker gets its own git worktree (reuses ll-parallel's `WorkerPool`/`GitLock`/`MergeCoordinator`); safe for loops that write files
- `isolation: thread` — workers share the filesystem in parallel threads; safe for read-only or non-overlapping-write loops

Results from all workers merge into `captured.<state_name>.results[i]`, and the aggregate verdict routes accordingly.

## Motivation

Queue-based orchestrator loops are significantly slower than necessary. `recursive-refine` with 10 issues runs 10 sequential `refine-to-ready-issue` sub-loops. With 4 workers those 10 issues could complete in ~3 serial lengths instead of 10. The same bottleneck exists across all 6 queue-based orchestrator loops identified in the codebase. Parallelism for the FSM system requires this as a first-class primitive — CLI-level solutions (`ll-loop-parallel`) break composability because loops cannot orchestrate other parallel loops via YAML.

## Proposed Solution

**schema.py** — Add `ParallelStateConfig` dataclass:

```python
@dataclass
class ParallelStateConfig:
    items: str                    # interpolated expression resolving to newline-delimited list
    loop: str                     # sub-loop name to run per item
    max_workers: int = 4
    isolation: str = "worktree"   # "worktree" | "thread"
    fail_mode: str = "collect"    # "collect" | "fail_fast"
    context_passthrough: bool = False
```

Add `parallel: ParallelStateConfig | None = None` to `StateConfig`. Validate mutual exclusion with `action:` and `loop:` in schema validation.

**executor.py** — Add `_execute_parallel_state()` alongside `_execute_sub_loop()`. Dispatch when `state.parallel is not None`. Fan out N sub-loop executions using `ParallelRunner`, collect `ParallelResult(succeeded, failed, all_captures)`, merge captures, derive verdict.

**fsm/parallel_runner.py** (new) — `ParallelRunner` class (~150 lines):
- Worktree mode: delegates to `WorkerPool` from `little_loops.parallel.worker_pool`, reusing `GitLock` and `MergeCoordinator`
- Thread mode: `ThreadPoolExecutor`, each thread runs `FSMExecutor` for one item
- Returns `ParallelResult` with per-item outcomes

**Scope locking** — Parent `parallel:` state acquires the scope lock once before spawning workers. Workers skip individual scope lock acquisition (isolation is handled by worktree separation or thread-level non-overlap).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — Add `ParallelStateConfig`, extend `StateConfig`
- `scripts/little_loops/fsm/executor.py` — Add `_execute_parallel_state()`, update dispatch in `_execute_state()`
- `scripts/little_loops/fsm/validation.py` — Add validation for `parallel:` mutual exclusion and field requirements

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — No changes expected; uses `FSMExecutor` transparently
- `scripts/little_loops/parallel/worker_pool.py` — Extract/expose `WorkerPool` for reuse by `parallel_runner.py`
- `scripts/little_loops/parallel/git_lock.py` — Reused directly

### Similar Patterns
- `_execute_sub_loop()` in `executor.py` — Direct analogue; `_execute_parallel_state()` fans out N instances of the same logic
- `WorkerPool` in `parallel/worker_pool.py` — Proven worktree fan-out pattern to reuse

### Tests
- `scripts/tests/fsm/test_executor.py` — Add parallel state dispatch tests
- `scripts/tests/fsm/test_schema.py` — Add `ParallelStateConfig` validation tests
- `scripts/tests/fsm/test_parallel_runner.py` (new) — Unit tests for `ParallelRunner` with mock workers

### Documentation
- `docs/ARCHITECTURE.md` — Document the `parallel:` state type
- `docs/reference/API.md` — Add `ParallelStateConfig` to schema reference

### Configuration
- N/A

## Implementation Steps

1. Add `ParallelStateConfig` to `schema.py` and extend `StateConfig` with `parallel:` field; update validation for mutual exclusion
2. Create `fsm/parallel_runner.py` with `ParallelRunner` — worktree mode reuses `WorkerPool`, thread mode uses `ThreadPoolExecutor`
3. Add `_execute_parallel_state()` to `FSMExecutor`; wire dispatch in `_execute_state()` 
4. Extract `WorkerPool` from `parallel/` for shared use (or import directly — assess coupling)
5. Update scope locking: parent state acquires lock, workers skip acquisition
6. Write tests for schema validation, executor dispatch, and parallel runner
7. Update ARCHITECTURE.md and API reference docs

## Use Case

A user runs `ll-loop recursive-refine --context input="ENH-001,ENH-002,ENH-003,ENH-004"`. Instead of refining issues one at a time (4 sequential sub-loop runs), `recursive-refine` uses a `parallel:` state to fan out all 4 to `refine-to-ready-issue` concurrently with `max_workers: 4`. After the batch completes, a `collect_children` state gathers any newly decomposed child issues and fans them out as the next generation. Total wall-clock time drops proportionally.

## Acceptance Criteria

- `parallel:` key in a state YAML triggers concurrent sub-loop fan-out
- `isolation: worktree` runs each item in an isolated git worktree; changes are merged back
- `isolation: thread` runs items in parallel threads with shared filesystem (no worktree overhead)
- `max_workers` limits concurrency; excess items queue and execute as workers finish
- `fail_mode: collect` continues all workers even if some fail; `fail_mode: fail_fast` cancels remaining on first failure
- `on_yes` routes when all workers reached terminal `done`; `on_partial` when mixed; `on_no` when all failed
- Worker captures merge into `captured.<state_name>.results[i]` and are accessible in subsequent states
- `context_passthrough: true` passes parent context to each worker's sub-loop
- Scope lock is held by the parent `parallel:` state; workers do not acquire individual locks
- Existing loops using `loop:` (sequential sub-loop delegation) are unaffected

## API/Interface

```python
@dataclass
class ParallelStateConfig:
    items: str                    # ${captured.queue.output} or literal newline-delimited list
    loop: str                     # name of sub-loop YAML to run per item
    max_workers: int = 4
    isolation: Literal["worktree", "thread"] = "worktree"
    fail_mode: Literal["collect", "fail_fast"] = "collect"
    context_passthrough: bool = False

@dataclass
class ParallelResult:
    succeeded: list[str]          # item values that reached terminal "done"
    failed: list[str]             # item values that did not
    all_captures: list[dict]      # per-worker captured dicts (indexed by item order)
    verdict: str                  # "yes" | "partial" | "no"
```

## Impact

- **Priority**: P2 — Enables parallelism for 6+ orchestrator loops; significant throughput improvement for the most expensive loop operations; blocks ENH-1073
- **Effort**: Large — New schema primitive, executor dispatch path, and parallel runner module; reuses ll-parallel infrastructure but requires careful integration
- **Risk**: Medium — New execution path in the FSM executor; worktree mode reuses proven ll-parallel machinery but scope lock integration needs care to avoid deadlocks
- **Breaking Change**: No — additive; existing loops unchanged

## Related Key Documentation

| Document | Relevance |
|---|---|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | FSM loop execution model, ll-parallel worktree architecture |
| [docs/reference/API.md](../../docs/reference/API.md) | FSMLoop and StateConfig schema reference |

`fsm`, `parallel`, `executor`, `schema`, `captured`

---

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c305cac4-c25e-482f-86f7-9adf26df1b0e.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
