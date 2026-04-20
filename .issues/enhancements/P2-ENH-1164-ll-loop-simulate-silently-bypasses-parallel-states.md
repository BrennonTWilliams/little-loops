---
discovered_date: "2026-04-18"
discovered_by: capture-issue
depends_on: [FEAT-1075, FEAT-1076]
---

# ENH-1164: `ll-loop simulate` Silently Bypasses Parallel States

> **Status: active — acceptance criteria folded into FEAT-1076.** Un-deferred 2026-04-20 during parallel-FSM issue-set review: this issue was in `.issues/deferred/`, but backlog tooling (`ll-auto`, `ll-parallel`, `find_issues`) excludes deferred files, so a folded-into-another-issue note did not survive in the active backlog. This file is retained in `.issues/enhancements/` as a tracking artifact and to own its tests (simulation dry-run aggregate shape; no-warning-no-error behavior; event stream parity). The simulation-mode guard itself is an acceptance criterion of FEAT-1076 (see FEAT-1076 "Blockers & Folded Criteria" and "Implementer checklist"). **Action on ship**: when FEAT-1076 merges, move this file to `.issues/completed/` and add a Session Log entry pointing at the FEAT-1076 PR. Do NOT re-implement the guard; only own its tests.

## Summary

When `ll-loop simulate` runs a loop containing a `parallel:` state, `SimulationActionRunner` is bypassed and `ParallelRunner` launches real worker threads/worktrees. Users get real execution in simulation mode with no warning or error.

## Current Behavior

`_execute_parallel_state()` in `executor.py` (added by FEAT-1076) lazy-imports and invokes `ParallelRunner` unconditionally. `SimulationActionRunner` (constructed in `cli/loop/testing.py:185`) is only used for `action:` states — it has no hook into the parallel dispatch path. A user calling `ll-loop simulate my-loop` with a `parallel:` state in it will trigger real concurrent sub-loop execution against live issue files.

## Expected Behavior

`ll-loop simulate` on a loop containing a `parallel:` state executes each item **sequentially** through the active `SimulationActionRunner` instead of invoking the real `ParallelRunner`. The sequential dry-run:

- Iterates `parallel.items` in order, running the named sub-loop once per item through the simulation runner (no threads, no worktrees, no real sub-process execution)
- Aggregates per-item outcomes into the same `{"results": [...]}` shape that `ParallelRunner` produces, so downstream routing (`on_yes` / `on_partial` / `on_no`) behaves identically to real execution
- Derives the verdict with the same rule (`"yes"` / `"partial"` / `"no"`)
- Emits the same event stream that normal simulation emits for sub-loops — each item produces its own dry-run trace
- Never raises for the presence of a `parallel:` state; raising would make `ll-loop simulate` unusable for any loop containing parallel fan-out, defeating the purpose of simulate as an authoring tool

Simulation deliberately does not preserve concurrency — the goal is to preview the loop's logic, not to stress-test the runner.

## Motivation

Simulation mode exists to let users preview loop behavior without side effects. A silent real execution bypass undermines this guarantee. Users who test their parallel-extended orchestrator loops (ENH-1073) in simulation mode will unknowingly run real refinement/implementation against live issue files.

Raising `NotImplementedError` was considered and rejected: simulate is a primary authoring tool, and a hard failure on every loop containing a `parallel:` state would push users to run loops for real just to preview behavior — exactly the opposite of what simulate is for. A sequential dry-run through the simulation runner preserves the tool's value while still avoiding real side effects.

## Proposed Solution

In `_execute_parallel_state()` (`executor.py`), detect simulation mode before invoking `ParallelRunner` and route to a sequential dry-run path instead:

```python
def _execute_parallel_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None:
    items = self._resolve_parallel_items(state.parallel, ctx)

    # Simulation mode: run items sequentially through the simulation runner,
    # producing the same {"results": [...]} shape ParallelRunner emits.
    from little_loops.cli.loop.testing import SimulationActionRunner
    if isinstance(self.action_runner, SimulationActionRunner):
        results = []
        for item in items:
            # Construct a child executor for state.parallel.loop, wired with the
            # same SimulationActionRunner, and run it exactly as _execute_sub_loop
            # would for a single item. Record its captured dict + terminated_by.
            child_result = self._run_simulated_parallel_item(
                state.parallel, item, ctx
            )
            results.append(child_result)
        verdict = self._derive_parallel_verdict(results)
        self.captured[self.current_state] = {"results": results}
        return self._route(state, verdict, ctx)

    # Normal execution: real parallel fan-out
    from little_loops.fsm.parallel_runner import ParallelRunner
    ...
```

