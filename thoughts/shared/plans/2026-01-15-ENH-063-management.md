# ENH-063: Add Evaluator Execution Context Tests - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-063-ll-loop-evaluator-execution-tests.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

### Key Discoveries
- Evaluator execution tests exist in `scripts/tests/test_fsm_executor.py:553-657`
- Currently tested: `exit_code`, `output_numeric`, `output_contains`
- Missing tests: `output_json`, `convergence`, `llm_structured`
- `MockActionRunner` class at `test_fsm_executor.py:22-81` provides action result mocking
- Evaluators implemented in `scripts/little_loops/fsm/evaluators.py`

### Existing Test Pattern (test_fsm_executor.py:556-657)
```python
class TestEvaluators:
    def test_exit_code_evaluator(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_success="pass",
                    on_failure="fail",
                ),
                ...
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("test.sh", exit_code=0)
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "pass"
```

## Desired End State

All six evaluator types are tested in execution context with FSMExecutor:
- `exit_code` (already tested)
- `output_numeric` (already tested)
- `output_contains` (already tested)
- `output_json` (NEW)
- `convergence` (NEW)
- `llm_structured` (NEW)

### How to Verify
- All new tests pass: `pytest scripts/tests/test_fsm_executor.py -v`
- Coverage of evaluators in execution context is complete

## What We're NOT Doing

- Not changing evaluator implementations
- Not modifying existing tests
- Not adding CLI-level tests (unit-level with MockActionRunner is sufficient)
- Not testing edge cases already covered in unit tests (`test_fsm_evaluators.py`)

## Implementation Phases

### Phase 1: Add output_json Execution Tests

#### Overview
Add tests to verify `output_json` evaluator correctly extracts JSON fields and routes state transitions in execution context.

#### Changes Required

**File**: `scripts/tests/test_fsm_executor.py`
**Changes**: Add tests to `TestEvaluators` class

```python
def test_output_json_evaluator_determines_state(self) -> None:
    """output_json evaluator extracts field and routes state."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="api.sh",
                evaluate=EvaluateConfig(
                    type="output_json",
                    path=".status",
                    operator="eq",
                    target="ready",
                ),
                on_success="done",
                on_failure="retry",
            ),
            "done": StateConfig(terminal=True),
            "retry": StateConfig(terminal=True),
        },
    )

    # Test string value matches -> success
    mock_runner = MockActionRunner()
    mock_runner.set_result("api.sh", output='{"status": "ready", "count": 5}')
    result = FSMExecutor(fsm, action_runner=mock_runner).run()
    assert result.final_state == "done"

    # Test string value doesn't match -> failure
    mock_runner = MockActionRunner()
    mock_runner.set_result("api.sh", output='{"status": "pending", "count": 5}')
    result = FSMExecutor(fsm, action_runner=mock_runner).run()
    assert result.final_state == "retry"

def test_output_json_nested_path(self) -> None:
    """output_json handles nested JSON paths."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="result.sh",
                evaluate=EvaluateConfig(
                    type="output_json",
                    path=".data.items.0.value",
                    operator="eq",
                    target=42,
                ),
                on_success="done",
                on_failure="retry",
            ),
            "done": StateConfig(terminal=True),
            "retry": StateConfig(terminal=True),
        },
    )

    mock_runner = MockActionRunner()
    mock_runner.set_result(
        "result.sh",
        output='{"data": {"items": [{"value": 42}, {"value": 100}]}}',
    )
    result = FSMExecutor(fsm, action_runner=mock_runner).run()
    assert result.final_state == "done"

def test_output_json_numeric_comparison(self) -> None:
    """output_json uses numeric comparison for numeric values."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="count.sh",
                evaluate=EvaluateConfig(
                    type="output_json",
                    path=".count",
                    operator="lt",
                    target=10,
                ),
                on_success="done",
                on_failure="retry",
            ),
            "done": StateConfig(terminal=True),
            "retry": StateConfig(terminal=True),
        },
    )

    # count=5 < 10 -> success
    mock_runner = MockActionRunner()
    mock_runner.set_result("count.sh", output='{"count": 5}')
    result = FSMExecutor(fsm, action_runner=mock_runner).run()
    assert result.final_state == "done"

    # count=15 not < 10 -> failure
    mock_runner = MockActionRunner()
    mock_runner.set_result("count.sh", output='{"count": 15}')
    result = FSMExecutor(fsm, action_runner=mock_runner).run()
    assert result.final_state == "retry"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators::test_output_json_evaluator_determines_state -v`
- [ ] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators::test_output_json_nested_path -v`
- [ ] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators::test_output_json_numeric_comparison -v`

