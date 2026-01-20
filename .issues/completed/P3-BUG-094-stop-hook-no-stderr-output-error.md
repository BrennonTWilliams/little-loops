---
discovered_date: 2026-01-19
discovered_by: capture_issue
---

# BUG-094: Stop hook reports "No stderr output" error

## Summary

Claude Code reports a false error when the stop hook runs:
```
Ran 1 stop hook
  ⎿  Stop hook error: Failed with non-blocking status code: No stderr output
```

This is a Claude Code bug, not a problem with the hook script. The `session-cleanup.sh` script runs successfully but produces no stderr output (by design), which Claude Code incorrectly interprets as a failure.

## Current Behavior

The `session-cleanup.sh` script:
- Runs cleanup operations with all errors suppressed (`2>/dev/null || true`)
- Outputs success message to stdout only
- Exits with code 0

Claude Code's stop hook handler expects stderr output and reports failure when none is present.

## Expected Behavior

Stop hooks that exit with code 0 should be reported as successful, regardless of stderr output.

## Reproduction Steps

1. Use the little-loops plugin in any project
2. Start a Claude Code session
3. End the session (Ctrl+C or natural completion)
4. Observe the "No stderr output" error message

## Proposed Solution

**Workaround**: Add an empty line to stderr to satisfy Claude Code's expectation.

In `hooks/scripts/session-cleanup.sh`, before `exit 0`:

```bash
echo "" >&2  # Workaround for Claude Code stop hook stderr check
```

This produces an empty stderr line without polluting the error stream with meaningful content.

## Impact

- **Priority**: P3 (cosmetic error, functionality works correctly)
- **Effort**: Trivial (one-line change)
- **Risk**: None

## Files to Modify

- `hooks/scripts/session-cleanup.sh`

## Notes

- This is a workaround for a Claude Code bug (possibly v2.1.5 regression)
- The actual cleanup functionality works fine
- When Claude Code fixes this upstream, the workaround can be removed

## Labels

`bug`, `hooks`, `workaround`, `captured`

---

## Status

**Open** | Created: 2026-01-19 | Priority: P3
