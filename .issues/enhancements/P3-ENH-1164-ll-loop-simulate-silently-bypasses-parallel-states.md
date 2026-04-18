---
discovered_date: "2026-04-18"
discovered_by: capture-issue
depends_on: [FEAT-1075, FEAT-1076]
---

# ENH-1164: `ll-loop simulate` Silently Bypasses Parallel States

## Summary

When `ll-loop simulate` runs a loop containing a `parallel:` state, `SimulationActionRunner` is bypassed and `ParallelRunner` launches real worker threads/worktrees. Users get real execution in simulation mode with no warning or error.

## Current Behavior

`_execute_parallel_state()` in `executor.py` (added by FEAT-1076) lazy-imports and invokes `ParallelRunner` unconditionally. `SimulationActionRunner` (constructed in `cli/loop/testing.py:185`) is only used for `action:` states — it has no hook into the parallel dispatch path. A user calling `ll-loop simulate my-loop` with a `parallel:` state in it will trigger real concurrent sub-loop execution against live issue files.

## Expected Behavior

`ll-loop simulate` on a loop containing a `parallel:` state either:
- Raises a clear `NotImplementedError` / user-facing error: "Simulation mode does not support `parallel:` states. Use `--dry-run` or run the loop directly."
- OR stubs the parallel state with a configurable mock result (verdict `"yes"`, empty captures) and emits a warning.

The default (and minimum acceptable) behavior is a blocking error — silent real execution in simulation mode is worse than failing loudly.

## Motivation

Simulation mode exists to let users preview loop behavior without side effects. A silent real execution bypass undermines this guarantee. Users who test their parallel-extended orchestrator loops (ENH-1073) in simulation mode will unknowingly run real refinement/implementation against live issue files.

## Proposed Solution

In `_execute_parallel_state()` (`executor.py`), detect simulation mode before invoking `ParallelRunner`:

```python
def _execute_parallel_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None:
    # Simulation mode: ParallelRunner bypasses SimulationActionRunner — fail loudly
    if isinstance(self.action_runner, SimulationActionRunner):
        raise NotImplementedError(
            f"State '{self.current_state}': simulation mode does not support parallel: states. "
            "Run without --simulate to execute parallel fan-out."
        )
    from little_loops.fsm.parallel_runner import ParallelRunner
    ...
```

`SimulationActionRunner` is importable from `little_loops.cli.loop.testing`. Use `isinstance` check rather than a flag to keep `FSMExecutor` clean of CLI concerns. This mirrors how `SimulationActionRunner` already signals its mode through type identity.

## Implementation Steps

1. Add `isinstance(self.action_runner, SimulationActionRunner)` check at top of `_execute_parallel_state()` in `executor.py`
2. Import `SimulationActionRunner` lazily inside the check to avoid circular imports (same pattern as `ParallelRunner` lazy import)
3. Add test to `TestParallelExecution` in `test_fsm_executor.py`: construct executor with `SimulationActionRunner`, assert `NotImplementedError` raised for parallel state
4. Update `docs/generalized-fsm-loop.md` or `LOOPS_GUIDE.md` to note simulation limitation for `parallel:` states

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — add simulation guard at top of `_execute_parallel_state()`
- `scripts/tests/test_fsm_executor.py` — add simulation mode test case to `TestParallelExecution`

### Similar Patterns
- `cli/loop/testing.py:185` — `run_simulated_loop()` constructs `FSMExecutor` with `SimulationActionRunner`; check pattern already used implicitly for action dispatch
- FEAT-1076 notes: "simulation mode does not support parallel states" — this issue implements that comment

## Acceptance Criteria

- `ll-loop simulate <loop-with-parallel>` raises a clear error identifying the parallel state and the limitation
- Simulation mode on loops without `parallel:` states is unaffected
- Test case passes for the `NotImplementedError` path

## Impact

- **Priority**: P3 — Not blocking parallel feature delivery; existing simulate users won't encounter until ENH-1073 or user-authored parallel loops ship
- **Effort**: Very Small — One guard check, one test, one doc note
- **Risk**: Very Low — Additive guard; no existing behavior changed
- **Breaking Change**: No — simulation mode with parallel states is currently broken (real execution); a clear error is strictly better

## Labels

`fsm`, `parallel`, `simulate`, `cli`

---

## Session Log
- `/ll:capture-issue` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ff9cd96-1544-4ffa-b28c-15aab5e9f3e8.jsonl`

---

**Open** | Created: 2026-04-18 | Priority: P3
