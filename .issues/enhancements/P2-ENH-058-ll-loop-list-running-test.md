# P2-ENH-058: Add Integration Test for `list --running`

## Summary

The `list --running` flag is parsed but the integration path that calls `list_running_loops()` is not tested.

## Problem

- Argument parsing tested at `test_ll_loop.py:163-168`
- Integration path at `cli.py:786-794` that filters to running loops only is untested
- `list_running_loops()` utility function not exercised through CLI

## Acceptance Criteria

- [x] Add test for `ll-loop list --running` with running loops present
- [x] Add test for `ll-loop list --running` with no running loops
- [x] Verify output shows loop status information (name, state, iteration)
- [x] Verify only running loops are shown (not completed/interrupted)

## Implementation Notes

```python
def test_list_running_shows_only_running_loops(tmp_path, capsys, monkeypatch):
    """list --running should show running loops with status info."""
    # Create .loops/.running/ directory with:
    # - running-loop.state.json (status: "running")
    # - stopped-loop.state.json (status: "interrupted")
    # Call main_loop with ["ll-loop", "list", "--running"]
    # Verify only running-loop appears in output
    # Verify status info displayed

def test_list_running_empty(tmp_path, capsys, monkeypatch):
    """list --running with no running loops should show appropriate message."""
    # Create empty .loops/.running/
    # Call main_loop
    # Verify appropriate "no running loops" message
```

## Related Files

- `scripts/tests/test_ll_loop.py:309-333` - `TestCmdList` class
- `scripts/little_loops/cli.py:786-794` - `--running` branch in `cmd_list()`
- `scripts/little_loops/fsm/persistence.py:350` - `list_running_loops()` function

## Priority Justification

P2 - Important for operational visibility but not critical functionality.

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Added `test_list_running_shows_status_info` - tests `list --running` with running loops present
- `scripts/tests/test_ll_loop.py`: Added `test_list_running_empty` - tests `list --running` with no running loops

### Verification Results
- Tests: PASS (89/89)
- Lint: PASS
- Types: PASS (pre-existing unrelated error in evaluators.py)
