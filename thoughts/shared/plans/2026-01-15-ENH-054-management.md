# ENH-054: Add Tests for Missing ll-loop Subcommands - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-054-ll-loop-missing-subcommand-tests.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `ll-loop` CLI test file (`scripts/tests/test_ll_loop.py`) has comprehensive tests for 6 subcommands but lacks coverage for `stop` and `resume`. Current test file has 787 lines with:

- **Covered**: `run`, `validate`, `list`, `compile`, `status`, `history`
- **Partially covered**: `stop` (only one error case at line 648-661)
- **Not covered**: `resume` (no tests at all)

### Key Discoveries
- `cmd_stop` at `scripts/little_loops/cli.py:828-844` - loads state via `StatePersistence`, marks as "interrupted"
- `cmd_resume` at `scripts/little_loops/cli.py:846-877` - loads FSM definition, calls `PersistentExecutor.resume()`
- Existing test pattern uses `main_loop()` with mocked `sys.argv` and `monkeypatch.chdir()`
- `StatePersistence` tests in `test_fsm_persistence.py:86-266` show mocking patterns
- `MockActionRunner` in `test_fsm_executor.py:21-81` provides action execution mock

## Desired End State

- `cmd_stop` has 3+ tests covering: success case, non-existent loop, already stopped loop
- `cmd_resume` has 3+ tests covering: success case, nothing to resume, file not found
- Error handling paths tested for `run`, `compile`, `validate` commands
- All tests pass with no regressions

### How to Verify
- `python -m pytest scripts/tests/test_ll_loop.py -v` passes
- New test classes `TestCmdStop`, `TestCmdResume`, `TestErrorHandling` exist
- Coverage for `cmd_stop` and `cmd_resume` paths verified

## What We're NOT Doing

- Not adding integration tests that run actual loops (covered by ENH-053)
- Not refactoring existing tests - only adding new test classes
- Not testing PersistentExecutor internals (covered in test_fsm_persistence.py)

## Solution Approach

Add three new test classes to `test_ll_loop.py` following existing integration test patterns:

1. **TestCmdStop** - Test stop subcommand with mocked state files
2. **TestCmdResume** - Test resume subcommand with mocked executor
3. **TestErrorHandling** - Test error paths (FileNotFoundError, ValueError, yaml.YAMLError)

All tests will use the established pattern:
- `tmp_path` for temporary directories
- `monkeypatch.chdir()` for working directory
- `patch.object(sys, "argv", ...)` for CLI arguments
- Direct `main_loop()` calls for integration testing

## Implementation Phases

### Phase 1: Add TestCmdStop Class

#### Overview
Add tests for the `stop` subcommand covering success and error cases.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add `TestCmdStop` class after `TestMainLoopIntegration` (after line 787)

```python
class TestCmdStop:
    """Tests for stop subcommand."""

    def test_stop_running_loop_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop marks running loop as interrupted."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        # Create state file for "running" loop
        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(json.dumps({
            "loop_name": "test-loop",
            "current_state": "check",
            "iteration": 3,
            "captured": {},
            "prev_result": None,
            "last_result": None,
            "started_at": "2026-01-15T10:00:00Z",
            "updated_at": "2026-01-15T10:05:00Z",
            "status": "running"
        }))

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 0
        # Verify status was updated
        updated_state = json.loads(state_file.read_text())
        assert updated_state["status"] == "interrupted"

    def test_stop_nonexistent_loop_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop returns error for unknown loop."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "stop", "nonexistent"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_stop_already_stopped_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop returns error if loop not running."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        # Create state file with "completed" status
        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(json.dumps({
            "loop_name": "test-loop",
            "current_state": "done",
            "iteration": 5,
            "captured": {},
            "prev_result": None,
            "last_result": None,
            "started_at": "2026-01-15T10:00:00Z",
            "updated_at": "2026-01-15T10:05:00Z",
            "status": "completed"
        }))

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_stop_interrupted_loop_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop returns error if loop already interrupted."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(json.dumps({
            "loop_name": "test-loop",
            "current_state": "check",
            "iteration": 3,
            "captured": {},
            "prev_result": None,
            "last_result": None,
            "started_at": "2026-01-15T10:00:00Z",
            "updated_at": "2026-01-15T10:05:00Z",
            "status": "interrupted"
        }))

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestCmdStop -v`