---

### Phase 2: Add convergence Execution Tests

#### Overview
Add tests to verify `convergence` evaluator tracks progress toward target values across iterations.

#### Changes Required

**File**: `scripts/tests/test_fsm_executor.py`
**Changes**: Add tests to `TestEvaluators` class

```python
def test_convergence_evaluator_detects_target(self) -> None:
    """convergence evaluator returns target verdict when value within tolerance."""
    fsm = FSMLoop(
        name="test",
        initial="optimize",
        states={
            "optimize": StateConfig(
                action="measure.sh",
                evaluate=EvaluateConfig(
                    type="convergence",
                    target=0,
                    tolerance=1.0,
                    direction="minimize",
                ),
                route=RouteConfig(
                    routes={"target": "done", "progress": "optimize", "stall": "stuck"},
                ),
            ),
            "done": StateConfig(terminal=True),
            "stuck": StateConfig(terminal=True),
        },
    )

    # Value 0.5 within tolerance 1.0 of target 0 -> target verdict
    mock_runner = MockActionRunner()
    mock_runner.set_result("measure.sh", output="0.5")
    result = FSMExecutor(fsm, action_runner=mock_runner).run()
    assert result.final_state == "done"

def test_convergence_evaluator_tracks_progress(self) -> None:
    """convergence evaluator tracks progress across iterations."""
    fsm = FSMLoop(
        name="test",
        initial="measure",
        max_iterations=3,
        states={
            "measure": StateConfig(
                action="count.sh",
                capture="last_count",
                evaluate=EvaluateConfig(
                    type="convergence",
                    target=0,
                    tolerance=0,
                    direction="minimize",
                    previous="${captured.last_count.output}",
                ),
                route=RouteConfig(
                    routes={"target": "done", "progress": "measure", "stall": "stuck"},
                ),
            ),
            "done": StateConfig(terminal=True),
            "stuck": StateConfig(terminal=True),
        },
    )

    mock_runner = MockActionRunner()
    # Simulate decreasing values: 10 -> 5 -> 0 (progress, progress, target)
    mock_runner.results = [
        ("count.sh", {"output": "10"}),  # First: progress (no previous)
        ("count.sh", {"output": "5"}),   # Second: progress (10 -> 5)
        ("count.sh", {"output": "0"}),   # Third: target reached
    ]
    mock_runner.use_indexed_order = True

    result = FSMExecutor(fsm, action_runner=mock_runner).run()
    assert result.final_state == "done"
    assert result.iterations == 3

def test_convergence_evaluator_detects_stall(self) -> None:
    """convergence evaluator returns stall when no progress made."""
    fsm = FSMLoop(
        name="test",
        initial="measure",
        max_iterations=2,
        states={
            "measure": StateConfig(
                action="count.sh",
                capture="last_count",
                evaluate=EvaluateConfig(
                    type="convergence",
                    target=0,
                    tolerance=0,
                    direction="minimize",
                    previous="${captured.last_count.output}",
                ),
                route=RouteConfig(
                    routes={"target": "done", "progress": "measure", "stall": "stuck"},
                ),
            ),
            "done": StateConfig(terminal=True),
            "stuck": StateConfig(terminal=True),
        },
    )

    mock_runner = MockActionRunner()
    # No progress: 10 -> 10 (stall)
    mock_runner.results = [
        ("count.sh", {"output": "10"}),  # First: progress (no previous)
        ("count.sh", {"output": "10"}),  # Second: stall (no change)
    ]
    mock_runner.use_indexed_order = True

    result = FSMExecutor(fsm, action_runner=mock_runner).run()
    assert result.final_state == "stuck"
    assert result.iterations == 2
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators::test_convergence_evaluator_detects_target -v`
- [ ] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators::test_convergence_evaluator_tracks_progress -v`
- [ ] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators::test_convergence_evaluator_detects_stall -v`

---

### Phase 3: Add llm_structured Execution Tests

#### Overview
Add tests to verify `llm_structured` evaluator calls Anthropic API and routes state based on LLM verdict, using mocked client.

#### Changes Required

**File**: `scripts/tests/test_fsm_executor.py`
**Changes**: Add imports and tests with mocked Anthropic client

