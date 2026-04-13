---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
confidence_score: 75
outcome_confidence: 86
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Verify `persistence.py:418` — confirm `captured` dict mutation flows into `PersistentExecutor._save_state()` automatically; no changes to `persistence.py` expected, but run `test_fsm_persistence.py` after implementation
7. Verify interceptor behavior — check where the `_interceptors` loop runs inside `_execute_state()` relative to the `if state.loop:` early-return; if interceptors are skipped for sub-loop states (expected), parallel dispatch is consistent — document this behavior in `_execute_parallel_state()` comments
8. Add comment in `_execute_parallel_state()` noting that `SimulationActionRunner` is bypassed when `ParallelRunner` is invoked (see `cli/loop/testing.py:185`) — simulation mode does not support parallel states
9. Confirm `fsm/__init__.py` — lazy import of `ParallelRunner` inside method body means no `__init__.py` update is required; verify after FEAT-1075 is merged

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — Add `_execute_parallel_state()`, `_route_parallel()`, insert dispatch at `_execute_state()` after `if state.loop is not None:` block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — Uses `FSMExecutor` transparently; no changes expected but verify scope lock architecture holds
- `scripts/little_loops/fsm/schema.py` — Must expose `StateConfig.parallel` (FEAT-1074 prerequisite)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py:343` — `PersistentExecutor` wraps `FSMExecutor` directly; `self.captured[self.current_state] = {"results": ...}` mutation from `_execute_parallel_state()` flows into `_save_state()` at line 418 automatically — verify no changes to `persistence.py` are needed
- `scripts/little_loops/extension.py:188–254` — `wire_extensions()` attaches interceptors to `FSMExecutor._interceptors`; the interceptor loop in `_execute_state()` does not fire for early-return dispatch paths (same behavior as `state.loop` — interceptors are skipped for both sub-loop and parallel dispatch); document this in `_execute_parallel_state()` comments
- `scripts/little_loops/cli/loop/testing.py:185` — `run_simulated_loop()` constructs `FSMExecutor` directly with `SimulationActionRunner`; parallel states will invoke `ParallelRunner`, bypassing the simulation runner — known gap, document in code comments
- `scripts/little_loops/cli/loop/_helpers.py:56–66` — signal handler reaches `FSMExecutor._current_process` to kill subprocesses; `ParallelRunner` worker threads are not reachable via this mechanism — out of scope for this issue, document as a known limitation
- `scripts/little_loops/fsm/__init__.py:86–94` — re-exports `FSMExecutor` and related symbols as the public `fsm` API; `ParallelRunner` is lazy-imported inside `_execute_parallel_state()` to avoid circular imports, so no `__init__.py` update is needed — verify

### Similar Patterns
- `_execute_sub_loop()` in `executor.py` — Parallel dispatch follows same structure; use as implementation template
- `if state.loop is not None:` block — Dispatch pattern to mirror for `if state.parallel is not None:`

### Tests
- New tests in `scripts/tests/test_fsm_executor.py` — add class `TestParallelExecution` following the `TestSubLoopExecution` pattern at line 3473; write child YAML to `tmp_path / ".loops"`, pass `loops_dir=loops_dir` to `FSMExecutor` (no `fsm/` subdirectory exists)
- Existing: `scripts/tests/test_fsm_executor.py` — Verify no regressions in `loop:` dispatch

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py` — verify `PersistentExecutor._save_state()` correctly serializes `captured[state_name] = {"results": [...]}` produced by `_execute_parallel_state()` (parallel results must round-trip through persistence without loss)
- `scripts/tests/test_ll_loop_execution.py:95` — `TestEndToEndExecution` exercises `_execute_state()` through `PersistentExecutor.run()`; run as a regression gate after implementing the dispatch insertion
- **`TestParallelExecution` must cover** (mirrors `TestSubLoopExecution` method set at `test_fsm_executor.py:3475–3792`): all-workers-succeed → `on_yes`; mixed results → `on_partial`; all-workers-fail → `on_no`; missing child loop with `on_error` set; missing child loop without `on_error`; `context_passthrough=True` stores results in `self.captured[state_name]`; `max_workers` limiting; `fail_mode: collect` vs `fail_mode: fail_fast`

