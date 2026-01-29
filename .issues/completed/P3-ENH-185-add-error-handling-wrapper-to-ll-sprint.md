---
discovered_date: 2026-01-29
discovered_by: capture_issue
source: docs/CLI-TOOLS-AUDIT.md
---

# ENH-185: Add error handling wrapper to ll-sprint

## Summary

ll-sprint has basic error handling that lacks the try/except/finally cleanup pattern used by ll-auto and ll-parallel. This can leave resources in inconsistent states on failure.

## Context

Identified from CLI Tools Audit (docs/CLI-TOOLS-AUDIT.md):
- Consistency Matrix shows ll-sprint has "⚠️ Basic" for Error Handling (60% score)
- Listed as "Medium Priority" standardization opportunity
- ll-auto and ll-parallel both use "✅ try/finally" pattern

## Current Behavior

`_cmd_sprint_run()` in `cli.py:1729-1945` handles errors but lacks:
- Comprehensive try/except wrapping around the entire function
- Finally block for guaranteed cleanup on any exit path
- Proper error classification (interrupted vs failed) at the function level

Note: State persistence (ENH-182) and signal handling (ENH-183) have been implemented. However, unexpected exceptions could still bypass state saving.

## Expected Behavior

- All exceptions caught and logged appropriately
- Finally block ensures cleanup always runs
- Errors classified as "interrupted" vs "failed"
- State saved on any exit path
- Clean exit codes (0=success, 1=error, 130=interrupted)

## Proposed Solution

Wrap `_cmd_sprint_run()` main logic in comprehensive error handling:

```python
def _cmd_sprint_run(
    args: argparse.Namespace,
    manager: SprintManager,
    config: BRConfig,
) -> int:
    """Execute a sprint with dependency-aware scheduling."""
    logger = Logger()
    state: SprintState | None = None
    exit_code = 0

    # Setup signal handlers (already implemented - ENH-183)
    ...

    try:
        # ... existing implementation (validation, wave execution, etc.) ...
        return 0
    except KeyboardInterrupt:
        logger.info("Sprint interrupted by user")
        exit_code = 130
    except Exception as e:
        logger.error(f"Sprint failed unexpectedly: {e}")
        exit_code = 1
    finally:
        # Guaranteed cleanup on any exit path
        if state is not None:
            _save_sprint_state(state, logger)
            logger.info("State saved before exit")
        logger.info(f"Sprint exiting with code {exit_code}")
    return exit_code
```

The try/except/finally pattern ensures:
1. **KeyboardInterrupt** is caught (belt-and-suspenders with signal handler)
2. **Unexpected exceptions** are logged and handled gracefully
3. **finally block** guarantees state is saved regardless of exit path

## Files to Modify

- `scripts/little_loops/cli.py:1729-1945` - Wrap sprint run in try/except/finally

## Anchor

Function: `_cmd_sprint_run`

## Dependencies

- ENH-182 (state persistence) - **Completed**
- ENH-183 (signal handling) - **Completed**
- This enhancement adds the final layer of defense for unexpected exceptions

## Impact

- **Priority**: P3 (Medium - reliability improvement)
- **Effort**: Low (straightforward pattern)
- **Risk**: Low (defensive coding, no behavior change on success)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| reference | scripts/little_loops/issue_manager.py | Error handling pattern |
| audit | docs/CLI-TOOLS-AUDIT.md | Source of this issue |

## Labels

`enhancement`, `ll-sprint`, `consistency`, `error-handling`, `captured`

---

## Status

**Completed** | Created: 2026-01-29 | Completed: 2026-01-29 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli.py`: Added try/except/finally wrapper to `_cmd_sprint_run()` function (lines 1848-1969)
  - `try:` block wraps wave execution logic
  - `except KeyboardInterrupt:` returns exit code 130 for user interruptions
  - `except Exception:` catches unexpected errors with logging, returns exit code 1
  - `finally:` guarantees state is saved on any non-success exit
- `scripts/tests/test_sprint.py`: Added `TestSprintErrorHandling` test class with 3 tests:
  - `test_keyboard_interrupt_returns_130`
  - `test_unexpected_exception_returns_1`
  - `test_exception_saves_state`

### Verification Results
- Tests: PASS (41 tests, including 3 new error handling tests)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
