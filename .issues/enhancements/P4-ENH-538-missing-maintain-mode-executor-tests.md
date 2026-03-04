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

`maintain` mode logic exists and handles both `on_maintain` and `initial` fallback. Three of four scenarios are already covered by existing test classes (`TestMaintainMode:840`, `TestMaintainModeExecutor:2249`). One scenario remains untested:
- The emitted `route` event includes `"reason": "maintain"`

## Expected Behavior

A `test_maintain_route_event_emitted` test in `TestMaintainMode` (or `TestMaintainModeExecutor`) verifies that restarting in maintain mode emits a `route` event with `reason="maintain"`.

## Motivation

`maintain` mode is a novel paradigm behavior (restart-on-terminal vs terminate). Untested code paths in the executor's main loop are high-risk: a regression could cause infinite loops, incorrect termination, or wrong restart targets without any test failure.

## Proposed Solution

Add a single test to `TestMaintainMode` in `scripts/tests/test_fsm_executor.py`:

```python
def test_maintain_route_event_emitted(self, mock_runner):
    """Restart in maintain mode emits a route event with reason='maintain'."""
    ...
    events = [e for e in executor.events if e["type"] == "route"]
    assert any(e["data"].get("reason") == "maintain" for e in events)
```

## Scope Boundaries

- Only adds one test; no implementation changes
- Does not add new maintain-mode features (that would be a separate issue)

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_executor.py` — add `test_maintain_route_event_emitted` to `TestMaintainMode` (line 840)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — code under test; no changes
- `scripts/little_loops/fsm/compilers.py` — `compile_maintain` paradigm (if exists); reference for test setup

### Similar Patterns
- Existing `MockActionRunner`-based tests in `test_fsm_executor.py` and `test_ll_loop_execution.py`
- `test_fsm_executor.py:1606` — `TestSignalHandling` class — same test class pattern to follow

### Tests
- This issue IS the tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — Existing maintain mode test coverage:_

**Partial coverage confirmed (verified 2026-03-03):**
- `scripts/tests/test_fsm_executor.py:840` — `TestMaintainMode` class exists and covers: (1) terminal state with `maintain=True` causes restart (`test_maintain_restarts_after_terminal`), (2) `on_maintain` target overrides `initial` (`test_maintain_uses_on_maintain_target`), (3) `max_iterations` still terminates (`test_maintain_max_iterations_terminates`)
- `scripts/tests/test_fsm_executor.py:2249` — `TestMaintainModeExecutor` class also exists

**Only scenario 4 is missing**: the emitted `route` event with `reason: "maintain"` (`test_maintain_route_event_emitted`). Scope is now a single test case, not a full class.

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/tests/test_fsm_executor.py:840` (`TestMaintainMode`)
2. Add `test_maintain_route_event_emitted` using the existing `MockActionRunner` fixture pattern
3. Run `python -m pytest scripts/tests/test_fsm_executor.py -k "route_event_emitted"` to confirm it passes

## Impact

- **Priority**: P4 — Test gap in well-defined code path; low urgency but real risk
- **Effort**: Small — ~50 lines of test code using existing fixtures
- **Risk**: Low — Tests only; no production code changes
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Testing strategy — mock patterns and fixture examples (line 1525), maintain paradigm (line 33) |
| `docs/development/TESTING.md` | FSM execution testing patterns (line 668), `MockActionRunner` documentation (line 537) |

## Labels

`enhancement`, `ll-loop`, `testing`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — CRITICAL: Found `TestMaintainMode:840` and `TestMaintainModeExecutor:2133` already exist in `test_fsm_executor.py`; issue may be stale
- `/ll:verify-issues` — 2026-03-03 — Confirmed 3/4 scenarios covered by `TestMaintainMode:840` and `TestMaintainModeExecutor:2249` (not 2133); corrected line ref. Narrowed scope to single missing test: `test_maintain_route_event_emitted`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P4
