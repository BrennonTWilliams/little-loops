---
discovered_date: "2026-04-12"
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 61
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
- `scripts/little_loops/fsm/schema.py` — Add `ParallelStateConfig`, extend `StateConfig` (follow `to_dict`/`from_dict` pattern at lines ~288–338)
- `scripts/little_loops/fsm/executor.py` — Add `_execute_parallel_state()`, insert dispatch at `_execute_state():396` (right before `state.next` check, matching the `if state.loop is not None:` guard pattern)
- `scripts/little_loops/fsm/validation.py` — Add `parallel:` to `KNOWN_TOP_LEVEL_KEYS` (lines 77–99) and add mutual exclusion checks: `parallel` + `action`, `parallel` + `loop`, `parallel` + `next`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — Add `parallel:` as a valid state-level key with its sub-fields (`items`, `loop`, `max_workers`, `isolation`, `fail_mode`, `context_passthrough`)
- `scripts/little_loops/fsm/__init__.py` — add `ParallelStateConfig` and `ParallelResult` to import block (lines 113–120) and `__all__` list (lines 136–184), and update module docstring [Wiring pass]
- `scripts/little_loops/cli/loop/layout.py` — `_get_state_badge()` at line 118 has no branch for `state.parallel is not None`; parallel states display no badge — add `_PARALLEL_BADGE` constant and dispatch branch [Wiring pass]
- `scripts/little_loops/cli/loop/info.py` — `_print_state_overview_table` type column (line 548) and verbose state output (lines 755–834) have no `state.parallel` branch; parallel states display `—` in type column — add display handling [Wiring pass]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — No changes expected; uses `FSMExecutor` transparently. **Scope lock is acquired here (`run.py:145–167`), NOT inside `FSMExecutor`** — see scope locking note below
- `scripts/little_loops/parallel/worker_pool.py` — **Cannot be directly reused**: `WorkerPool._process_issue()` is tightly coupled to `IssueInfo` and the 9-step `ll-parallel` workflow. `ParallelRunner` must implement its own fan-out using `ThreadPoolExecutor` directly
- `scripts/little_loops/parallel/git_lock.py` — Reused directly for worktree-mode git operations
- `scripts/little_loops/parallel/merge_coordinator.py` — Reused for serialized merge-back of worktree changes in worktree mode
- `scripts/little_loops/worktree_utils.py` — Reuse for worktree setup/teardown in worktree mode (instead of going through `WorkerPool`)
- `scripts/little_loops/fsm/concurrency.py` — Contains `LockManager` and scope lock primitives; relevant to understanding the scope locking architecture

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py` — wraps `FSMExecutor` as `PersistentExecutor`; if `FSMExecutor.__init__` gains an optional `lock_manager=None` param (scope lock option B), propagation is needed here [Agent 2 finding]

### Similar Patterns
- `_execute_sub_loop()` in `executor.py:318–381` — Direct analogue; `_execute_parallel_state()` fans out N instances of the same logic. Note that `self.captured[self.current_state] = child_executor.captured` (line 364) is how single-child captures merge back; parallel will store `{"results": [...]}` under the same key
- `link_checker.py:286–318` — Canonical `ThreadPoolExecutor` + `as_completed` fan-out/collect pattern for thread mode: `{executor.submit(fn, item): item for item in items}` then drain with `as_completed()`
- `WorkerPool` in `parallel/worker_pool.py` — Pattern reference only (NOT reusable directly); shows `ThreadPoolExecutor(max_workers=N, thread_name_prefix=...)` constructor and `Future`-based result tracking

### Tests
- `scripts/tests/test_fsm_executor.py` — Add parallel state dispatch tests (class `TestSubLoopExecution` at line 3472 shows the exact pattern to follow)
- `scripts/tests/test_fsm_schema.py` — Add `ParallelStateConfig` validation tests
- `scripts/tests/test_fsm_validation.py` — Add `parallel:` mutual exclusion validation tests
- `scripts/tests/fsm/test_parallel_runner.py` (new) — Unit tests for `ParallelRunner` with mock workers

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema_fuzz.py:134` — `malformed_state_config` strategy does not include `parallel` key; add it to fuzz coverage of `StateConfig.from_dict()` [new test]
- `scripts/tests/test_ll_loop_display.py:2255` — `TestStateBadges` class tests sub-loop badge; add equivalent test for `parallel:` state badge [new test]
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` (new) — fixture YAML with a minimal `parallel:` state for `TestLoadAndValidate`-style round-trip tests [new fixture]
- `scripts/tests/fsm/` (directory) — does not exist; must be created before placing `test_parallel_runner.py` [infrastructure]
- `scripts/tests/test_fsm_schema.py:636` — `TestFSMValidation`; new mutual-exclusion rules may alter error counts in tests that assert specific counts — review for regressions [may break]
- `scripts/tests/test_fsm_fragments.py` + `scripts/tests/test_builtin_loops.py` — call `validate_fsm` across all 33 built-in loops; new validation rules must not reject existing loops [may break]

### Documentation
- `docs/ARCHITECTURE.md` — Document the `parallel:` state type
- `docs/reference/API.md` — Add `ParallelStateConfig` to schema reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:1653` — "Composable Sub-Loops" section and comparison table (lines 1695–1700) describe only `loop:` and inline states; add `parallel:` row and examples
- `skills/create-loop/reference.md:686` — `loop:` field section documents sub-loop invocation; `parallel:` field documentation belongs alongside it
- `skills/create-loop/loop-types.md:978` — Sub-loop composition section describes `loop:` as the primary child mechanism; add `parallel:` as peer concurrent fan-out mechanism
- `scripts/little_loops/loops/README.md:148` — "Composing Loops" section references `loop:` field only; add `parallel:` fan-out pattern
- `CONTRIBUTING.md:231` — `fsm/` directory tree listing; add `parallel_runner.py` entry when the new module is created

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Scope locking architecture (important correction):** `LockManager` is instantiated in `cli/loop/run.py:145` and scope lock acquisition happens at `run.py:148` — before `FSMExecutor` is ever constructed. `FSMExecutor` has zero awareness of `LockManager`. The statement "parent `parallel:` state acquires the scope lock" in the Proposed Solution is therefore impossible at the executor level as currently architected. Options:
1. Leave scope lock management entirely at the CLI level (simplest — worktree isolation handles the real conflict risk)
2. Thread `lock_manager` into `FSMExecutor` as an optional constructor arg for parallel state use
3. Document that `isolation: worktree` makes scope lock per-worker a non-issue (each worker has its own worktree)

