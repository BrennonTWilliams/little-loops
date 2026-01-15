# ENH-060: Test `--quiet` Mode Logo Suppression - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-060-ll-loop-quiet-mode-test.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `--quiet` flag suppresses logo display at `cli.py:576-577`, but this behavior is not explicitly tested.

### Key Discoveries
- Existing test at `test_ll_loop.py:2071-2102` verifies progress output suppression but not logo
- Logo is displayed via `print_logo()` from `logo.py:23-31`
- Logo content in `assets/ll-cli-logo.txt` contains distinctive text: "little loops" and box-drawing characters `╭──╮`
- The existing `test_quiet_mode_suppresses_output` provides a perfect pattern to follow

## Desired End State

A test that explicitly verifies `--quiet` suppresses the logo ASCII art.

### How to Verify
- Test should check that "little loops" text is not in output when `--quiet` is used
- Test passes in quiet mode and demonstrates logo would appear without `--quiet`

## What We're NOT Doing

- Not testing progress output suppression (already covered by existing test)
- Not modifying the logo display implementation
- Not adding tests for `ll-parallel` or `ll-auto` logo suppression

## Solution Approach

Add a new test method `test_quiet_mode_suppresses_logo` to the `TestEndToEndExecution` class, immediately after the existing `test_quiet_mode_suppresses_output` test for logical grouping.

## Implementation Phases

### Phase 1: Add Logo Suppression Test

#### Overview
Add a test that verifies the `--quiet` flag suppresses logo display by checking for the absence of the distinctive "little loops" text.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add new test method after `test_quiet_mode_suppresses_output` (after line 2102)

```python
def test_quiet_mode_suppresses_logo(
    self,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--quiet flag suppresses logo display."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    loop_content = """
name: test-quiet-logo
initial: done
max_iterations: 1
states:
  done:
    terminal: true
"""
    (loops_dir / "test-quiet-logo.yaml").write_text(loop_content)

    monkeypatch.chdir(tmp_path)
    with patch("little_loops.fsm.executor.subprocess.run"):
        with patch.object(sys, "argv", ["ll-loop", "run", "test-quiet-logo", "--quiet"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Logo should not be displayed in quiet mode
        assert "little loops" not in captured.out
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestEndToEndExecution::test_quiet_mode_suppresses_logo -v`
- [ ] Full test suite passes: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- The new test follows the established pattern from `test_quiet_mode_suppresses_output`
- Uses terminal-only loop to avoid subprocess complexity
- Verifies logo text "little loops" is absent from stdout

### Edge Cases
- The test uses the same minimal loop pattern to ensure consistency
- Logo file path resolution is handled by existing `print_logo()` function

## References

- Original issue: `.issues/enhancements/P3-ENH-060-ll-loop-quiet-mode-test.md`
- Existing quiet mode test: `test_ll_loop.py:2071-2102`
- Logo suppression code: `cli.py:576-577`
- Logo content: `assets/ll-cli-logo.txt`
