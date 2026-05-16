---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# ENH-631: FSM test coverage gaps — `direction="maximize"` via dispatcher; `append_event` without `initialize()`

## Summary

Two small test coverage gaps in the FSM test suite:

1. `TestEvaluateDispatcher` in `test_fsm_evaluators.py` tests the `convergence` type via `evaluate()` but all cases use the default `direction="minimize"`. The `direction="maximize"` path through `EvaluateConfig` is never exercised via the dispatcher (only tested by calling `evaluate_convergence()` directly).

2. `append_event()` in `persistence.py` opens the events file in `"a"` mode and relies on `initialize()` having been called first (to create the parent directory). The test suite always goes through `PersistentExecutor` which calls `initialize()`. The code path where `append_event` is called before `initialize()` is not tested.

## Current Behavior

1. `direction="maximize"` convergence behavior is only tested via direct `evaluate_convergence()` calls. Any regression in how `EvaluateConfig.direction` is passed through the dispatcher would go undetected.
2. `append_event()` called without a prior `initialize()` would raise `FileNotFoundError` (parent dir doesn't exist) but this case has no test.

## Expected Behavior

Both paths should have explicit test coverage.

## Motivation

Small gap; low risk of regression, but covering these paths makes the test suite complete and prevents future refactors from introducing silent regressions.

## Proposed Solution

```python
# Test 1: direction="maximize" through evaluate() dispatcher
def test_dispatch_convergence_maximize(self):
    config = EvaluateConfig(
        type="convergence",
        target=10.0,
        direction="maximize",   # test this path
        ...
    )
    # verify "target" verdict when current >= target

# Test 2: append_event without initialize()
def test_append_event_without_initialize_raises(tmp_path):
    persistence = StatePersistence(tmp_path / "nonexistent_dir" / "state.json")
    with pytest.raises(FileNotFoundError):
        persistence.append_event({"type": "test"})
```

## Scope Boundaries

- Tests only; no production code changes

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_evaluators.py` — add `direction="maximize"` dispatcher test; anchor: `class TestEvaluateDispatcher` ([ref 12a6af0](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/tests/test_fsm_evaluators.py#L440-L481))
- `scripts/tests/test_fsm_persistence.py` — add `append_event` without `initialize()` test

### Source Under Test
- `scripts/little_loops/fsm/persistence.py` — `class StatePersistence`, method `append_event()` (lines 187–194 at scan commit 12a6af0) — no modifications required

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `direction="maximize"` test case to `TestEvaluateDispatcher`
2. Add `append_event`-without-`initialize` test to `test_fsm_persistence.py`

## Impact

- **Priority**: P5 — Low-risk coverage gap; nice-to-have
- **Effort**: Small — Two test additions
- **Risk**: Low — Tests only
- **Breaking Change**: No

## Labels

`enhancement`, `testing`, `fsm`, `captured`

## Resolution

Added two test cases:

1. `TestEvaluateDispatcher::test_dispatch_convergence_maximize_target_reached` and `test_dispatch_convergence_maximize_progress` in `scripts/tests/test_fsm_evaluators.py` — exercises the `direction="maximize"` path through the `evaluate()` dispatcher
2. `TestStatePersistence::test_append_event_without_initialize_raises` in `scripts/tests/test_fsm_persistence.py` — verifies `FileNotFoundError` when `append_event()` is called without `initialize()`

All 168 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ece04b0a-a2ce-4735-8217-fa4d505ba91b.jsonl`
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T23:20:17Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e92f3b7-729f-49fa-923d-832b9db88827.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: new issue; `direction="maximize"` dispatcher test and `append_event`-without-`initialize()` test both confirmed absent

---

**Completed** | Created: 2026-03-07 | Completed: 2026-03-09 | Priority: P5
