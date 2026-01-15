# ENH-065: Add Capture-Then-Use Workflow Tests for ll-loop

## Summary

The variable capture and interpolation system allows state A to capture output that state B uses via `${captured.A.output}`. This workflow is not tested end-to-end in execution context, only in isolated unit tests.

## Current State

- **Interpolation Tests**: `scripts/tests/test_fsm_interpolation.py` (292 lines)
- **Coverage Type**: Unit tests for interpolation logic only
- **Execution Tests**: None

### What's Missing

End-to-end tests that:
1. Execute state A with capture enabled
2. Verify capture is stored in state
3. Execute state B that interpolates `${captured.A.output}`
4. Verify interpolated value is correct in action

## Proposed Tests

### Capture-Then-Use Workflow Tests

```python
class TestCaptureWorkflow:
    """Tests for variable capture and interpolation in execution."""

    def test_captured_output_used_in_next_state(self, tmp_path):
        """Output captured in state A is available in state B action."""
        loop_yaml = """
        initial_state: fetch
        states:
          fetch:
            action: 'echo "secret-value-123"'
            capture:
              name: token
              source: output
            transitions:
              success: use
          use:
            action: 'echo "Using: ${captured.token.output}"'
            transitions:
              success: done
          done:
            terminal: true
        """
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "capture-test.yaml").write_text(loop_yaml)

        # Execute loop
        result = execute_loop(tmp_path / ".loops" / "capture-test.yaml")

        # Verify state B's action received interpolated value
        assert "Using: secret-value-123" in result.output

    def test_captured_exit_code_interpolation(self, tmp_path):
        """Captured exit code can be interpolated."""
        loop_yaml = """
        states:
          check:
            action: 'exit 42'
            capture:
              name: result
              source: exit_code
            transitions:
              failure: report
          report:
            action: 'echo "Exit was: ${captured.result.exit_code}"'
        """
        # Verify interpolation works with exit codes

    def test_multiple_captures_available(self, tmp_path):
        """Multiple captures from different states all available."""
        loop_yaml = """
        states:
          step1:
            action: 'echo "first"'
            capture: {name: a}
            transitions: {success: step2}
          step2:
            action: 'echo "second"'
            capture: {name: b}
            transitions: {success: step3}
          step3:
            action: 'echo "${captured.a.output} and ${captured.b.output}"'
        """
        # Verify both captures available in step3

    def test_capture_persists_across_resume(self, tmp_path):
        """Captured variables restored when resuming interrupted loop."""
        # Execute partially, interrupt
        # Resume and verify captures still available
```

### Edge Cases

```python
    def test_missing_capture_interpolation_error(self, tmp_path):
        """Referencing non-existent capture should error clearly."""
        loop_yaml = """
        states:
          use:
            action: 'echo "${captured.nonexistent.output}"'
        """
        # Verify clear error message about missing capture

    def test_capture_with_special_characters(self, tmp_path):
        """Captured output with quotes/newlines handled correctly."""
        # Test with output containing special chars
```

## Implementation Approach

Add tests to `test_fsm_executor.py` or new `test_capture_integration.py`:

1. Create multi-state loops with capture configs
2. Execute with real `PersistentExecutor`
3. Mock subprocess to control captured values
4. Verify interpolation in subsequent state actions
5. Check state persistence includes captures

## Impact

- **Priority**: P3 (Medium)
- **Effort**: Medium
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [x] Test verifies captured output used in next state action
- [x] Test verifies captured exit code interpolation
- [x] Test verifies multiple captures available
- [x] Test verifies captures persist across resume
- [x] Test verifies error on missing capture reference
- [x] All new tests pass

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `interpolation`, `fsm`

---

## Status

**Completed** | Created: 2026-01-15 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_fsm_executor.py`: Added `TestCaptureWorkflow` class with 7 tests
  - `test_captured_output_used_in_next_state`: Verifies `${captured.X.output}` interpolation
  - `test_captured_exit_code_interpolation`: Verifies `${captured.X.exit_code}` interpolation
  - `test_multiple_captures_available_in_later_state`: Verifies multiple captures accessible
  - `test_missing_capture_returns_error`: Verifies error handling for missing captures
  - `test_capture_with_special_characters`: Verifies special chars in output
  - `test_captured_stderr_interpolation`: Verifies `${captured.X.stderr}` interpolation
  - `test_captured_duration_interpolation`: Verifies `${captured.X.duration_ms}` interpolation
- `scripts/tests/test_fsm_persistence.py`: Added `test_resume_preserves_captured_for_interpolation`
  - Verifies captured variables persist across resume and remain usable

### Verification Results
- Tests: PASS (8 new tests, 88 total in files)
- Lint: PASS
- Types: PASS
