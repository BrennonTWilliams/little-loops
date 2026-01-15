# ENH-063: Add Evaluator Execution Context Tests for ll-loop

## Summary

Three of six evaluator types (`output_json`, `convergence`, `llm_structured`) are only unit-tested in isolation. They have never been tested in an actual execution context where they evaluate real state transitions.

## Current State

- **Evaluator Unit Tests**: `scripts/tests/test_fsm_evaluators.py` (771 lines)
- **Execution Tests**: `scripts/tests/test_ll_loop.py`, `test_fsm_executor.py`
- **Coverage**: 4/6 evaluators tested in execution

### Evaluator Coverage Matrix

| Evaluator | Unit Tests | Execution Tests |
|-----------|------------|-----------------|
| `exit_code` | Yes | Yes |
| `output_numeric` | Yes | Yes |
| `output_contains` | Yes | Yes |
| `output_json` | Yes | **NO** |
| `convergence` | Yes | **NO** |
| `llm_structured` | Yes (mocked) | **NO** |

### What's Missing

Integration tests that:
- Use `output_json` to extract JSON field and determine next state
- Use `convergence` to compare current vs previous output
- Use `llm_structured` with mocked Anthropic client to evaluate output

## Proposed Tests

### output_json Execution Tests

```python
class TestEvaluatorExecution:
    """Tests for evaluators in actual execution context."""

    def test_output_json_evaluator_determines_state(self, tmp_path):
        """output_json evaluator extracts field and routes state."""
        loop_yaml = """
        states:
          check:
            action: 'echo \'{"status": "ready", "count": 5}\''
            evaluator:
              type: output_json
              path: "$.status"
              success_value: "ready"
            transitions:
              success: done
              failure: retry
        """
        # Execute and verify transitions to "done"

    def test_output_json_nested_path(self, tmp_path):
        """output_json handles nested JSON paths."""
        # Test with $.data.items[0].value style paths
```

### convergence Execution Tests

```python
    def test_convergence_evaluator_detects_stability(self, tmp_path):
        """convergence evaluator succeeds when output matches previous."""
        loop_yaml = """
        states:
          optimize:
            action: 'echo "stable-value"'
            evaluator:
              type: convergence
              threshold: 0.0
            transitions:
              success: done
              failure: optimize
        """
        # Run twice, second should detect convergence

    def test_convergence_with_threshold(self, tmp_path):
        """convergence allows small differences within threshold."""
        # Test with numeric outputs and threshold tolerance
```

### llm_structured Execution Tests

```python
    def test_llm_structured_evaluator_integration(self, tmp_path):
        """llm_structured evaluator calls LLM and parses response."""
        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_anthropic.return_value.messages.create.return_value = MockResponse(
                content=[{"type": "text", "text": '{"decision": "success"}'}]
            )
            # Execute loop with llm_structured evaluator
            # Verify LLM was called with correct prompt
            # Verify state transition based on response
```

## Implementation Approach

Add tests to `test_fsm_executor.py` or create new `test_evaluator_integration.py`:

1. Create loop configs using each untested evaluator
2. Execute with real `PersistentExecutor` (mocking subprocess/LLM as needed)
3. Verify correct state transitions occur
4. Verify events are logged correctly

## Impact

- **Priority**: P2 (High)
- **Effort**: Medium
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [x] `output_json` evaluator tested in execution with valid JSON output
- [x] `output_json` handles nested JSON paths
- [x] `convergence` evaluator tested with matching outputs
- [x] `convergence` threshold tolerance verified
- [x] `llm_structured` evaluator tested with mocked Anthropic client
- [x] All evaluators correctly determine state transitions
- [x] All new tests pass

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `evaluators`, `fsm`

---

## Status

**Open** | Created: 2026-01-15 | Priority: P2

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_fsm_executor.py`: Added 9 new execution tests for evaluators:
  - `test_output_json_evaluator_determines_state`: Tests JSON field extraction and state routing
  - `test_output_json_nested_path`: Tests nested JSON path like `.data.items.0.value`
  - `test_output_json_numeric_comparison`: Tests numeric operators (`lt`) on JSON values
  - `test_convergence_evaluator_detects_target`: Tests target reached within tolerance
  - `test_convergence_evaluator_tracks_progress`: Tests multi-iteration progress tracking with `${prev.output}`
  - `test_convergence_evaluator_detects_stall`: Tests stall detection when no progress
  - `test_llm_structured_evaluator_routes_on_verdict`: Tests success verdict routing with mocked Anthropic
  - `test_llm_structured_evaluator_failure_verdict`: Tests failure verdict routing
  - `test_llm_structured_evaluator_blocked_verdict`: Tests blocked verdict with custom route table

### Verification Results
- Tests: PASS (39 tests in test_fsm_executor.py)
- Lint: PASS
- Types: PASS
