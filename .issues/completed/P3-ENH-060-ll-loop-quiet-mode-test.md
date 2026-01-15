# P3-ENH-060: Test `--quiet` Mode Logo Suppression

## Summary

The `--quiet` flag suppresses logo display but this behavior is not explicitly tested.

## Problem

- Progress output suppression is already tested at `test_ll_loop.py:2071-2102` (`test_quiet_mode_suppresses_output`)
- Logo suppression at `cli.py:576-577` is not explicitly verified
- No test confirms that logo ASCII art is absent in quiet mode

## Acceptance Criteria

- [x] ~~Add test that verifies `--quiet` suppresses progress output during execution~~ (Already exists: `test_quiet_mode_suppresses_output`)
- [x] Add test that verifies `--quiet` suppresses logo display
- [x] ~~Compare output between quiet and non-quiet modes~~ (Partially covered by existing test)

## Implementation Notes

```python
def test_quiet_mode_suppresses_logo(tmp_path, capsys, monkeypatch):
    """--quiet should suppress logo display."""
    # Create executable loop
    # Run with --quiet flag
    # Verify logo ASCII art not in output
    # Could check for distinctive logo characters or use get_logo() to compare
```

## Related Files

- `scripts/tests/test_ll_loop.py:1377-1401` - Quiet flag acceptance test
- `scripts/tests/test_ll_loop.py:2071-2102` - Quiet mode output suppression test (EXISTING)
- `scripts/little_loops/cli.py:576-577` - Logo suppression in quiet mode
- `scripts/little_loops/cli.py:616-621` - Progress display quiet mode condition
- `scripts/little_loops/logo.py` - Logo display utilities

## Priority Justification

P3 - Nice to have verification but not critical functionality.

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py:2104-2133`: Added `test_quiet_mode_suppresses_logo` test

### Verification Results
- Tests: PASS (1250 passed)
- Lint: PASS (modified file)
- Types: N/A (test file only)
