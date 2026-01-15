# ENH-066: Add Resume from Interrupted Status Tests - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-066-ll-loop-interrupted-resume-tests.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

### Key Discoveries
- Resume logic at `persistence.py:324`: `if state.status != "running": return None` - treats "interrupted" same as completed/failed
- Tests exist for "completed" (`test_fsm_persistence.py:411-435`) and "failed" (`test_fsm_persistence.py:437-459`) returning None
- No test exists for "interrupted" status - missing coverage gap
- Test `test_resume_continues_interrupted_loop` at `test_ll_loop.py:1681-1749` uses `status="running"` at line 1729 despite its name suggesting "interrupted"

### How "interrupted" Status Gets Set
1. User runs `ll-loop stop` → `cli.py:841` sets `status="interrupted"`
2. Max iterations reached → `persistence.py:296-297` sets `status="interrupted"`

## Desired End State

1. Test coverage documents that "interrupted" status is NOT resumable (matches completed/failed behavior)
2. Misleading test name fixed to accurately reflect what it tests
3. All tests pass

### How to Verify
- `pytest scripts/tests/test_fsm_persistence.py -k "interrupted"` - new test passes
- `pytest scripts/tests/test_ll_loop.py -k "resume_continues_running"` - renamed test passes
- All existing tests continue to pass

## What We're NOT Doing

- Not changing the resume logic to make "interrupted" resumable (that's a separate design decision)
- Not adding CLI-level tests for "interrupted" status (unit test is sufficient)
- Not documenting design rationale in code comments (issue file serves as documentation)

## Solution Approach

1. Add `test_resume_returns_none_for_interrupted` following the exact pattern of completed/failed tests
2. Rename `test_resume_continues_interrupted_loop` to `test_resume_continues_running_loop`
3. Update the comment at line 1716 to match the new name

## Implementation Phases

### Phase 1: Add Test for Interrupted Status

#### Overview
Add a test that documents the current behavior where "interrupted" status returns None from resume().

#### Changes Required

**File**: `scripts/tests/test_fsm_persistence.py`
**Changes**: Add new test method after `test_resume_returns_none_for_failed` (around line 460)

```python
def test_resume_returns_none_for_interrupted(
    self, simple_fsm: FSMLoop, tmp_loops_dir: Path
) -> None:
    """resume() returns None if loop was interrupted (same as completed/failed)."""
    persistence = StatePersistence("test-loop", tmp_loops_dir)
    persistence.initialize()

    state = LoopState(
        loop_name="test-loop",
        current_state="check",
        iteration=5,
        captured={},
        prev_result=None,
        last_result=None,
        started_at="2024-01-15T10:30:00Z",
        updated_at="",
        status="interrupted",
    )
    persistence.save_state(state)

    executor = PersistentExecutor(
        simple_fsm, persistence=persistence, action_runner=MockActionRunner()
    )
    result = executor.resume()
    assert result is None
```

#### Success Criteria

**Automated Verification**:
- [ ] New test passes: `pytest scripts/tests/test_fsm_persistence.py::TestPersistentExecutor::test_resume_returns_none_for_interrupted -v`

---

### Phase 2: Rename Misleading Test

#### Overview
Rename `test_resume_continues_interrupted_loop` to `test_resume_continues_running_loop` and update its comment.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**:
1. Line 1681: Rename function from `test_resume_continues_interrupted_loop` to `test_resume_continues_running_loop`
2. Line 1716: Update comment from "loop interrupted at step2" to "loop paused at step2"

#### Success Criteria

**Automated Verification**:
- [ ] Renamed test passes: `pytest scripts/tests/test_ll_loop.py::TestLLLoopCLI::test_resume_continues_running_loop -v`
- [ ] Old test name doesn't exist: `pytest scripts/tests/test_ll_loop.py -k "interrupted_loop" --collect-only` returns no tests

---

### Phase 3: Full Verification

#### Overview
Run all tests and linting to ensure changes don't break anything.

#### Success Criteria

**Automated Verification**:
- [ ] All resume tests pass: `pytest scripts/tests/ -k "resume" -v`
- [ ] All persistence tests pass: `pytest scripts/tests/test_fsm_persistence.py -v`
- [ ] All ll_loop tests pass: `pytest scripts/tests/test_ll_loop.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- New test follows exact pattern of existing completed/failed status tests
- Validates that "interrupted" status is treated consistently with other terminal states

### Integration Tests
- Renamed test continues to verify CLI-level resume functionality
- No new integration tests needed

## References

- Original issue: `.issues/enhancements/P3-ENH-066-ll-loop-interrupted-resume-tests.md`
- Similar test pattern: `test_fsm_persistence.py:411-435` (completed status)
- Similar test pattern: `test_fsm_persistence.py:437-459` (failed status)
- Resume logic: `persistence.py:324`