### Documentation
- N/A — internal implementation; no public-facing docs changes

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/loop-types.md:978–1014` — documents `loop:` sub-loop state type; no `parallel:` entry exists; users cannot discover the new state type from this skill (FEAT-1078 scope)
- `skills/create-loop/reference.md:686–713` — documents `loop` field mutual exclusions; `parallel` field and `on_yes`/`on_partial`/`on_no` routing semantics are absent (FEAT-1078 scope)

### Display Files (Out of Scope — Known Gaps)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/layout.py:118–133` — `_get_state_badge()` checks `state.loop is not None` but has no branch for `state.parallel`; parallel states render with no badge in the TUI diagram — track as a separate display issue
- `scripts/little_loops/cli/loop/info.py:548–576` — `_print_state_overview_table()` Type column falls through to `—` for states with no `action`, `action_type`, `next`, or `loop`; parallel states show no type — track as a separate display issue

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

- **`_execute_state()` dispatch insertion point**: `executor.py:396–402`. Insert `if state.parallel is not None:` immediately after the `if state.loop is not None:` block (line 402, before the blank comment line `# Handle unconditional transition`) and before `if state.next:` at line 405.
- **Scope locking architecture**: `LockManager` is instantiated in `cli/loop/run.py:145` and scope lock acquisition happens at `run.py:148` — before `FSMExecutor` is ever constructed (via `PersistentExecutor` at `run.py:217`). `FSMExecutor` has zero awareness of `LockManager`. Option A (leave at CLI) is simplest and sufficient.
- `cli/loop/run.py` — No changes expected; uses `FSMExecutor` via `PersistentExecutor` transparently.
- **Implementation Step 2 (`_route_parallel()`) is eliminated**: Use `self._route(state, result.verdict, ctx)` directly inside `_execute_parallel_state()`. `_route()` at `executor.py:713` already maps `"yes"` → `on_yes`, `"partial"` → `on_partial`, `"no"` → `on_no` via shorthand routing at lines 747–753. No separate routing method is needed.
- **`interpolate()` import**: The standalone `interpolate` function is already imported at the top of `executor.py`. No new import needed inside `_execute_parallel_state()` — only the lazy `from little_loops.fsm.parallel_runner import ParallelRunner` line inside the method body.
- **Effective implementation steps** (supersedes Step 2 in Implementation Steps above):
  1. Add `_execute_parallel_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None` alongside `_execute_sub_loop()` at line 318
  2. Insert `if state.parallel is not None:` dispatch block in `_execute_state()` after line 402, before `if state.next:` at line 405 — pass `ctx` to `_execute_parallel_state(state, ctx)`
  3. Verify `persistence.py:418` — no changes expected
  4. Document known limitations in `_execute_parallel_state()` comments (interceptors skipped, simulation bypassed, signal handler gap)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Verdict values**: Issue body says `done/partial/failed` but FEAT-1075 spec defines `ParallelResult.verdict: str` with values `"yes"` / `"partial"` / `"no"`. Implementation must use FEAT-1075's values. The `_route_parallel()` method maps `"yes"` → `on_yes`, `"partial"` → `on_partial`, `"no"` → `on_no`.
