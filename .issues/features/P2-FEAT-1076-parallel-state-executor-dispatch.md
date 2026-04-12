---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
---

# FEAT-1076: Parallel State Executor Dispatch

## Summary

Add `_execute_parallel_state()` to `executor.py` and wire the dispatch at `_execute_state()`. Decide and document the scope lock architecture for parallel states.

## Current Behavior

`executor.py` has no `_execute_parallel_state()` method and `_execute_state()` has no dispatch for `parallel:` state types. A state YAML containing a `parallel:` key silently falls through to the `if state.next:` block, with no concurrent fan-out triggered.

## Expected Behavior

When a state contains `parallel: ...`, `_execute_state()` dispatches to `_execute_parallel_state()`, which fans out sub-loop execution concurrently via `ParallelRunner`, stores per-worker captures in `self.captured[self.current_state]`, and returns a verdict (`done`/`partial`/`failed`) for routing via `_route_parallel()`.

## Use Case

**Who**: An automation engineer building an FSM loop that needs to process multiple items concurrently (e.g., running the same sub-loop against a list of open issues in parallel).

**Context**: The engineer has a list of items in captured context and wants to fan out a named sub-loop across all items concurrently rather than sequentially, with configurable `max_workers`, `fail_mode`, and `context_passthrough`.

**Goal**: Define a `parallel:` state in YAML that triggers concurrent fan-out execution and aggregates worker results under `${captured.<state_name>.results}`.

**Outcome**: All items are processed concurrently; the FSM routes on `on_yes` / `on_partial` / `on_no` based on collective verdict.

## Motivation

This feature:
- **Completes FEAT-1072**: This dispatch wiring is the final integration point connecting the schema (FEAT-1074) and `ParallelRunner` (FEAT-1075) into the live executor.
- **Enables concurrent fan-out**: Reduces wall-clock time from O(n) sequential to O(n/workers) concurrent for multi-item sub-loop patterns.
- **Establishes scope lock architecture**: Documents that `isolation: worktree` handles real conflict risk, keeping `FSMExecutor` clean of lock concerns.

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Proposed Solution

### executor.py changes

**Add `_execute_parallel_state()`** alongside `_execute_sub_loop()` at line 318:

```python
def _execute_parallel_state(self, state: StateConfig) -> str:
    """Fan out sub-loop execution over a list of items concurrently."""
    assert state.parallel is not None
    items = self._interpolate(state.parallel.items).splitlines()
    runner = ParallelRunner()
    result = runner.run(
        items=items,
        loop_name=state.parallel.loop,
        config=state.parallel,
        parent_context=self.captured if state.parallel.context_passthrough else None,
    )
    self.captured[self.current_state] = {"results": result.all_captures}
    return result.verdict
```

**Insert dispatch** at `executor.py:396–402` immediately after the `if state.loop is not None:` block (line 403) and before the `if state.next:` block. Follow the same `try/except (FileNotFoundError, ValueError)` guard pattern:

```python
if state.parallel is not None:
    try:
        verdict = self._execute_parallel_state(state)
        return self._route_parallel(state, verdict)
    except (FileNotFoundError, ValueError) as e:
        ...
```

**Scope lock design decision** — pick one and document in implementation:
- Option A (recommended): Leave scope lock management at the CLI level (`run.py:148`). Worktree isolation handles the real conflict risk. Document that `isolation: worktree` makes per-worker locking unnecessary.
- Option B: Thread `lock_manager` into `FSMExecutor` as an optional constructor arg

**Captured context**: parallel state stores results as `self.captured[self.current_state] = {"results": [per_worker_captured_dict, ...]}` — accessible downstream as `${captured.<state_name>.results}`.

**Route method** — add `_route_parallel(state, verdict)` that maps `verdict` → `on_yes` / `on_partial` / `on_no` route keys.

## Implementation Steps

1. Add `_execute_parallel_state(state)` to `FSMExecutor` in `executor.py` alongside `_execute_sub_loop()`
2. Add `_route_parallel(state, verdict)` to map verdict → `on_yes` / `on_partial` / `on_no` route keys
3. Insert `if state.parallel is not None:` dispatch block in `_execute_state()` after the `if state.loop is not None:` block, following the same `try/except (FileNotFoundError, ValueError)` guard pattern
4. Adopt Option A for scope lock (leave at CLI level) and add a comment in `_execute_parallel_state()` documenting why executor-level locking is unnecessary
5. Verify existing `loop:` sequential dispatch is unaffected (run existing FSM tests)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — Add `_execute_parallel_state()`, `_route_parallel()`, insert dispatch at `_execute_state()` after `if state.loop is not None:` block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — Uses `FSMExecutor` transparently; no changes expected but verify scope lock architecture holds
- `scripts/little_loops/fsm/schema.py` — Must expose `StateConfig.parallel` (FEAT-1074 prerequisite)

### Similar Patterns
- `_execute_sub_loop()` in `executor.py` — Parallel dispatch follows same structure; use as implementation template
- `if state.loop is not None:` block — Dispatch pattern to mirror for `if state.parallel is not None:`

### Tests
- New test file per FEAT-1077: `scripts/tests/fsm/test_parallel_executor.py`
- Existing: `scripts/tests/fsm/test_executor.py` — Verify no regressions in `loop:` dispatch

### Documentation
- N/A — internal implementation; no public-facing docs changes

### Configuration
- N/A

## Dependencies

- FEAT-1074 (schema) and FEAT-1075 (ParallelRunner) must be complete

## Acceptance Criteria

- `parallel:` key in a state YAML triggers concurrent sub-loop fan-out via `_execute_parallel_state()`
- `on_yes` routes when all workers reached terminal `done`; `on_partial` when mixed; `on_no` when all failed
- Worker captures accessible as `${captured.<state_name>.results[i]}`
- `context_passthrough: true` passes parent captured dict to each worker
- `max_workers` limits concurrency; excess items queue and execute as workers finish
- `fail_mode: collect` continues all workers even if some fail
- `fail_mode: fail_fast` cancels remaining on first failure
- Existing loops using `loop:` (sequential sub-loop delegation) are unaffected
- Scope lock behavior is documented in code comments

## Implementation Notes

- **`_execute_state()` dispatch insertion point**: `executor.py:396–402`. Insert `if state.parallel is not None:` immediately after the `if state.loop is not None:` block (line 403) and before the `if state.next:` block.
- **Scope locking architecture**: `LockManager` is instantiated in `cli/loop/run.py:145` and scope lock acquisition happens at `run.py:148` — before `FSMExecutor` is ever constructed. `FSMExecutor` has zero awareness of `LockManager`. The statement "parent `parallel:` state acquires the scope lock" is impossible at the executor level as currently architected. Option A (leave at CLI) is simplest and sufficient.
- `cli/loop/run.py` — No changes expected; uses `FSMExecutor` transparently.

## Impact

- **Priority**: P2 — Core dispatch wiring for FEAT-1072; blocked by FEAT-1074 and FEAT-1075 completing first
- **Effort**: Small — Adds 2 new methods and 1 dispatch block; mirrors the existing `_execute_sub_loop()` pattern exactly
- **Risk**: Low — New code path only; existing `loop:` dispatch block is untouched; scope lock stays at CLI level
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `executor`

---

## Session Log
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
