# ENH-053: Add Integration Tests for ll-loop CLI

## Summary

The `ll-loop` CLI command lacks integration tests. Current tests simulate argument parsing logic rather than testing the actual `main_loop()` entry point. This means the CLI could break without tests catching it.

## Current State

- **Test File**: `scripts/tests/test_ll_loop.py` (402 lines)
- **Coverage Type**: Unit-level logic simulation only
- **Integration Tests**: None

### What's Missing

The tests recreate parsers and simulate logic patterns but never:
- Call `main_loop()` directly
- Test actual CLI argv parsing
- Invoke real `cmd_*` handler functions
- Test the shorthand conversion (`ll-loop fix-types` -> `ll-loop run fix-types`)

## Proposed Tests

### CLI Entry Point Tests

1. **Argument Parsing Integration**
   - Test `main_loop()` with mocked `sys.argv`
   - Verify shorthand loop name -> `run` subcommand conversion
   - Test unknown subcommand handling
   - Test missing required arguments

2. **Subcommand Dispatch**
   - Test each subcommand routes to correct handler
   - Mock dependencies (file system, executor) to isolate CLI logic

### End-to-End Tests (with fixtures)

1. **Run Command Integration**
   - Create temp `.loops/` directory with valid loop file
   - Test `ll-loop run test-loop` executes successfully
   - Test `--dry-run` outputs execution plan
   - Test `--max-iterations` override applies
   - Test `--quiet` suppresses output

2. **Validate Command Integration**
   - Test valid loop returns success
   - Test invalid loop returns error with message

3. **List Command Integration**
   - Test with empty `.loops/` directory
   - Test with multiple loop files
   - Test `--running` flag with mocked running state

4. **Compile Command Integration**
   - Test paradigm compilation with temp files
   - Test `-o` output path works
   - Test missing input file error

## Implementation Approach

```python
import subprocess
from unittest.mock import patch

class TestMainLoopIntegration:
    """Integration tests that call main_loop() directly."""

    def test_shorthand_inserts_run(self, tmp_path, monkeypatch):
        """ll-loop fix-types becomes ll-loop run fix-types."""
        # Setup temp loop file
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "fix-types.yaml").write_text(VALID_LOOP_YAML)

        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["ll-loop", "fix-types", "--dry-run"]):
            from little_loops.cli import main_loop
            exit_code = main_loop()
            assert exit_code == 0
```

Use `pytest` fixtures and `monkeypatch` to:
- Mock `sys.argv` for different CLI invocations
- Create temporary `.loops/` directories
- Mock `PersistentExecutor` to avoid real execution
- Capture stdout/stderr for output verification

## Impact

- **Priority**: P2 (Medium)
- **Effort**: Medium
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [x] `main_loop()` is tested with various argv combinations
- [x] Shorthand loop name conversion is verified
- [x] Each subcommand has at least one integration test
- [x] Tests use real argument parsing, not recreated parsers
- [x] Coverage of `cli.py` `main_loop` function reaches 60%+

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `cli`

---

## Status

**Completed** | Created: 2026-01-15 | Completed: 2026-01-15 | Priority: P2

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Added `TestMainLoopIntegration` class with 17 new integration tests

### Tests Added
1. `test_shorthand_inserts_run_subcommand` - Tests shorthand conversion (ll-loop fix-types -> ll-loop run fix-types)
2. `test_run_dry_run_outputs_plan` - Tests --dry-run flag outputs execution plan
3. `test_run_with_max_iterations_shows_in_plan` - Tests -n/--max-iterations override
4. `test_run_missing_loop_returns_error` - Tests error handling for missing loop
5. `test_validate_valid_loop_succeeds` - Tests validate command with valid loop
6. `test_validate_missing_loop_returns_error` - Tests validate with missing loop
7. `test_list_empty_loops_dir` - Tests list with empty .loops/ directory
8. `test_list_multiple_loops` - Tests list shows all available loops
9. `test_list_no_loops_dir` - Tests list handles missing .loops/ gracefully
10. `test_status_no_state_returns_error` - Tests status with no saved state
11. `test_stop_no_running_loop_returns_error` - Tests stop with no running loop
12. `test_history_no_events_returns_gracefully` - Tests history with no events
13. `test_compile_valid_paradigm` - Tests compile creates output file
14. `test_compile_with_output_flag` - Tests compile -o flag
15. `test_compile_missing_input_returns_error` - Tests compile with missing input
16. `test_unknown_command_shows_help` - Tests no command shows help
17. `test_run_quiet_flag_accepted` - Tests --quiet flag is accepted

### Verification Results
- Tests: PASS (42 tests in test_ll_loop.py, 1190 total)
- Lint: PASS
- Types: PASS