- **`_route_parallel()` simplification**: The existing `_route()` method at `executor.py:713` already handles `on_yes`/`on_partial`/`on_no` for these exact verdict strings. Consider calling `self._route(state, verdict, ctx)` directly instead of adding a separate `_route_parallel()`. If a dedicated method is added for clarity, it can simply delegate to `_route()` or inline the same three-case check.
- **`_execute_parallel_state()` signature**: `_execute_sub_loop()` at `executor.py:318` takes `(self, state: StateConfig, ctx: InterpolationContext) -> str | None`. Mirror this signature for `_execute_parallel_state()` so routing can call `interpolate()` with `ctx`.
- **Lazy import pattern**: `_execute_sub_loop()` imports `resolve_loop_path` and `load_and_validate` inside the method body to avoid circular imports. Apply the same pattern for `ParallelRunner` — import lazily from `little_loops.fsm.concurrency` (where `LockManager` lives; `ParallelRunner` will be added there by FEAT-1075).
- **Test location confirmed**: `scripts/tests/` (flat, no `fsm/` subdirectory). Model tests after `TestSubLoopExecution` at `scripts/tests/test_fsm_executor.py:3473`. FEAT-1077 may target the same file with a `TestParallelExecution` class.
- **Prerequisite status**: Both FEAT-1074 (schema — `StateConfig.parallel` field absent from `schema.py`) and FEAT-1075 (`ParallelRunner` class absent from codebase) are confirmed **Open**. Do not begin implementation until both are merged.
- **`self._interpolate()` does not exist — use `interpolate(string, ctx)` instead**: The `Proposed Solution` code block calls `self._interpolate(state.parallel.items)`, but `FSMExecutor` has no such method. The executor uses a standalone `interpolate()` function (imported at the top of `executor.py`) called as `interpolate(string, ctx)`. The correct items line is `items = interpolate(state.parallel.items, ctx).splitlines()`. This also means `_execute_parallel_state()` **must accept `ctx: InterpolationContext`** as a second parameter — exactly mirroring `_execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None`.
- **Routing decision resolved — drop `_route_parallel()`, call `_route()` directly**: `_route()` at `executor.py:713` already handles `"yes"` → `on_yes`, `"partial"` → `on_partial`, `"no"` → `on_no` via shorthand routing (lines 747–753). `ParallelResult.verdict` is already one of these three strings. Call `return self._route(state, result.verdict, ctx)` at the end of `_execute_parallel_state()`. This makes Implementation Step 2 ("Add `_route_parallel()`") unnecessary — skip it.
- **Corrected `_execute_parallel_state()` code** (supersedes Proposed Solution code block):
  ```python
  def _execute_parallel_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None:
      """Fan out sub-loop execution over a list of items concurrently.
      
      Note: interceptors (_interceptors loop) are skipped for this early-return path,
      consistent with _execute_sub_loop() behavior.
      Note: SimulationActionRunner is bypassed — simulation mode does not support parallel states.
      Note: isolation: worktree handles real conflict risk; FSMExecutor needs no scope lock awareness.
      """
      from little_loops.fsm.parallel_runner import ParallelRunner
      assert state.parallel is not None
      items = interpolate(state.parallel.items, ctx).splitlines()
      runner = ParallelRunner()
      result = runner.run(
          items=items,
          loop_name=state.parallel.loop,
          config=state.parallel,
          parent_context=self.captured if state.parallel.context_passthrough else None,
      )
      self.captured[self.current_state] = {"results": result.all_captures}
      return self._route(state, result.verdict, ctx)
  ```
- **Corrected dispatch block** in `_execute_state()` (insertion point: after line 402, before `if state.next:` at line 405):
  ```python
  if state.parallel is not None:
      try:
          return self._execute_parallel_state(state, ctx)
      except (FileNotFoundError, ValueError) as e:
          if state.on_error:
              return interpolate(state.on_error, ctx)
          raise
  ```

## Impact

- **Priority**: P2 — Core dispatch wiring for FEAT-1072; blocked by FEAT-1074 and FEAT-1075 completing first
- **Effort**: Small — Adds 2 new methods and 1 dispatch block; mirrors the existing `_execute_sub_loop()` pattern exactly
- **Risk**: Low — New code path only; existing `loop:` dispatch block is untouched; scope lock stays at CLI level
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `executor`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-12_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- **Unresolved dependencies**: FEAT-1074 (`StateConfig.parallel` schema) and FEAT-1075 (`ParallelRunner`) are both still Open — implementation cannot begin until both are merged.
- **Verdict values mismatch**: Issue Summary says `done/partial/failed`; Research Findings correct this to `yes/partial/no` per FEAT-1075 spec. Implementation must use corrected values.
- **Routing design choice resolved**: Call `self._route(state, result.verdict, ctx)` directly — `_route()` at line 713 already handles `"yes"/"partial"/"no"`. No `_route_parallel()` method needed. Implementation Step 2 is eliminated.

## Session Log
- `/ll:refine-issue` - 2026-04-12T22:06:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d78494ba-e368-4d92-ac07-474ca60ddbb1.jsonl`
- `/ll:wire-issue` - 2026-04-12T22:00:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbab3ea7-aba1-4f99-878c-4df082545c74.jsonl`
- `/ll:refine-issue` - 2026-04-12T21:53:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6227012-241e-4253-adf1-d540b03b8c94.jsonl`
- `/ll:format-issue` - 2026-04-12T21:50:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e24121c8-614a-47dc-b39d-f7ef139d0a8c.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d6467f5-0702-4f04-ae61-18783596ccff.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
