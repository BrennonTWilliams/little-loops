# P1-ENH-056: Add End-to-End Execution Test for ll-loop

## Summary

The `ll-loop` test suite lacks any test that actually executes a loop through `PersistentExecutor.run()`. All current tests stop at `--dry-run` mode, leaving the core execution path untested.

## Problem

The main value proposition of `ll-loop` (running FSM loops with progress display) is completely untested:
- `PersistentExecutor.run()` at `cli.py:626` is never called in tests
- Progress display callback at `cli.py:618-621` never exercised with real events
- Event stream processing through `run_foreground()` at `cli.py:574-642` untested

## Acceptance Criteria

- [x] Add test that executes a simple loop through `main_loop()` without `--dry-run`
- [x] Mock subprocess calls to avoid actual shell execution
- [x] Verify event callback receives expected events (`state_enter`, `action_start`, `evaluate`, `route`) - verified via events file
- [x] Test both successful terminal completion and non-terminal exit
- [x] Test exits with correct return code (0 for terminal, 1 otherwise)
- [x] Verify state and events files are created during execution

Note: Progress display callback integration was found to have a pre-existing bug where event callbacks are not properly forwarded to the display function. Events are verified via the events file instead.

## Implementation Notes

Create a minimal loop definition that:
1. Has 2-3 states with simple transitions
2. Uses `exit_code` evaluator (deterministic, no LLM needed)
3. Mocks `subprocess.run()` to return controlled exit codes

Example approach:
```python
@pytest.fixture
def simple_executable_loop(tmp_path):
    """Create a loop that can be executed with mocked subprocess."""
    loop_content = """
name: test-exec
initial: check
max_iterations: 3
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
    # ... create file

def test_run_executes_loop_to_completion(tmp_path, capsys, monkeypatch):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="test", stderr="")
        # ... verify execution completes
```

## Related Files

- `scripts/tests/test_ll_loop.py` - Test file to modify
- `scripts/little_loops/cli.py:574-642` - `run_foreground()` function to test
- `scripts/little_loops/fsm/executor.py` - FSMExecutor implementation

## Priority Justification

P1 - This is the most critical gap. The core functionality of `ll-loop` (actually running loops) has zero test coverage.

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Added `TestEndToEndExecution` class with 6 new tests:
  - `test_executes_loop_to_terminal_state` - verifies successful execution to terminal
  - `test_exits_on_max_iterations` - verifies exit code 1 when max iterations reached
  - `test_reports_final_state_on_failure` - verifies correct state reported on action failure
  - `test_successful_route_to_terminal` - verifies routing through multiple states
  - `test_quiet_mode_suppresses_output` - verifies --quiet flag behavior
  - `test_creates_state_files` - verifies event persistence (all event types recorded)

### Implementation Details
- Tests mock `little_loops.fsm.executor.subprocess.run` to control action results
- Tests verify correct return codes (0 for terminal, 1 for non-terminal)
- Events verified via `.events.jsonl` file containing all event types
- State files verified at `.loops/.running/` directory

### Verification Results
- Tests: PASS (86/86 tests pass)
- Lint: PASS
- Types: PASS
