# ENH-185: Add Error Handling Wrapper to ll-sprint - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-185-add-error-handling-wrapper-to-ll-sprint.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `_cmd_sprint_run` function at `cli.py:1729-1945` executes sprint-based issue processing. It already has:
- **Signal handling** (ENH-183): Module-level `_sprint_shutdown_requested` flag with double-signal force exit
- **State persistence** (ENH-182): State saved after each wave completion

### Key Discoveries
- `cli.py:1729-1945`: Main function has no try/except/finally wrapper around execution
- `cli.py:1854-1934`: Wave execution loop - unexpected exceptions bypass state saving
- `orchestrator.py:115-157`: ll-parallel uses `try:/except KeyboardInterrupt:/except Exception:/finally:` pattern
- `issue_manager.py:701-726`: ll-auto uses `try:/except Exception:/finally:` pattern
- Current exit code convention: 0=success, 1=error (no 130 for interrupts currently used)

### Gap Analysis
If an unexpected exception occurs after state initialization (`cli.py:1803`) but before completion (`cli.py:1945`), the function will:
1. Propagate the exception without saving state
2. Leave resources in inconsistent state
3. Not provide a clean exit code

## Desired End State

The `_cmd_sprint_run` function wrapped in try/except/finally that:
1. Catches `KeyboardInterrupt` as belt-and-suspenders with signal handler (returns 130)
2. Catches unexpected `Exception` with logging (returns 1)
3. Guarantees state is saved in `finally` block regardless of exit path
4. Provides clear error classification in logs

### How to Verify
- Tests pass: `pytest scripts/tests/test_sprint.py -v`
- Lint passes: `ruff check scripts/`
- Type check passes: `mypy scripts/little_loops/`
- KeyboardInterrupt during execution saves state and returns 130
- Unexpected exception saves state and returns 1

## What We're NOT Doing

- Not changing the signal handler behavior (already implemented in ENH-183)
- Not changing the state persistence functions (already implemented in ENH-182)
- Not adding signal handler save/restore pattern (ll-sprint uses module-level handlers, not class-based)
- Not adding exit code 130 to early validation failures (no state exists yet)
- Not modifying ParallelOrchestrator calls (it has its own error handling)

## Problem Analysis

The function has multiple exit points but no unified error handling:

| Exit Path | Line | Has State? | Currently Saves? |
|-----------|------|------------|------------------|
| Sprint not found | 1748 | No | N/A |
| Invalid issues | 1767 | No | N/A |
| No issue files | 1773 | No | N/A |
| Dependency cycles | 1783 | No | N/A |
| Wave generation error | 1790 | No | N/A |
| Dry run | 1801 | No | N/A |
| Shutdown before wave | 1859 | Yes | Yes |
| Shutdown after wave | 1897/1934 | Yes | Yes (at 1891/1928) |
| Unexpected exception | N/A | Yes | **NO** |
| Success | 1945 | Yes | Cleaned up |
| Failed waves | 1941 | Yes | **NO** |

The two "NO" cases are the gaps this enhancement addresses.

## Solution Approach

Wrap the wave execution portion (lines 1848-1945) in try/except/finally:
- The early validation (lines 1745-1843) can remain outside since no state exists yet
- The wave execution loop needs the protection
- Use the ll-parallel pattern with separate KeyboardInterrupt handling

## Implementation Phases

### Phase 1: Add Try/Except/Finally Wrapper

#### Overview
Wrap the wave execution logic in a try/except/finally block that ensures state is always saved on error.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Location**: Lines 1844-1945 (wave execution section)

The key insight: We need to track whether state has been initialized and save it in finally only if it exists and we're exiting abnormally.

**Change 1**: Add exit_code tracking variable after state initialization (around line 1844):

```python
    # Track exit status for error handling
    exit_code = 0
    state_initialized = True  # At this point state exists
```

**Change 2**: Wrap lines 1845-1944 in try/except/finally:

