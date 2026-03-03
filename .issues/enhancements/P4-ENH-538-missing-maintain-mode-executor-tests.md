---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# ENH-538: Missing Executor-Level Tests for `maintain` Mode Restart Behavior

## Summary

`FSMExecutor.run()` has a `maintain` mode code path that restarts the loop when a terminal state is reached instead of terminating. The path has two sub-cases: `on_maintain` target (when set) and `initial` fallback. Compiler-level tests exist but no executor-level test verifies that hitting a terminal state with `maintain=True` restarts the loop, that `on_maintain` overrides `initial`, or that `max_iterations` still terminates a `maintain` loop.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 380–393 (at scan commit: 47c81c8)
- **Anchor**: `in method FSMExecutor.run()`, terminal-state maintain branch
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/executor.py#L380-L393)
- **Code**:
```python
if state_config.terminal:
    if self.fsm.maintain:
        self.iteration += 1
        maintain_target = state_config.on_maintain or self.fsm.initial
        self._emit("route", {"from": self.current_state, "to": maintain_target, "reason": "maintain"})
        self.current_state = maintain_target
        continue
    return self._finish("terminal")
```

## Current Behavior

`maintain` mode logic exists and handles both `on_maintain` and `initial` fallback, but there are no executor-level tests for:
- Terminal state with `maintain=True` causes loop restart (not termination)
- `on_maintain` state is used as restart target when set
- Fallback to `initial` when `on_maintain` is not set
- `max_iterations` still terminates a `maintain` loop
- The emitted `route` event includes `"reason": "maintain"`

## Expected Behavior

A `TestMaintainMode` class in `test_fsm_executor.py` covers the above scenarios.

## Motivation

`maintain` mode is a novel paradigm behavior (restart-on-terminal vs terminate). Untested code paths in the executor's main loop are high-risk: a regression could cause infinite loops, incorrect termination, or wrong restart targets without any test failure.

## Proposed Solution

Add `TestMaintainMode` class to `scripts/tests/test_fsm_executor.py` using the existing `MockActionRunner` fixture:

```python
class TestMaintainMode:
    def test_maintain_restarts_from_initial(self, mock_runner):
        """Terminal state with maintain=True restarts from initial, not terminates."""
        ...
        result = executor.run()
        assert result.termination_reason == "max_iterations"  # not "terminal"

    def test_maintain_uses_on_maintain_target(self, mock_runner):
        """on_maintain overrides initial as restart target."""
        ...

    def test_maintain_max_iterations_terminates(self, mock_runner):
        """max_iterations limit still applies in maintain mode."""
        ...

    def test_maintain_route_event_emitted(self, mock_runner):
        """Restart emits route event with reason='maintain'."""
        ...
```

## Scope Boundaries

- Only adds tests; no implementation changes
- Does not add new maintain-mode features (that would be a separate issue)

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_executor.py` — add `TestMaintainMode` class (or similar)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — code under test; no changes
- `scripts/little_loops/fsm/compilers.py` — `compile_maintain` paradigm (if exists); reference for test setup

### Similar Patterns
- Existing `MockActionRunner`-based tests in `test_fsm_executor.py` and `test_ll_loop_execution.py`

### Tests
- This issue IS the tests

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate existing `MockActionRunner` or test fixture setup in `test_fsm_executor.py`
2. Add `TestMaintainMode` with 4 test cases covering the scenarios above
3. Run `python -m pytest scripts/tests/test_fsm_executor.py -k "maintain"` to confirm all pass

## Impact

- **Priority**: P4 — Test gap in well-defined code path; low urgency but real risk
- **Effort**: Small — ~50 lines of test code using existing fixtures
- **Risk**: Low — Tests only; no production code changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `testing`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P4