---

### Phase 2: Add TestCmdResume Class

#### Overview
Add tests for the `resume` subcommand covering success and error cases.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add `TestCmdResume` class after `TestCmdStop`

```python
class TestCmdResume:
    """Tests for resume subcommand."""

    def test_resume_nothing_to_resume_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resume returns warning when nothing to resume."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        # Create valid loop file but no state
        loop_content = """
name: test-loop
initial: check
states:
  check:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "test-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_resume_file_not_found_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resume returns error for missing loop file."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "nonexistent"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_resume_validation_error_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resume returns error for invalid loop definition."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        # Create invalid loop (initial state doesn't exist)
        loop_content = """
name: invalid-loop
initial: nonexistent
states:
  check:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "invalid-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "invalid-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_resume_completed_loop_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resume returns error if loop already completed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        # Create valid loop file
        loop_content = """
name: test-loop
initial: check
states:
  check:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        # Create state file with "completed" status
        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(json.dumps({
            "loop_name": "test-loop",
            "current_state": "done",
            "iteration": 5,
            "captured": {},
            "prev_result": None,
            "last_result": None,
            "started_at": "2026-01-15T10:00:00Z",
            "updated_at": "2026-01-15T10:05:00Z",
            "status": "completed"
        }))

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "test-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        # PersistentExecutor.resume() returns None for completed loops
        assert result == 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestCmdResume -v`

---

### Phase 3: Add TestErrorHandling Class

#### Overview
Add tests for error handling paths across subcommands.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add `TestErrorHandling` class after `TestCmdResume`

```python
class TestErrorHandling:
    """Tests for error handling across subcommands."""

    def test_run_validation_error_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run returns error for invalid loop definition."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        # Create invalid loop (initial state doesn't exist)
        loop_content = """
name: invalid-loop
initial: nonexistent
states:
  check:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "invalid-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "invalid-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_validate_invalid_initial_state_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """validate catches missing initial state."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_content = """
name: invalid-loop
initial: nonexistent
states:
  check:
    action: "echo hello"
"""
        (loops_dir / "invalid-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "invalid-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_compile_yaml_error_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """compile returns error for malformed YAML."""
        # Create file with invalid YAML syntax
        input_file = tmp_path / "malformed.yaml"
        input_file.write_text("""
name: test
paradigm: simple
invalid yaml: [unclosed bracket
goal: "Test"
""")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_run_yaml_error_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run returns error for malformed YAML."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        # Create file with invalid YAML syntax
        (loops_dir / "malformed.yaml").write_text("""
name: test
initial: check
states: [unclosed bracket
""")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "malformed"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_status_displays_all_fields(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """status displays all state fields correctly."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(json.dumps({
            "loop_name": "test-loop",
            "current_state": "fixing",
            "iteration": 7,
            "captured": {"errors": "3"},
            "prev_result": None,
            "last_result": None,
            "started_at": "2026-01-15T10:00:00Z",
            "updated_at": "2026-01-15T10:15:00Z",
            "status": "running"
        }))

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "status", "test-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "test-loop" in captured.out
        assert "running" in captured.out
        assert "fixing" in captured.out
        assert "7" in captured.out
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestErrorHandling -v`

---

## Testing Strategy

### Unit Tests
- All tests use `tmp_path` fixture for isolation
- State files created directly as JSON for `stop`/`status` tests
- Loop definition files created as YAML for `resume`/`run`/`validate` tests

### Integration Tests
- All tests call actual `main_loop()` function
- Return codes verified (0 for success, 1 for error)
- Output captured with `capsys` where needed

## References

- Original issue: `.issues/enhancements/P2-ENH-054-ll-loop-missing-subcommand-tests.md`
- Test file: `scripts/tests/test_ll_loop.py`
- CLI implementation: `scripts/little_loops/cli.py:828-877`
- Similar patterns: `scripts/tests/test_fsm_persistence.py:86-266`
