# ENH-057: Add Successful Resume Test for ll-loop - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P1-ENH-057-ll-loop-successful-resume-test.md`
- **Type**: enhancement
- **Priority**: P1
- **Action**: improve

## Current State Analysis

The `TestCmdResume` class at `scripts/tests/test_ll_loop.py:1431-1555` currently only tests error cases:
- `test_resume_nothing_to_resume_returns_error` (line 1434)
- `test_resume_file_not_found_returns_error` (line 1463)
- `test_resume_validation_error_returns_error` (line 1478)
- `test_resume_completed_loop_returns_error` (line 1507)

The success path at `cli.py:865-877` where `executor.resume()` returns a result and logs success is untested.

### Key Discoveries
- Resume only works when state has `status: "running"` (`persistence.py:324-325`)
- State restoration occurs at `persistence.py:328-333`
- Resume emits `loop_resume` event at `persistence.py:336-344`
- Success message format: `"Resumed and completed: {state} ({iterations} iterations, {duration})"` at `cli.py:873-876`
- Pattern for subprocess mocking: `patch("little_loops.fsm.executor.subprocess.run")` from `test_ll_loop.py:1722-1735`
- Pattern for state file creation: `test_ll_loop.py:1308-1344`

## Desired End State

A test that verifies the successful resume path:
1. Creates a loop definition with multiple states
2. Creates a state file with `status: "running"` at a non-initial state
3. Mocks subprocess execution
4. Calls resume and verifies it returns 0
5. Verifies the `loop_resume` event was emitted
6. Verifies execution started from the saved state (not initial)

### How to Verify
- Test passes when running `pytest scripts/tests/test_ll_loop.py -k test_resume_continues`
- Resume path covered in code coverage

## What We're NOT Doing

- Not testing edge cases like partially written state files
- Not testing resume with captured variables (separate enhancement)
- Not refactoring existing tests

## Solution Approach

Add a single comprehensive test `test_resume_continues_interrupted_loop` to `TestCmdResume` class following existing patterns:
- Use same state file structure from `test_stop_running_loop_succeeds`
- Use subprocess mocking from `TestEndToEndExecution`
- Verify resume event in events file

## Implementation Phases

### Phase 1: Add Successful Resume Test

#### Overview
Add `test_resume_continues_interrupted_loop` method to `TestCmdResume` class

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Location**: After `test_resume_completed_loop_returns_error` (around line 1555)
**Changes**: Add new test method

```python
def test_resume_continues_interrupted_loop(
    self,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Resume should continue from saved state to completion."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    running_dir = loops_dir / ".running"
    running_dir.mkdir()

    # Create loop definition with multiple states
    loop_content = """
name: test-loop
initial: step1
max_iterations: 5
states:
  step1:
    action: "echo step1"
    evaluate:
      type: exit_code
    on_success: step2
    on_failure: step1
  step2:
    action: "echo step2"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: step2
  done:
    terminal: true
"""
    (loops_dir / "test-loop.yaml").write_text(loop_content)

    # Create state file showing loop interrupted at step2 (not initial)
    state_file = running_dir / "test-loop.state.json"
    state_file.write_text(
        json.dumps(
            {
                "loop_name": "test-loop",
                "current_state": "step2",
                "iteration": 2,
                "captured": {},
                "prev_result": None,
                "last_result": None,
                "started_at": "2026-01-15T10:00:00Z",
                "updated_at": "2026-01-15T10:05:00Z",
                "status": "running",
            }
        )
    )

    monkeypatch.chdir(tmp_path)
    with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["bash", "-c", "echo step2"],
            returncode=0,
            stdout="step2",
            stderr="",
        )

        with patch.object(sys, "argv", ["ll-loop", "resume", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

    # Verify successful completion
    assert result == 0
    captured = capsys.readouterr()
    assert "Resumed and completed: done" in captured.out

    # Verify loop_resume event was emitted
    events_file = running_dir / "test-loop.events.jsonl"
    assert events_file.exists()

    with open(events_file) as f:
        events = [json.loads(line) for line in f if line.strip()]

    event_types = [e["event"] for e in events]
    assert "loop_resume" in event_types

    # Verify resume started from step2
    resume_event = next(e for e in events if e["event"] == "loop_resume")
    assert resume_event["from_state"] == "step2"
    assert resume_event["iteration"] == 2
```

#### Success Criteria

**Automated Verification** (commands that can be run):
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestCmdResume -v`
- [ ] All ll-loop tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_ll_loop.py`

**Manual Verification** (requires human judgment):
- [ ] Test correctly validates resume from non-initial state

## Testing Strategy

### Unit Tests
- The new test covers the success path of `cmd_resume`
- Verifies state restoration, event emission, and return code

### Integration Tests
- Test is an integration test covering CLI → PersistentExecutor → FSMExecutor flow

## References

- Original issue: `.issues/enhancements/P1-ENH-057-ll-loop-successful-resume-test.md`
- Related patterns: `test_ll_loop.py:1308-1344` (state file creation)
- Similar implementation: `test_ll_loop.py:1722-1735` (subprocess mocking)
