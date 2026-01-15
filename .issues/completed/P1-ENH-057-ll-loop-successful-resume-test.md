# P1-ENH-057: Add Successful Resume Test for ll-loop

## Summary

The `cmd_resume` tests only cover error cases. There is no test for successfully resuming an interrupted loop.

## Problem

`TestCmdResume` at `test_ll_loop.py:1431-1555` only tests:
- Nothing to resume (warning)
- Missing loop file (error)
- Invalid loop definition (error)
- Completed loop (error)

The success path at `cli.py:859-877` where `executor.resume()` actually resumes execution is untested.

## Acceptance Criteria

- [ ] Add test that successfully resumes an interrupted loop
- [ ] Create valid state file with `status: "running"` and valid `current_state`
- [ ] Mock subprocess to control execution
- [ ] Verify resume continues from saved state (not from initial)
- [ ] Verify progress output shows resumed execution
- [ ] Verify returns 0 on successful terminal completion

## Implementation Notes

```python
def test_resume_continues_interrupted_loop(tmp_path, capsys, monkeypatch):
    """Resume should continue from saved state to completion."""
    # 1. Create loop definition
    # 2. Create state file with status="interrupted", current_state="step2"
    # 3. Mock subprocess for remaining states
    # 4. Call main_loop with ["ll-loop", "resume", "test-loop"]
    # 5. Verify execution started from step2, not initial state
    # 6. Verify terminal completion and exit code 0
```

State file structure (note: `status` must be `"running"` for resume to work):
```json
{
  "loop_name": "test-loop",
  "status": "running",
  "current_state": "step2",
  "iteration": 2,
  "captured": {},
  "prev_result": null,
  "last_result": null,
  "started_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:01:00"
}
```

## Related Files

- `scripts/tests/test_ll_loop.py:1431-1555` - `TestCmdResume` class
- `scripts/little_loops/cli.py:846-877` - `cmd_resume()` function
- `scripts/little_loops/fsm/persistence.py` - `PersistentExecutor.resume()`

## Priority Justification

P1 - Resume is a key feature for long-running loops. Without testing the success path, we can't be confident it works correctly.

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Added `test_resume_continues_interrupted_loop` test method to `TestCmdResume` class

### Verification Results
- Tests: PASS (87/87 in test_ll_loop.py)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
