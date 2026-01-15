# ENH-058: Add Integration Test for `list --running` - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-058-ll-loop-list-running-test.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `list --running` flag is implemented in the CLI but lacks integration testing:

- **Argument parsing**: Tested at `test_ll_loop.py:163-168` - verifies `args.running = True`
- **Integration path**: `cli.py:786-794` - the branch that calls `list_running_loops()` is untested
- **Underlying function**: `persistence.py:350-373` - unit tested in `test_fsm_persistence.py:578-590`

### Key Discoveries
- `list_running_loops()` returns ALL state files regardless of status (`persistence.py:366-371`)
- Output format: "Running loops:" header with each loop as `  {name}: {state} (iteration {n})`
- Empty case outputs: "No running loops"
- Existing list tests at `test_ll_loop.py:1090-1147` follow `tmp_path + monkeypatch + capsys` pattern

## Desired End State

Two new integration tests in `TestCmdList` class:
1. `test_list_running_shows_only_running_loops` - verifies running loops display with status info
2. `test_list_running_empty` - verifies "No running loops" message when no state files exist

### How to Verify
- Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestCmdList -v`
- New tests exercise `cli.py:786-794` branch
- Output verification confirms format: name, current_state, iteration

## What We're NOT Doing

- Not modifying `list_running_loops()` to filter by status - that's a separate enhancement
- Not adding tests for malformed state file handling - already unit tested
- Not refactoring existing tests - only adding new ones

## Problem Analysis

The acceptance criteria require:
1. Test `list --running` with running loops present - need state file setup
2. Test `list --running` with no running loops - empty `.running/` directory
3. Verify output shows loop status info (name, state, iteration)
4. Verify only running loops shown (but note: function returns all, output shows all)

Note: The current implementation does NOT filter by status field. `list_running_loops()` returns all state files in `.loops/.running/`. The test should reflect actual behavior.

## Solution Approach

Add two test methods to `TestCmdList` class following existing patterns from:
- `test_list_multiple_loops` at line 1111 - capsys pattern
- `test_stop_running_loop_succeeds` at line 1308 - state file creation pattern

## Implementation Phases

### Phase 1: Add test for running loops present

#### Overview
Add `test_list_running_shows_status_info` method that creates state files and verifies output.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Location**: After `test_list_no_loops_dir` (around line 1147)
**Changes**: Add new test method

```python
def test_list_running_shows_status_info(
    self,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """list --running shows running loops with status info."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    running_dir = loops_dir / ".running"
    running_dir.mkdir()

    # Create state files
    (running_dir / "loop-a.state.json").write_text(
        json.dumps(
            {
                "loop_name": "loop-a",
                "current_state": "check-errors",
                "iteration": 3,
                "captured": {},
                "prev_result": None,
                "last_result": None,
                "started_at": "2026-01-15T10:00:00Z",
                "updated_at": "2026-01-15T10:05:00Z",
                "status": "running",
            }
        )
    )
    (running_dir / "loop-b.state.json").write_text(
        json.dumps(
            {
                "loop_name": "loop-b",
                "current_state": "fix-types",
                "iteration": 1,
                "captured": {},
                "prev_result": None,
                "last_result": None,
                "started_at": "2026-01-15T10:00:00Z",
                "updated_at": "2026-01-15T10:00:30Z",
                "status": "running",
            }
        )
    )

    monkeypatch.chdir(tmp_path)
    with patch.object(sys, "argv", ["ll-loop", "list", "--running"]):
        from little_loops.cli import main_loop

        result = main_loop()

    assert result == 0
    captured = capsys.readouterr()
    assert "Running loops:" in captured.out
    assert "loop-a" in captured.out
    assert "check-errors" in captured.out
    assert "iteration 3" in captured.out
    assert "loop-b" in captured.out
    assert "fix-types" in captured.out
    assert "iteration 1" in captured.out
```

#### Success Criteria

**Automated Verification**:
- [ ] Test passes: `python -m pytest scripts/tests/test_ll_loop.py::TestCmdList::test_list_running_shows_status_info -v`

---

### Phase 2: Add test for empty running loops

#### Overview
Add `test_list_running_empty` method that verifies "No running loops" message.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Location**: After the test from Phase 1
**Changes**: Add new test method

```python
def test_list_running_empty(
    self,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """list --running with no running loops shows appropriate message."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    running_dir = loops_dir / ".running"
    running_dir.mkdir()
    # Empty .running directory - no state files

    monkeypatch.chdir(tmp_path)
    with patch.object(sys, "argv", ["ll-loop", "list", "--running"]):
        from little_loops.cli import main_loop

        result = main_loop()

    assert result == 0
    captured = capsys.readouterr()
    assert "No running loops" in captured.out
```

#### Success Criteria

**Automated Verification**:
- [ ] Test passes: `python -m pytest scripts/tests/test_ll_loop.py::TestCmdList::test_list_running_empty -v`

---

### Phase 3: Run full test suite verification

#### Overview
Verify all tests pass and no regressions introduced.

#### Success Criteria

**Automated Verification**:
- [ ] All TestCmdList tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestCmdList -v`
- [ ] Full test file passes: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Type check passes: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Both new tests are integration tests exercising `cli.py:786-794`
- Tests cover both branches: loops present and no loops

### Integration Tests
- Uses same pattern as existing `TestCmdList` tests
- Creates `.loops/.running/` directory structure
- Invokes `main_loop()` via `sys.argv` patching
- Captures stdout with `capsys`

## References

- Original issue: `.issues/enhancements/P2-ENH-058-ll-loop-list-running-test.md`
- CLI implementation: `scripts/little_loops/cli.py:786-794`
- Similar test pattern: `scripts/tests/test_ll_loop.py:1111-1134`
- State file creation pattern: `scripts/tests/test_ll_loop.py:1308-1344`
