# ENH-068: Add Error Message Content Validation Tests - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-068-ll-loop-error-message-tests.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `TestErrorHandling` class in `scripts/tests/test_ll_loop.py` (line 1770) contains error tests that only verify return codes. None of these tests validate error message content.

### Key Discoveries
- Error tests at `test_ll_loop.py:1773-1890` only assert `result == 1`
- Error messages are logged via `logger.error()` at `logger.py:73-76` to stderr
- The `Logger.error()` method only writes when `verbose=True` at `logger.py:75`
- Existing capsys pattern in `test_logger.py:305-333` shows how to verify stderr
- CLI success tests at `test_ll_loop.py:1084-1115` already use capsys for stdout

### Error Messages to Test (from `cli.py`)
| Scenario | Message Format | Location |
|----------|----------------|----------|
| Missing loop | `"Loop not found: {name}"` | cli.py:650 |
| Validation error | `"Validation error: {e}"` | cli.py:653 |
| Missing input file | `"Input file not found: {path}"` | cli.py:681 |
| YAML parse error | `"YAML parse error: {e}"` | cli.py:692 |
| No state found | `"No state found for: {name}"` | cli.py:817 |
| Nothing to resume | `"Nothing to resume for: {name}"` | cli.py:862 (warning, stdout) |

## Desired End State

All error handling tests in `test_ll_loop.py` will verify:
1. Error messages are printed to stderr (not stdout)
2. Error messages are non-empty
3. Error messages include relevant context (loop name, file path)
4. Error messages contain helpful keywords ("not found", "error", etc.)

### How to Verify
- All tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- Error message assertions use `capsys.readouterr()` pattern

## What We're NOT Doing

- Not modifying the CLI error messages themselves - only testing existing ones
- Not adding new error scenarios - only enhancing existing tests
- Not refactoring existing test structure - keeping `TestErrorHandling` class
- Not testing quiet mode suppression - that's a separate concern

## Problem Analysis

Current tests verify return codes work but provide no assurance that:
- Users see helpful error messages
- Error messages go to stderr (not stdout)
- Error messages include context (file paths, loop names)
- Error messages aren't empty or malformed

## Solution Approach

Add `capsys` fixture to existing error tests and add assertions for error message content, following the established pattern from `test_logger.py`.

## Implementation Phases

### Phase 1: Add TestErrorMessages Class

#### Overview
Create a new `TestErrorMessages` class with tests that verify error message content for each error scenario.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add `TestErrorMessages` class after `TestErrorHandling` class (around line 1890)

```python
class TestErrorMessages:
    """Tests that verify error message content, not just return codes."""

    def test_missing_loop_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Missing loop shows helpful error message."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "nonexistent"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""  # Error message is not empty
        assert "nonexistent" in captured.err  # Mentions the loop name
        assert "not found" in captured.err.lower()  # Helpful error indication

    def test_validation_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Validation error shows what's wrong."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "invalid.yaml").write_text("""
name: invalid
initial: nonexistent
states:
  start:
    action: "echo test"
    terminal: true
""")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "invalid"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""
        assert "validation" in captured.err.lower() or "invalid" in captured.err.lower()
        assert "nonexistent" in captured.err  # Mentions the invalid state

    def test_yaml_parse_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Invalid YAML shows parsing error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "bad.yaml").write_text("invalid: yaml: content: [broken")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "bad"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""
        assert "yaml" in captured.err.lower() or "parse" in captured.err.lower()

    def test_compile_missing_input_error_message(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Compile with missing file shows helpful error."""
        missing_path = tmp_path / "nonexistent.yaml"
        with patch.object(sys, "argv", ["ll-loop", "compile", str(missing_path)]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""
        assert "not found" in captured.err.lower()
        assert str(missing_path) in captured.err or "nonexistent" in captured.err

    def test_status_no_state_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Status with no state shows helpful message."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "status", "test-loop"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""
        assert "test-loop" in captured.err  # Mentions loop name
        assert "not found" in captured.err.lower() or "no state" in captured.err.lower()

    def test_resume_no_state_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Resume with no state shows helpful message."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: start
states:
  start:
    action: "echo test"
    terminal: true
""")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "test"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        # Note: resume with nothing uses logger.warning() which goes to stdout
        combined = captured.out + captured.err
        assert "test" in combined  # Mentions loop name
        assert "nothing" in combined.lower() or "resume" in combined.lower()

    def test_error_messages_go_to_stderr(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Error messages go to stderr, not stdout."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "nonexistent"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""  # Error in stderr
        # stdout may have some output but the error message is in stderr

    def test_error_messages_not_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Error conditions produce non-empty error output."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        error_scenarios = [
            (["ll-loop", "run", "missing"], "missing loop"),
            (["ll-loop", "validate", "missing"], "missing loop validation"),
            (["ll-loop", "status", "missing"], "missing status"),
        ]

        for argv, scenario in error_scenarios:
            monkeypatch.chdir(tmp_path)
            with patch.object(sys, "argv", argv):
                result = main_loop()

            captured = capsys.readouterr()
            assert result == 1, f"Expected error for {scenario}"
            combined = captured.out + captured.err
            assert combined.strip() != "", f"Empty output for {scenario}"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestErrorMessages -v`
- [ ] Type checking: `python -m mypy scripts/tests/test_ll_loop.py`

---

### Phase 2: Verify Full Test Suite

#### Overview
Run the complete test suite to ensure new tests integrate properly.

#### Success Criteria

**Automated Verification**:
- [ ] Full tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_ll_loop.py`

---

## Testing Strategy

### Unit Tests
- Each error scenario has dedicated test verifying message content
- Tests use `capsys` fixture to capture output
- Tests verify both return code and message content

### Edge Cases
- YAML parse errors (malformed YAML)
- Missing required fields
- Invalid state references
- Resume with no saved state (uses warning not error)

## References

- Original issue: `.issues/enhancements/P3-ENH-068-ll-loop-error-message-tests.md`
- Error handling pattern: `scripts/tests/test_logger.py:305-333`
- CLI error output: `scripts/little_loops/cli.py:650-692`
- Existing error tests: `scripts/tests/test_ll_loop.py:1770-1890`
