# ENH-066: Add Resume from Interrupted Status Tests for ll-loop

## Summary

The `ll-loop` resume functionality handles "completed" and "failed" statuses, but behavior for "interrupted" status is unclear and untested. There are no tests verifying that interrupted loops can be properly resumed with their state intact.

## Current State

- **Resume Command**: `scripts/little_loops/cli.py` - `cmd_resume()`
- **Persistence**: `scripts/little_loops/fsm/persistence.py:324-325` - resume only allows "running" status
- **Test Coverage**: Partial

### Existing Resume Tests

| Test | Location | What It Tests |
|------|----------|---------------|
| `test_resume_continues_interrupted_loop` | test_ll_loop.py:1681 | Misleading name - uses "running" status, not "interrupted" |
| `test_resume_continues_from_saved_state` | test_fsm_persistence.py:711 | Resume from "running" status |
| `test_resume_preserves_captured_for_interpolation` | test_fsm_persistence.py:742 | Captured vars restored (uses "running") |
| `test_resume_returns_none_for_completed` | test_fsm_persistence.py:411 | Completed status returns None |
| `test_resume_returns_none_for_failed` | test_fsm_persistence.py:437 | Failed status returns None |

### What's Missing

1. **Test for "interrupted" status resume behavior** - The code at `persistence.py:324` treats "interrupted" same as completed/failed (returns None), but no test verifies this
2. **Design decision documentation** - Should "interrupted" be resumable? Currently it's not.
3. **Test for `test_resume_continues_interrupted_loop`** - Rename or fix - it tests "running" status despite name

## Proposed Tests

### Option A: Test that "interrupted" is NOT resumable (current behavior)

```python
def test_resume_returns_none_for_interrupted(self, simple_fsm, tmp_loops_dir):
    """Resume returns None for interrupted status (same as completed/failed)."""
    persistence = StatePersistence("test-loop", tmp_loops_dir)
    persistence.initialize()

    state = LoopState(
        loop_name="test-loop",
        current_state="check",
        iteration=5,
        status="interrupted",  # <-- Key difference
        ...
    )
    persistence.save_state(state)

    executor = PersistentExecutor(simple_fsm, persistence=persistence)
    result = executor.resume()
    assert result is None  # Documents current behavior
```

### Option B: Make "interrupted" resumable (feature change)

If interrupted loops *should* be resumable, modify `persistence.py:324`:
```python
# Change from:
if state.status != "running":
    return None

# To:
if state.status in ("completed", "failed"):
    return None
# Allow "running" and "interrupted" to continue
```

Then add test:
```python
def test_resume_interrupted_continues_execution(self, tmp_path, monkeypatch):
    """Interrupted loop should resume from last state."""
    state_data = {"status": "interrupted", "current_state": "step2", ...}
    # ... verify resume succeeds
```

### Rename Misleading Test

The existing `test_resume_continues_interrupted_loop` should be renamed:
```python
# FROM:
def test_resume_continues_interrupted_loop(...)  # Uses status="running"

# TO:
def test_resume_continues_running_loop(...)  # Accurate name
```

## Implementation Approach

1. **Decide design intent**: Should "interrupted" be resumable or not?
   - Currently: NOT resumable (same as completed/failed)
   - The `stop` command sets status to "interrupted" (test_ll_loop.py:1468)

2. **Add missing test**: Either Option A or B from above

3. **Rename misleading test**: `test_resume_continues_interrupted_loop` → `test_resume_continues_running_loop`

4. **Document behavior**: Add docstring explaining why "interrupted" is/isn't resumable

## Impact

- **Priority**: P3 (Medium)
- **Effort**: Low (test + rename only)
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [x] Design decision documented: "interrupted" resumable or not
- [x] Test for "interrupted" status resume behavior added
- [x] `test_resume_continues_interrupted_loop` renamed to `test_resume_continues_running_loop`
- [x] All tests pass

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `resume`, `persistence`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Design Decision
"interrupted" status is NOT resumable, matching behavior of "completed" and "failed" statuses. This is intentional because:
1. User-initiated stops (`ll-loop stop`) set "interrupted" to signal explicit termination intent
2. Max iterations reached also sets "interrupted" to signal the loop may not make progress

### Changes Made
- `scripts/tests/test_fsm_persistence.py`: Added `test_resume_returns_none_for_interrupted` test documenting that interrupted status returns None from resume()
- `scripts/tests/test_ll_loop.py`: Renamed `test_resume_continues_interrupted_loop` to `test_resume_continues_running_loop` and updated comment

### Verification Results
- Tests: PASS (20/20 resume tests pass)
- Lint: PASS
