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

`_cmd_sprint_run()` in `cli.py:1619-1735` handles errors but lacks:
- Comprehensive try/except wrapping
- Finally block for guaranteed cleanup
- Proper error classification (interrupted vs failed)
- State persistence on error (when ENH-182 is implemented)

## Expected Behavior

- All exceptions caught and logged appropriately
- Finally block ensures cleanup always runs
- Errors classified as "interrupted" vs "failed"
- State saved on any exit path
- Clean exit codes (0=success, 1=error, 130=interrupted)

## Proposed Solution

Wrap `_cmd_sprint_run()` in comprehensive error handling:

```python
def _cmd_sprint_run(args: argparse.Namespace) -> int:
    """Run a sprint with proper error handling."""
    exit_code = 0
    try:
        # ... existing implementation ...
        return 0
    except KeyboardInterrupt:
        logger.info("Sprint interrupted by user")
        exit_code = 130
    except Exception as e:
        logger.error(f"Sprint failed: {e}")
        exit_code = 1
    finally:
        # Cleanup resources
        if state:  # When ENH-182 is implemented
            state.save()
        logger.info(f"Sprint exiting with code {exit_code}")
    return exit_code
```

Also add error classification for wave/issue failures:
- Track which issues failed vs were interrupted
- Report summary at end showing success/fail/interrupted counts

## Files to Modify

- `scripts/little_loops/cli.py:1619-1735` - Wrap sprint run in try/except/finally

## Dependencies

- Complements ENH-182 (state persistence) and ENH-183 (signal handling)
- Can be implemented independently

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

**Open** | Created: 2026-01-29 | Priority: P3
