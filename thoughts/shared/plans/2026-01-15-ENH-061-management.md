# ENH-061: Test `--background` Warning Message - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-061-ll-loop-background-warning-test.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `--background` flag is defined at `cli.py:487` and triggers a warning at `cli.py:670-671`:

```python
if getattr(args, "background", False):
    logger.warning("Background mode not yet implemented, running in foreground")
```

This warning is not currently tested. The codebase has established patterns for testing similar functionality (see `test_quiet_mode_suppresses_output` and `test_quiet_mode_suppresses_logo`).

### Key Discoveries
- Background flag defined at `scripts/little_loops/cli.py:487`
- Warning issued at `scripts/little_loops/cli.py:670-671`
- Test file is `scripts/tests/test_ll_loop.py`
- Pattern: Use `capsys` fixture to capture stdout, warning goes to `captured.out`
- Similar tests at lines 2071-2133 use the same pattern

## Desired End State

A test exists that verifies:
1. `--background` flag produces warning message
2. Warning mentions "Background mode not yet implemented"
3. Execution continues (returns 0) and runs in foreground

### How to Verify
- Run `python -m pytest scripts/tests/test_ll_loop.py::TestMainLoopIntegration::test_background_flag_shows_warning -v`
- Test should pass

## What We're NOT Doing

- Not implementing the actual background mode functionality
- Not refactoring existing tests
- Not adding integration tests for background mode behavior

## Solution Approach

Add a single test method to `TestMainLoopIntegration` class following the established pattern from `test_quiet_mode_suppresses_logo`. The test will:
1. Create a minimal terminal-only loop
2. Run with `--background` flag
3. Verify warning message appears in output
4. Verify execution completes successfully (returns 0)

## Implementation Phases

### Phase 1: Add Test

#### Overview
Add `test_background_flag_shows_warning` to `TestMainLoopIntegration` class.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add test method after `test_quiet_mode_suppresses_logo` (around line 2134)

```python
def test_background_flag_shows_warning(
    self,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--background flag shows warning that it's not implemented."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    loop_content = """
name: test-background
initial: done
max_iterations: 1
states:
  done:
    terminal: true
"""
    (loops_dir / "test-background.yaml").write_text(loop_content)

    monkeypatch.chdir(tmp_path)
    with patch("little_loops.fsm.executor.subprocess.run"):
        with patch.object(sys, "argv", ["ll-loop", "run", "test-background", "--background"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Warning should appear about background mode
        assert "Background mode not yet implemented" in captured.out
        assert "running in foreground" in captured.out
```

#### Success Criteria

**Automated Verification**:
- [ ] Test passes: `python -m pytest scripts/tests/test_ll_loop.py::TestMainLoopIntegration::test_background_flag_shows_warning -v`
- [ ] All tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Test verifies warning message content
- Test verifies execution continues (returns 0)

## References

- Original issue: `.issues/enhancements/P3-ENH-061-ll-loop-background-warning-test.md`
- Similar test pattern: `scripts/tests/test_ll_loop.py:2104-2133`
- Warning implementation: `scripts/little_loops/cli.py:670-671`
