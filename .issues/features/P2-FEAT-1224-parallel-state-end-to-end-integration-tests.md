---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-21"
discovered_by: issue-size-review
parent_issue: FEAT-1201
size: Medium
---

# FEAT-1224: Parallel State End-to-End Integration Tests

## Summary

Add three end-to-end integration test methods to `TestEndToEndExecution` in `scripts/tests/test_ll_loop_execution.py` exercising a real parallel loop YAML through `FSMExecutor.run()` with toy sub-loops (un-mocked `ParallelRunner`).

## Parent Issue

Decomposed from FEAT-1201: Parallel State Executor, Integration, and Display Tests

## Use Case

**Who**: Developer closing out the parallel state feature after FEAT-1074/1075/1076 are complete

**Context**: The canonical end-to-end gate that runs `ParallelRunner` un-mocked through `main_loop()` — the only test that verifies fan-out, verdict aggregation, and outer-loop routing end-to-end.

**Goal**: Append three test methods at the end of `TestEndToEndExecution` (before line 562 where `TestLLMFlags` begins).

**Outcome**: `python -m pytest scripts/tests/test_ll_loop_execution.py -x -k parallel_state_end_to_end` passes green.

## Proposed Solution

Append inside `TestEndToEndExecution` (class ends at line 560; `TestLLMFlags` begins at 562):

Write three separate named methods — do NOT use `@pytest.mark.parametrize`:
- `test_parallel_state_end_to_end_on_yes`
- `test_parallel_state_end_to_end_on_partial`
- `test_parallel_state_end_to_end_on_no`

Per the codebase convention at `test_fsm_executor.py:1023–1130` (one method per route variant with a focused docstring).

### Fixture Design

Use toy sub-loops that terminate on their initial state so `subprocess.Popen` is never invoked:

```yaml
name: child
initial: done
states:
  done:
    terminal: true
```

This exact shape (confirmed at `test_fsm_executor.py:3642`) means no `Popen` mock is needed for success paths. For `on_no` / `on_partial`, use a child YAML with `max_iterations: 1` and a non-terminating action to force failure.

### E2E Pattern

```python
monkeypatch.chdir(tmp_path)
with patch("little_loops.fsm.executor.subprocess.Popen") as mock_popen:
    mock_popen.side_effect = _make_mock_popen_factory(returncode=0, stdout="yes\n")
    with patch.object(sys, "argv", ["ll-loop", "run", "<loop-name>"]):
        from little_loops.cli import main_loop
        result = main_loop()
```

Use `isolation: "thread"` and `timeout_seconds: None` for speed. Verify that `isolation: "thread"` is the correct field name for `ParallelStateConfig` (FEAT-1074 deliverable) before writing — field may differ.

### Pre-implementation Checks

- Verify `ParallelStateConfig` field name for isolation mode (`isolation` vs `worker_isolation`)
- Verify verdict aggregation behavior for mixed sub-loop outcomes (partial success)
- MUST use real `FSMExecutor.run()` without mocking `ParallelRunner` — this is the canonical E2E gate

## Integration Map

### Files to Modify
- `scripts/tests/test_ll_loop_execution.py` — Add three test methods inside `TestEndToEndExecution` (append at end; class ends at line 560)

### Dependent Files (all must exist before implementation)
- `scripts/little_loops/fsm/parallel_runner.py` — FEAT-1075
- `scripts/little_loops/fsm/executor.py` — `_execute_parallel_state()` — FEAT-1076
- `scripts/little_loops/fsm/schema.py` — `ParallelStateConfig`, `StateConfig.parallel` — FEAT-1074

### Similar Patterns
- `scripts/tests/test_fsm_executor.py:3634` — `TestSubLoopExecution` — fixture and assertion patterns
- `scripts/tests/test_ll_loop_execution.py:26` — `_make_mock_popen_factory` — subprocess mock factory
- `scripts/tests/test_ll_loop_execution.py:95–560` — `TestEndToEndExecution` — E2E pattern

## Dependencies

- **FEAT-1074** must be complete (schema, validation)
- **FEAT-1075** must be complete (ParallelRunner)
- **FEAT-1076** must be complete (`_execute_parallel_state()`)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_ll_loop_execution.py -x -k parallel_state_end_to_end` passes green
- At least one test exercises a real parallel loop YAML through `FSMExecutor.run()` (not mocked) with ≥2 toy sub-loops
- Fan-out verified via captures; verdict aggregation produces expected value; outer loop routes correctly on `on_yes`, `on_partial`, `on_no`
- Three separate named methods (not parametrized)

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Session Log
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/258256f7-974b-4688-b813-9928466b24ec.jsonl`
