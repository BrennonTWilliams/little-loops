# ENH-068: Add Error Message Content Validation Tests for ll-loop

## Summary

All error handling tests in `ll-loop` only verify return codes (`assert result == 1`), not the actual error messages displayed to users. This means error messages could be empty, misleading, or malformed without tests catching it.

## Current State

- **Test File**: `scripts/tests/test_ll_loop.py`
- **Error Tests**: `TestErrorHandling` class
- **Coverage**: Return codes only

### Current Test Pattern

```python
def test_run_missing_loop_returns_error(self, tmp_path, monkeypatch):
    """Missing loop file should return error."""
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", ["ll-loop", "run", "nonexistent"]):
        result = main_loop()
        assert result == 1  # Only checks code, not message
```

### What's Missing

Assertions that verify:
1. Error message is printed to stderr
2. Error message is helpful (mentions what went wrong)
3. Error message includes relevant context (file path, loop name)
4. Error message formatting is consistent

## Proposed Tests

### Error Message Content Tests

```python
class TestErrorMessages:
    """Tests that verify error message content, not just return codes."""

    def test_missing_loop_error_message(self, tmp_path, monkeypatch, capsys):
        """Missing loop shows helpful error message."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".loops").mkdir()

        with patch("sys.argv", ["ll-loop", "run", "nonexistent"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert "nonexistent" in captured.err  # Mentions the loop name
        assert "not found" in captured.err.lower() or "does not exist" in captured.err.lower()

    def test_invalid_yaml_error_message(self, tmp_path, monkeypatch, capsys):
        """Invalid YAML shows parsing error with location."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "bad.yaml").write_text("invalid: yaml: content:")

        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["ll-loop", "validate", "bad"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert "yaml" in captured.err.lower() or "parse" in captured.err.lower()

    def test_validation_error_shows_field(self, tmp_path, monkeypatch, capsys):
        """Validation error mentions which field is invalid."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "incomplete.yaml").write_text("states: {}")  # Missing required fields

        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["ll-loop", "validate", "incomplete"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        # Should mention what's missing/invalid

    def test_resume_no_state_error_message(self, tmp_path, monkeypatch, capsys):
        """Resume with no state shows helpful message."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text(VALID_LOOP_YAML)

        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["ll-loop", "resume", "test"]):
            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert "no saved state" in captured.err.lower() or "not found" in captured.err.lower()
```

### Error Consistency Tests

```python
    def test_error_messages_go_to_stderr(self, tmp_path, monkeypatch, capsys):
        """All error messages should go to stderr, not stdout."""
        # Test various error conditions
        # Verify stderr has content, stdout is empty (or only has normal output)

    def test_error_messages_not_empty(self, tmp_path, monkeypatch, capsys):
        """Error conditions should never produce silent failures."""
        error_scenarios = [
            (["ll-loop", "run", "missing"], "missing loop"),
            (["ll-loop", "validate", "invalid"], "invalid loop"),
            (["ll-loop", "resume", "no-state"], "no state"),
        ]
        for argv, scenario in error_scenarios:
            # Each should produce non-empty stderr
```

## Implementation Approach

Enhance `TestErrorHandling` in `test_ll_loop.py`:

1. Use `capsys` fixture to capture stdout/stderr
2. Add assertions for `captured.err` content
3. Verify error messages contain relevant context
4. Test various error scenarios

## Impact

- **Priority**: P3 (Medium)
- **Effort**: Low
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Error tests verify message content, not just return code
- [ ] Tests verify error messages go to stderr
- [ ] Tests verify error messages are non-empty
- [ ] Tests verify error messages include relevant context
- [ ] All existing error scenarios have message assertions
- [ ] All new tests pass

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `error-handling`, `ux`

---

## Status

**Open** | Created: 2026-01-15 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Added `TestErrorMessages` class with 8 tests verifying error message content

### Tests Added
1. `test_missing_loop_error_message` - Verifies missing loop shows loop name and "not found"
2. `test_validation_error_message` - Verifies validation errors include invalid field names
3. `test_yaml_parse_error_message` - Verifies YAML errors mention "yaml" or "parse"
4. `test_compile_missing_input_error_message` - Verifies compile with missing file shows path
5. `test_status_no_state_error_message` - Verifies status with no state shows loop name
6. `test_resume_no_state_error_message` - Verifies resume with no state shows helpful message
7. `test_error_messages_go_to_stderr` - Verifies error messages go to stderr
8. `test_error_messages_not_empty` - Verifies multiple error scenarios produce non-empty output

### Verification Results
- Tests: PASS (130/130 in test_ll_loop.py)
- Lint: PASS
- Types: PASS
