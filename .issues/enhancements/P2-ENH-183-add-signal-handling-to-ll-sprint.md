---
discovered_date: 2026-01-29
discovered_by: capture_issue
source: docs/CLI-TOOLS-AUDIT.md
---

# ENH-183: Add signal handling to ll-sprint

## Summary

ll-sprint lacks signal handlers for SIGINT/SIGTERM, causing abrupt termination that loses progress. Both ll-auto and ll-parallel implement graceful shutdown patterns that should be adopted.

## Context

Identified from CLI Tools Audit (docs/CLI-TOOLS-AUDIT.md):
- Consistency Matrix shows ll-sprint has "❌ None" for Signal Handling (35% score)
- Listed as "High Priority" standardization opportunity
- ll-auto implements handlers at `issue_manager.py:609-615`
- ll-parallel implements handlers with proper cleanup

## Current Behavior

When user presses Ctrl+C during sprint execution:
- Process terminates immediately
- Current issue processing is interrupted mid-execution
- No state is saved (compounds ENH-182)
- No cleanup of temporary resources

## Expected Behavior

- SIGINT (Ctrl+C) triggers graceful shutdown
- Current issue is allowed to complete or cleanly abort
- State is persisted before exit (requires ENH-182)
- User sees clear message about shutdown in progress
- Second SIGINT forces immediate exit

## Proposed Solution

1. Add signal handler function following ll-auto pattern:

```python
def _signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    if _shutdown_requested:
        logger.warning("Force shutdown requested")
        sys.exit(1)
    _shutdown_requested = True
    logger.info("Shutdown requested, finishing current issue...")
```

2. Register handlers in `_cmd_sprint_run()`:

```python
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)
```

3. Check `_shutdown_requested` flag in wave execution loop

4. Save state before exit if state persistence is implemented (ENH-182)

## Files to Modify

- `scripts/little_loops/cli.py:1666-1851` - Add signal handlers to sprint run

## Dependencies

- Benefits from ENH-182 (state persistence) for saving progress on shutdown
- Can be implemented independently but full benefit requires both

## Impact

- **Priority**: P2 (High - user experience and reliability)
- **Effort**: Low (well-established pattern to follow)
- **Risk**: Low (proven pattern from other tools)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| reference | scripts/little_loops/issue_manager.py:609-615 | Signal handler pattern |
| audit | docs/CLI-TOOLS-AUDIT.md | Source of this issue |

## Labels

`enhancement`, `ll-sprint`, `consistency`, `captured`

---

## Verification Notes

**Verified: 2026-01-29**

- Confirmed: No signal handling in `_cmd_sprint_run()` at `cli.py:1666-1851`
- ll-auto has signal handlers at `issue_manager.py:609-615`
- ll-parallel has signal handlers in `orchestrator.py`
- Issue description remains accurate

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli.py`: Added module-level `_sprint_shutdown_requested` flag and `_sprint_signal_handler()` function
- `scripts/little_loops/cli.py`: Registered SIGINT/SIGTERM handlers in `_cmd_sprint_run()`
- `scripts/little_loops/cli.py`: Added shutdown checks between waves in the execution loop
- `scripts/tests/test_sprint.py`: Added unit tests for signal handler behavior

### Implementation Details
- First Ctrl+C sets shutdown flag and logs message, allowing current wave to complete
- Second Ctrl+C forces immediate exit with code 1
- State is automatically saved per-wave (already implemented), preserved for resume
- Follows ll-auto pattern (simple module-level handler, no handler restoration needed)

### Verification Results
- Tests: PASS (2 new signal handler tests + 1881 existing tests pass)
- Lint: PASS
- Types: PASS

### Commits
- See git log for commit details

---

## Status

**Completed** | Created: 2026-01-29 | Verified: 2026-01-29 | Completed: 2026-01-29 | Priority: P2
