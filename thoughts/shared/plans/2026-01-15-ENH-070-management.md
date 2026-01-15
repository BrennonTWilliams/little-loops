# ENH-070: Add History --tail Integration Test for ll-loop - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-070-ll-loop-history-tail-tests.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The `ll-loop history --tail N` flag is defined in argparse at `scripts/little_loops/cli.py:517-521` with a default value of 50. The truncation logic at `cli.py:889` uses `events[-tail:]` to show the last N events.

### Key Discoveries
- **Argparse definition**: `scripts/little_loops/cli.py:520` - `--tail` with default=50
- **Truncation logic**: `scripts/little_loops/cli.py:889` - `events[-tail:]` slice
- **Output format**: `scripts/little_loops/cli.py:893` - `f"{ts} {event_type}: {details}"`
- **Existing tests**: `scripts/tests/test_ll_loop.py:361-406` - `TestCmdHistory` class with unit tests only
- **Events file fixture**: `scripts/tests/test_ll_loop.py:364-382` - Creates 4 test events
- **Existing integration pattern**: `scripts/tests/test_ll_loop.py:1304-1318` - `test_history_no_events_returns_gracefully`

### What's Currently Tested
- Argparse tests verify `--tail` is accepted and parsed correctly
- Unit test at line 395 verifies slice behavior on events list
- Integration test at line 1304 verifies empty events handling

### What's Missing
Integration tests that:
1. Run the actual CLI with `--tail` flag
2. Verify output contains exactly N events
3. Verify the correct (last N) events are shown
4. Test edge cases: tail=0, tail > total, default behavior

## Desired End State

A comprehensive `TestHistoryTail` class with integration tests verifying:
- `--tail N` shows exactly the last N events
- `--tail 0` shows no events
- `--tail` exceeding total events shows all events
- Default (no `--tail`) shows all events (up to 50)
- Truncation preserves chronological order

### How to Verify
- All new tests pass with `pytest scripts/tests/test_ll_loop.py::TestHistoryTail -v`
- Tests verify actual CLI output, not just slice logic

## What We're NOT Doing

- Not modifying the CLI implementation (tests only)
- Not changing the default tail value
- Not adding tests for negative tail values (argparse handles validation)
- Not refactoring existing TestCmdHistory tests

## Problem Analysis

The current test coverage verifies argparse accepts `--tail` and that Python list slicing works, but doesn't verify the end-to-end behavior of running `ll-loop history --tail N` with actual events files and capturing/validating output.

## Solution Approach

Add a new `TestHistoryTail` class following the established integration test pattern:
1. Use `tmp_path`, `monkeypatch`, and `capsys` fixtures
2. Create events file with known test data
3. Run CLI via `patch.object(sys, "argv", [...])` and `main_loop()`
4. Capture output with `capsys.readouterr()`
5. Verify expected events appear and others don't

## Implementation Phases

### Phase 1: Add TestHistoryTail Class

#### Overview
Add new test class with integration tests for `--tail` flag behavior.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add `TestHistoryTail` class after `TestCmdHistory` (around line 407)

```python
class TestHistoryTail:
    """Integration tests for history --tail flag truncation behavior."""

    @pytest.fixture
    def many_events_file(self, tmp_path: Path) -> Path:
        """Create an events file with 10 events for tail testing."""
        running_dir = tmp_path / ".loops" / ".running"
        running_dir.mkdir(parents=True)
        events_file = running_dir / "test-loop.events.jsonl"

        # Create 10 events with unique identifiers
        events = [
            {
                "event": "transition",
                "ts": f"2026-01-15T10:00:{i:02d}",
                "from": f"state{i}",
                "to": f"state{i+1}",
            }
            for i in range(10)
        ]

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return events_file

    def test_history_tail_limits_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """--tail N should show only last N events."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "3"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # Verify only last 3 events appear (state7, state8, state9)
        assert "state7" in captured.out
        assert "state8" in captured.out
        assert "state9" in captured.out
        # First events should NOT appear
        assert "state0" not in captured.out
        assert "state1" not in captured.out
        assert "state5" not in captured.out

    def test_history_tail_zero_shows_nothing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """--tail 0 should show no events."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "0"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # No transition events should appear
        assert "transition" not in captured.out
        assert "state" not in captured.out

    def test_history_tail_exceeds_events_shows_all(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """--tail N where N > total events shows all events."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "100"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # All 10 events should appear
        for i in range(10):
            assert f"state{i}" in captured.out

    def test_history_default_tail_shows_all_small(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """Without --tail (default 50), all events shown when < 50."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # All 10 events should appear (10 < 50 default)
        for i in range(10):
            assert f"state{i}" in captured.out

    def test_history_tail_preserves_chronological_order(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """Tail should show events in chronological order."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "3"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]

        # Verify chronological order: state7 before state8 before state9
        state7_pos = captured.out.find("state7")
        state8_pos = captured.out.find("state8")
        state9_pos = captured.out.find("state9")
        assert state7_pos < state8_pos < state9_pos

    def test_history_tail_with_empty_events(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--tail with empty events file handles gracefully."""
        # Create empty events file
        running_dir = tmp_path / ".loops" / ".running"
        running_dir.mkdir(parents=True)
        events_file = running_dir / "test-loop.events.jsonl"
        events_file.write_text("")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "5"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "No history" in captured.out
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestHistoryTail -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_ll_loop.py`

---

## Testing Strategy

### Unit Tests
- Existing unit tests in `TestCmdHistory` cover slice logic
- New tests focus on integration/end-to-end behavior

### Integration Tests
- Test actual CLI invocation with `main_loop()`
- Verify stdout output with `capsys`
- Cover all edge cases from acceptance criteria

## Acceptance Criteria Mapping

| Criteria | Test Method |
|----------|-------------|
| --tail N shows exactly N events | `test_history_tail_limits_output` |
| --tail shows last N events (not first) | `test_history_tail_limits_output` (asserts state0 not in output) |
| --tail 0 behavior | `test_history_tail_zero_shows_nothing` |
| --tail exceeding total shows all | `test_history_tail_exceeds_events_shows_all` |
| default (no --tail) shows all | `test_history_default_tail_shows_all_small` |
| All new tests pass | Run pytest |

## References

- Original issue: `.issues/enhancements/P4-ENH-070-ll-loop-history-tail-tests.md`
- Existing history tests: `scripts/tests/test_ll_loop.py:361-406`
- Integration test pattern: `scripts/tests/test_ll_loop.py:1304-1318`
- CLI implementation: `scripts/little_loops/cli.py:879-895`