```python
# At top of file, add:
from unittest.mock import MagicMock

# Add to TestEvaluators class:
def test_llm_structured_evaluator_routes_on_verdict(self) -> None:
    """llm_structured evaluator calls LLM and routes based on verdict."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="deploy.sh",
                evaluate=EvaluateConfig(
                    type="llm_structured",
                    prompt="Did the deployment succeed?",
                ),
                on_success="done",
                on_failure="retry",
            ),
            "done": StateConfig(terminal=True),
            "retry": StateConfig(terminal=True),
        },
    )

    # Create mock LLM response
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "evaluate"
    mock_block.input = {
        "verdict": "success",
        "confidence": 0.95,
        "reason": "Deployment completed successfully",
    }
    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_runner = MockActionRunner()
    mock_runner.set_result("deploy.sh", output="Deployed to production")

    with patch("little_loops.fsm.evaluators.ANTHROPIC_AVAILABLE", True):
        with patch("little_loops.fsm.evaluators.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = FSMExecutor(fsm, action_runner=mock_runner).run()

    assert result.final_state == "done"
    # Verify LLM was called
    mock_client.messages.create.assert_called_once()

def test_llm_structured_evaluator_failure_verdict(self) -> None:
    """llm_structured evaluator routes to failure on failure verdict."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="test.sh",
                evaluate=EvaluateConfig(type="llm_structured"),
                on_success="done",
                on_failure="retry",
            ),
            "done": StateConfig(terminal=True),
            "retry": StateConfig(terminal=True),
        },
    )

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "evaluate"
    mock_block.input = {
        "verdict": "failure",
        "confidence": 0.9,
        "reason": "Tests failed",
    }
    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_runner = MockActionRunner()
    mock_runner.set_result("test.sh", output="3 tests failed")

    with patch("little_loops.fsm.evaluators.ANTHROPIC_AVAILABLE", True):
        with patch("little_loops.fsm.evaluators.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = FSMExecutor(fsm, action_runner=mock_runner).run()

    assert result.final_state == "retry"

def test_llm_structured_evaluator_blocked_verdict(self) -> None:
    """llm_structured evaluator routes blocked verdict to configured state."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="deploy.sh",
                evaluate=EvaluateConfig(type="llm_structured"),
                route=RouteConfig(
                    routes={
                        "success": "done",
                        "failure": "retry",
                        "blocked": "needs_help",
                    },
                ),
            ),
            "done": StateConfig(terminal=True),
            "retry": StateConfig(terminal=True),
            "needs_help": StateConfig(terminal=True),
        },
    )

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "evaluate"
    mock_block.input = {
        "verdict": "blocked",
        "confidence": 0.85,
        "reason": "Missing permissions",
    }
    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_runner = MockActionRunner()
    mock_runner.set_result("deploy.sh", output="Permission denied")

    with patch("little_loops.fsm.evaluators.ANTHROPIC_AVAILABLE", True):
        with patch("little_loops.fsm.evaluators.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = FSMExecutor(fsm, action_runner=mock_runner).run()

    assert result.final_state == "needs_help"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators::test_llm_structured_evaluator_routes_on_verdict -v`
- [ ] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators::test_llm_structured_evaluator_failure_verdict -v`
- [ ] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators::test_llm_structured_evaluator_blocked_verdict -v`

---

### Phase 4: Final Verification

#### Overview
Run full test suite to verify all tests pass and no regressions.

#### Success Criteria

**Automated Verification**:
- [ ] All evaluator tests pass: `pytest scripts/tests/test_fsm_executor.py::TestEvaluators -v`
- [ ] Full test file passes: `pytest scripts/tests/test_fsm_executor.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_fsm_executor.py`
- [ ] Type check passes: `mypy scripts/tests/test_fsm_executor.py`

## Testing Strategy

### Unit Tests Added
- `test_output_json_evaluator_determines_state`: String value routing
- `test_output_json_nested_path`: Nested JSON path extraction
- `test_output_json_numeric_comparison`: Numeric operators on JSON values
- `test_convergence_evaluator_detects_target`: Target reached within tolerance
- `test_convergence_evaluator_tracks_progress`: Multi-iteration progress tracking
- `test_convergence_evaluator_detects_stall`: Stall detection
- `test_llm_structured_evaluator_routes_on_verdict`: LLM success routing
- `test_llm_structured_evaluator_failure_verdict`: LLM failure routing
- `test_llm_structured_evaluator_blocked_verdict`: LLM blocked routing

### Key Edge Cases
- JSON with nested paths and array indices
- Convergence with and without previous value
- Convergence across multiple iterations with capture
- LLM with different verdict types

## References

- Original issue: `.issues/enhancements/P2-ENH-063-ll-loop-evaluator-execution-tests.md`
- Evaluator implementations: `scripts/little_loops/fsm/evaluators.py`
- Existing execution tests: `scripts/tests/test_fsm_executor.py:553-657`
- MockActionRunner: `scripts/tests/test_fsm_executor.py:22-81`
