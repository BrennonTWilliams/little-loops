# ENH-183: Add signal handling to ll-sprint - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-183-add-signal-handling-to-ll-sprint.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `_cmd_sprint_run` function in `cli.py:1666-1851` currently has **no signal handling**. When a user presses Ctrl+C:

1. During single-issue waves (`process_issue_inplace`): Process terminates abruptly
2. During multi-issue waves (`ParallelOrchestrator.run()`): The orchestrator's internal signal handler captures it

The sprint state persistence infrastructure already exists (`cli.py:1625-1663`):
- `_save_sprint_state()` saves after each wave
- `_load_sprint_state()` for resume capability
- `_cleanup_sprint_state()` on successful completion

### Key Discoveries
- ll-auto implements signal handling at `issue_manager.py:607-615` using instance method pattern
- ll-parallel implements signal handling at `orchestrator.py:150-160, 433-438` with handler save/restore
- Both use `_shutdown_requested` flag checked in main loop: `while not self._shutdown_requested:`
- Sprint state is already saved after each wave at `cli.py:1805, 1838`

## Desired End State

- SIGINT (Ctrl+C) triggers graceful shutdown at sprint level
- Current wave is allowed to complete (don't interrupt mid-wave)
- State is automatically saved before exit (already happens per-wave)
- User sees clear message about shutdown in progress
- Second SIGINT forces immediate exit
- Sprint can be resumed with `--resume` flag after graceful shutdown

### How to Verify
- Run `ll-sprint run <sprint>` and press Ctrl+C during execution
- Verify graceful shutdown message appears
- Verify state is preserved
- Verify `--resume` continues from correct wave
- Press Ctrl+C twice quickly to verify force exit

## What We're NOT Doing

- Not propagating shutdown to `process_issue_inplace` (single-issue processing is fast)
- Not adding handler restoration (this is a CLI entry point, not a library)
- Not modifying `ParallelOrchestrator` (it already has its own signal handling)
- Not changing state persistence (already implemented properly)

## Problem Analysis

The gap is at the sprint-level wave loop (`cli.py:1774-1840`). When Ctrl+C is pressed:
- If in single-issue mode: Unhandled, process crashes
- If in multi-issue mode: `ParallelOrchestrator` handles it internally

We need sprint-level signal handling that:
1. Sets a shutdown flag when SIGINT/SIGTERM received
2. Checks the flag between waves
3. Logs a message and exits gracefully
4. Supports force exit on second signal

## Solution Approach

Use the simple ll-auto pattern (not the handler-restore pattern) since this is a CLI entry point function that doesn't need to restore handlers. Add module-level globals for the shutdown flag and handler, following the pattern suggested in the issue.

## Implementation Phases

### Phase 1: Add Signal Handler Infrastructure

#### Overview
Add module-level shutdown flag and signal handler function to cli.py, plus registration in `_cmd_sprint_run`.

#### Changes Required

**File**: `scripts/little_loops/cli.py`

1. Add import for `signal` module near other imports (after `import sys`):

```python
import signal
from types import FrameType
```

2. Add module-level shutdown flag and handler after imports (before `main_auto`):

```python
# Module-level shutdown flag for ll-sprint signal handling (ENH-183)
_sprint_shutdown_requested: bool = False


def _sprint_signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle shutdown signals gracefully for ll-sprint.

    First signal: Set shutdown flag for graceful exit after current wave.
    Second signal: Force immediate exit.
    """
    global _sprint_shutdown_requested
    if _sprint_shutdown_requested:
        # Second signal - force exit
        print("\nForce shutdown requested", file=sys.stderr)
        sys.exit(1)
    _sprint_shutdown_requested = True
    print("\nShutdown requested, will exit after current wave...", file=sys.stderr)
```

3. Register signal handlers at start of `_cmd_sprint_run` (after logger creation at line 1674):

```python
    # Setup signal handlers for graceful shutdown (ENH-183)
    global _sprint_shutdown_requested
    _sprint_shutdown_requested = False  # Reset in case of multiple runs
    signal.signal(signal.SIGINT, _sprint_signal_handler)
    signal.signal(signal.SIGTERM, _sprint_signal_handler)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Add Shutdown Check in Wave Loop

#### Overview
Check the shutdown flag between waves and exit gracefully if set.

#### Changes Required

**File**: `scripts/little_loops/cli.py`

1. Add shutdown check at the start of the wave loop (after line 1774 `for wave_num, wave in enumerate(waves, 1):`):

```python
    for wave_num, wave in enumerate(waves, 1):
        # Check for shutdown request (ENH-183)
        if _sprint_shutdown_requested:
            logger.warning("Shutdown requested - saving state and exiting")
            _save_sprint_state(state, logger)
            return 1
```

2. Also check after each wave completes (after the `_save_sprint_state` calls at lines 1805 and 1838), before continuing to next wave:

After line 1807 (`logger.info(f"Continuing to wave {wave_num + 1}/{total_waves}...")`) in single-issue branch:
```python
                # Check for shutdown before next wave (ENH-183)
                if _sprint_shutdown_requested:
                    logger.warning("Shutdown requested - exiting after wave completion")
                    return 1
```

After line 1840 (`logger.info(f"Continuing to wave {wave_num + 1}/{total_waves}...")`) in multi-issue branch:
```python
                # Check for shutdown before next wave (ENH-183)
                if _sprint_shutdown_requested:
                    logger.warning("Shutdown requested - exiting after wave completion")
                    return 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 3: Add Unit Tests

#### Overview
Add tests for signal handler behavior.

#### Changes Required

**File**: `scripts/tests/test_sprint.py`

Add a new test class at the end of the file:

```python
class TestSprintSignalHandler:
    """Tests for sprint signal handling (ENH-183)."""

    def test_signal_handler_sets_flag(self) -> None:
        """First signal sets shutdown flag."""
        from little_loops import cli

        # Reset state
        cli._sprint_shutdown_requested = False

        # Call handler (simulating SIGINT)
        import signal
        cli._sprint_signal_handler(signal.SIGINT, None)

        assert cli._sprint_shutdown_requested is True

    def test_signal_handler_second_signal_exits(self) -> None:
        """Second signal raises SystemExit."""
        import signal
        import pytest
        from little_loops import cli

        # Set flag as if first signal received
        cli._sprint_shutdown_requested = True

        # Second signal should exit
        with pytest.raises(SystemExit) as exc_info:
            cli._sprint_signal_handler(signal.SIGINT, None)

        assert exc_info.value.code == 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v -k "signal"`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test `_sprint_signal_handler` sets flag on first call
- Test `_sprint_signal_handler` exits on second call

### Integration Tests
Manual testing (not automated due to signal complexity):
- Run `ll-sprint run` with a multi-wave sprint
- Press Ctrl+C during execution
- Verify graceful message appears
- Verify state preserved for resume
- Verify double Ctrl+C forces exit

## References

- Original issue: `.issues/enhancements/P2-ENH-183-add-signal-handling-to-ll-sprint.md`
- ll-auto pattern: `issue_manager.py:607-615`
- ll-parallel pattern: `orchestrator.py:150-160, 433-438`
- Sprint state functions: `cli.py:1625-1663`