**`_execute_state()` dispatch insertion point:** `executor.py:396–402`. Insert `if state.parallel is not None:` immediately after the `if state.loop is not None:` block (line 403) and before the `if state.next:` block. Follow the same `try/except (FileNotFoundError, ValueError)` guard pattern.

**`StateConfig` serialization:** When adding `parallel: ParallelStateConfig | None = None` to `StateConfig`, follow the `loop` field pattern in `to_dict()` (skip if None) and `from_dict()` (use `data.get("parallel")`). `ParallelStateConfig` needs its own `to_dict()` / `from_dict()` following `LoopConfigOverrides` at `schema.py:419`.

**Captured context for parallel results:** The parallel state should store results as `self.captured[self.current_state] = {"results": [per_worker_captured_dict, ...]}`. This makes results accessible downstream as `${captured.<state_name>.results}`. Each entry should match the `ParallelResult.all_captures` structure.

**`KNOWN_TOP_LEVEL_KEYS`:** Located at `validation.py:77–99` as a frozenset. Must add `"parallel"` here, or unknown-key warnings will fire on every loop YAML containing a `parallel:` state.

## Implementation Steps

1. **`schema.py`**: Add `ParallelStateConfig` dataclass with `to_dict`/`from_dict` (follow `LoopConfigOverrides` at `schema.py:419`); add `parallel: ParallelStateConfig | None = None` to `StateConfig` following the `loop` field pattern in `to_dict()` (lines ~316) and `from_dict()` (lines ~288–338)
2. **`validation.py`**: Add `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` (`validation.py:77–99`); add mutual exclusion checks for `parallel` + `action`, `parallel` + `loop`, `parallel` + `next`; add range validation for `max_workers >= 1` and `isolation` / `fail_mode` enum checks
3. **`fsm/parallel_runner.py`** (new): `ParallelRunner` class with two fan-out modes:
   - Thread mode: `ThreadPoolExecutor(max_workers=N)` + `as_completed()` pattern from `link_checker.py:286–318`; each thread constructs and runs an `FSMExecutor` with the child loop
   - Worktree mode: per-item worktree via `worktree_utils.py`; git operations via `GitLock` directly (not `WorkerPool` — see coupling note)
   - Returns `ParallelResult(succeeded, failed, all_captures, verdict)`
