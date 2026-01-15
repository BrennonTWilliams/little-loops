# P3-ENH-061: Test `--background` Warning Message

## Summary

The `--background` flag triggers a warning message that background mode is not yet implemented, but this warning is not tested.

## Problem

- Background flag accepted at `cli.py:487`
- Warning message at `cli.py:670-671` never verified in tests
- User would not know if this warning accidentally stopped appearing

## Acceptance Criteria

- [x] Add test that verifies `--background` flag produces warning message
- [x] Verify warning text mentions background mode not implemented
- [x] Verify execution continues in foreground after warning

## Implementation Notes

```python
def test_background_flag_shows_warning(tmp_path, capsys, monkeypatch):
    """--background should warn that it's not implemented."""
    # Create valid loop
    # Run with --background --dry-run (dry-run to avoid execution)
    # Verify warning message in stderr or stdout
    # Verify execution plan still shown (continues in foreground)
```

Expected warning at `cli.py:670-671`:
```python
if args.background:
    logger.warning("Background mode not yet implemented, running in foreground")
```

## Related Files

- `scripts/tests/test_ll_loop.py` - Add test
- `scripts/little_loops/cli.py:670-671` - Warning message

## Priority Justification

P3 - Low priority, mainly for completeness. The feature isn't implemented anyway.

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Added `test_background_flag_shows_warning` test in `TestEndToEndExecution` class

### Verification Results
- Tests: PASS (103/103)
- Lint: PASS