`SimulationActionRunner` is importable from `little_loops.cli.loop.testing`. Using an `isinstance` check (rather than a runtime flag) keeps `FSMExecutor` clean of CLI concerns and mirrors how `SimulationActionRunner` already signals its mode through type identity.

The sequential path reuses the same verdict-derivation and result-shape logic as `ParallelRunner` so that `on_yes` / `on_partial` / `on_no` routing is exercised identically in simulation and real execution. The only behavioral difference is concurrency: simulate runs items one at a time, which is the correct tradeoff for a dry-run authoring tool.

## Implementation Steps

1. Add `isinstance(self.action_runner, SimulationActionRunner)` branch at the top of `_execute_parallel_state()` in `executor.py`
2. Import `SimulationActionRunner` lazily inside the branch to avoid circular imports (same pattern as `ParallelRunner` lazy import)
3. Implement the sequential dry-run: iterate `parallel.items`, spawn a child `FSMExecutor` per item wired with the same `SimulationActionRunner`, collect each child's `captured` / `terminated_by` into a `results` list matching `ParallelRunner`'s `{"results": [...]}` shape
4. Reuse `ParallelRunner`'s verdict-derivation rule (all-succeeded / all-failed / mixed → `"yes"` / `"no"` / `"partial"`) — factor it into a shared helper if duplication would otherwise grow
5. Write `self.captured[self.current_state] = {"results": results}` and call `self._route(state, verdict, ctx)` so downstream routing matches real execution exactly
6. Add test to `TestParallelExecution` in `test_fsm_executor.py`: construct executor with `SimulationActionRunner`, run a 2-item parallel state, assert results contain one entry per item, assert verdict/routing match the configured sub-loop outcomes, assert no real threads or worktrees were created (mock `ParallelRunner` and assert it was never invoked)
7. Update `docs/generalized-fsm-loop.md` or `LOOPS_GUIDE.md` with one paragraph explaining that `parallel:` states run sequentially under `ll-loop simulate`

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — add simulation guard at top of `_execute_parallel_state()`
- `scripts/tests/test_fsm_executor.py` — add simulation mode test case to `TestParallelExecution`

### Similar Patterns
- `cli/loop/testing.py:185` — `run_simulated_loop()` constructs `FSMExecutor` with `SimulationActionRunner`; check pattern already used implicitly for action dispatch
- FEAT-1076 notes: "simulation mode does not support parallel states" — this issue implements that comment

## Acceptance Criteria

- `ll-loop simulate` on a loop containing a `parallel:` state completes without error and produces a dry-run trace showing each item processed sequentially through the simulation runner
- Per-item results are aggregated into `self.captured[state_name]["results"]` matching `ParallelRunner`'s output shape
- Verdict derivation (`"yes"` / `"partial"` / `"no"`) under simulation matches what real execution would produce for the same sub-loop outcomes
- `on_yes` / `on_partial` / `on_no` routing is exercised identically in simulate and real execution
- `ParallelRunner` is never instantiated when simulation mode is active (verified by mock assertion in the test)
- Simulation mode on loops without `parallel:` states is unaffected

## Impact

- **Priority**: P2 — **Must ship with FEAT-1076.** Without this, `ll-loop simulate` on any loop containing a `parallel:` state triggers real concurrent sub-loop execution against live issue files — a data-safety issue, not a UX gap. Users dry-running ENH-1073 orchestrator loops in simulation will unknowingly run real refine/implement work. The cost of deferring is paid by users before they realize the bypass exists.
- **Effort**: Small — Sequential dispatch branch, a verdict-derivation helper (possibly shared with `ParallelRunner`), one integration test, one doc note
- **Risk**: Low — Additive branch on a new code path (`_execute_parallel_state` ships in FEAT-1076); no existing non-parallel behavior changed
- **Breaking Change**: No — simulation mode with parallel states is currently broken (real execution); a sequential dry-run is strictly better

## Ship Bundling

**This issue must land in the same release as FEAT-1076.** FEAT-1076 introduces `_execute_parallel_state()`; this issue adds the simulation guard at its entry point. Shipping FEAT-1076 without this guard is equivalent to shipping a broken dry-run mode for any loop that adopts `parallel:`.

## Labels

`fsm`, `parallel`, `simulate`, `cli`

---

## Session Log
- `/ll:capture-issue` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ff9cd96-1544-4ffa-b28c-15aab5e9f3e8.jsonl`

---

**Open** | Created: 2026-04-18 | Priority: P2 (promoted from P3 on 2026-04-18 — blocker for FEAT-1076 ship)