4. **`executor.py`**: Add `_execute_parallel_state()` alongside `_execute_sub_loop()` (line 318); insert dispatch at `executor.py:396–402` right after the `if state.loop` block, using same `try/except (FileNotFoundError, ValueError)` guard; merge captures as `self.captured[self.current_state] = {"results": [...]}` 
5. **Scope lock design decision**: Decide between (a) leave at CLI level (worktree isolation suffices), or (b) thread `lock_manager` into `FSMExecutor` — document decision in implementation; `FSMExecutor.__init__` signature may need `lock_manager=None` optional param
6. **`fsm-loop-schema.json`**: Add `parallel:` object schema with sub-fields matching `ParallelStateConfig` fields and their types/constraints
7. **Tests**: Follow `TestSubLoopExecution` at `test_fsm_executor.py:3472` for executor dispatch tests; add `TestParallelStateConfig` to `test_fsm_schema.py`; add `test_fsm_validation.py` cases for mutual exclusion; create `scripts/tests/fsm/test_parallel_runner.py` with mock `FSMExecutor` workers
8. **Docs**: Update `docs/ARCHITECTURE.md` and `docs/reference/API.md` with `ParallelStateConfig` and `ParallelResult`; update `docs/generalized-fsm-loop.md` with `parallel:` state type reference

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/little_loops/fsm/__init__.py` — add `ParallelStateConfig` and `ParallelResult` to `from little_loops.fsm.schema import (...)` block (lines 113–120) and `__all__` list (lines 136–184); update module docstring at lines 1–68
10. Update `scripts/little_loops/cli/loop/layout.py:_get_state_badge` — add `_PARALLEL_BADGE` constant and `if state.parallel is not None: return _PARALLEL_BADGE` branch before action_type checks (line 118)
11. Update `scripts/little_loops/cli/loop/info.py` — add `state.parallel` display branches to `_print_state_overview_table` type column (line 548) and verbose state output (lines 755–834)
12. Create `scripts/tests/fsm/` directory; place `test_parallel_runner.py` there
13. Create `scripts/tests/fixtures/fsm/parallel-loop.yaml` fixture with a minimal `parallel:` state for `TestLoadAndValidate`-style round-trip tests
14. Update `scripts/tests/test_fsm_schema_fuzz.py:134` — add `parallel` key to `malformed_state_config` hypothesis strategy
15. Update `scripts/tests/test_ll_loop_display.py:TestStateBadges` — add test for `parallel:` state badge (model after `test_get_state_badge_sub_loop` at line 2255)
16. Update `docs/guides/LOOPS_GUIDE.md` — add `parallel:` to "Composable Sub-Loops" section (line 1653) and comparison table (lines 1695–1700)
17. Update `skills/create-loop/reference.md:686` and `skills/create-loop/loop-types.md:978` — document `parallel:` field alongside `loop:`
18. Update `scripts/little_loops/loops/README.md:148` — add `parallel:` to "Composing Loops" section
19. Update `CONTRIBUTING.md:231` — add `parallel_runner.py` to `fsm/` directory tree listing

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

## Labels

`fsm`, `parallel`, `executor`, `schema`, `captured`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-12
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- FEAT-1074: Parallel State Schema and Validation
- FEAT-1075: FSM ParallelRunner Module
- FEAT-1076: Parallel State Executor Dispatch
- FEAT-1077: Parallel State Tests
- FEAT-1078: Parallel State Wiring, Display, and Docs

---

## Session Log
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d9dab5f-0500-45e4-a7b3-4a342aa59e89.jsonl`
- `/ll:wire-issue` - 2026-04-12T20:59:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cc4df60-baf3-40fc-bf23-c4a224b1f898.jsonl`
- `/ll:refine-issue` - 2026-04-12T20:49:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fcb243f-3ce0-4787-a0c2-82ca645cd388.jsonl`
- `/ll:format-issue` - 2026-04-12T20:45:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/25126069-d8fb-4fac-ae10-8b33af465661.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c305cac4-c25e-482f-86f7-9adf26df1b0e.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Decomposed** | Created: 2026-04-12 | Priority: P2