```python
    try:
        # Determine max workers
        max_workers = args.max_workers or (sprint.options.max_workers if sprint.options else 2)

        # Execute wave by wave
        completed: set[str] = set(state.completed_issues)
        failed_waves = 0
        total_duration = 0.0
        total_waves = len(waves)

        for wave_num, wave in enumerate(waves, 1):
            # ... existing wave processing code (unchanged) ...

        wave_word = "wave" if len(waves) == 1 else "waves"
        logger.info(f"\nSprint completed: {len(completed)} issues processed ({len(waves)} {wave_word})")
        logger.timing(f"Total execution time: {format_duration(total_duration)}")
        if failed_waves > 0:
            logger.warning(f"{failed_waves} wave(s) had failures")
            exit_code = 1
        else:
            # Clean up state on successful completion
            _cleanup_sprint_state(logger)

    except KeyboardInterrupt:
        # Belt-and-suspenders with signal handler
        logger.warning("Sprint interrupted by user (KeyboardInterrupt)")
        exit_code = 130

    except Exception as e:
        logger.error(f"Sprint failed unexpectedly: {e}")
        exit_code = 1

    finally:
        # Guaranteed state save on any non-success exit
        if exit_code != 0 and state_initialized:
            _save_sprint_state(state, logger)
            logger.info("State saved before exit")

    return exit_code
```

**Change 3**: Remove the `return 1` at line 1941 and `return 0` at line 1945 since we now return at the end.

#### Key Design Decisions

1. **Why exit_code variable?** - Allows finally block to conditionally save state only on error
2. **Why state_initialized flag?** - Ensures we don't try to save undefined state
3. **Why save only on error?** - Success path already cleans up state; we don't want to recreate it
4. **Why catch KeyboardInterrupt separately?** - Provides clearer classification (130 vs 1)

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_sprint.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `mypy scripts/little_loops/cli.py`
- [ ] Existing integration tests pass: `pytest scripts/tests/test_sprint_integration.py -v`

**Manual Verification**:
- [ ] Code review confirms try/except/finally structure matches ll-parallel pattern
- [ ] Exit codes are correct: 0=success, 1=error, 130=interrupt

---

### Phase 2: Add Unit Tests for Error Handling

#### Overview
Add tests to verify the error handling wrapper behaves correctly.

#### Changes Required

**File**: `scripts/tests/test_sprint.py`

Add a new test class `TestSprintErrorHandling` with tests for:

```python
class TestSprintErrorHandling:
    """Tests for _cmd_sprint_run error handling (ENH-185)."""

    def test_keyboard_interrupt_saves_state(self, tmp_path, monkeypatch):
        """KeyboardInterrupt during wave processing saves state and returns 130."""
        # Mock process_issue_inplace to raise KeyboardInterrupt
        # Verify state file exists after function returns
        # Verify return code is 130

    def test_unexpected_exception_saves_state(self, tmp_path, monkeypatch):
        """Unexpected exception saves state and returns 1."""
        # Mock process_issue_inplace to raise RuntimeError
        # Verify state file exists after function returns
        # Verify return code is 1

    def test_failed_waves_returns_one(self, tmp_path, monkeypatch):
        """Failed waves (without exception) return 1."""
        # Mock process_issue_inplace to return failure
        # Verify return code is 1
        # Verify state file is cleaned up (success path)
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `pytest scripts/tests/test_sprint.py -v -k TestSprintErrorHandling`
- [ ] Full test suite passes: `pytest scripts/tests/test_sprint.py -v`

**Manual Verification**:
- [ ] Tests cover the three key scenarios: interrupt, exception, failed waves

---

## Testing Strategy

### Unit Tests
- Test KeyboardInterrupt is caught and state saved
- Test generic Exception is caught and state saved
- Test successful completion cleans up state
- Test failed waves return 1 but don't leave stale state

### Integration Tests
The existing integration tests in `test_sprint_integration.py` should continue to pass unchanged.

## References

- Original issue: `.issues/enhancements/P3-ENH-185-add-error-handling-wrapper-to-ll-sprint.md`
- ll-parallel pattern: `scripts/little_loops/parallel/orchestrator.py:115-157`
- ll-auto pattern: `scripts/little_loops/issue_manager.py:701-726`
- Signal handler: `scripts/little_loops/cli.py:26-43`
- State functions: `scripts/little_loops/cli.py:1688-1727`
