---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-328: ll-auto verify phase should check implementation markers

## Summary

The `ll-auto` verify phase (Phase 3) only checks whether the issue file was moved to `.issues/completed/`. This misses cases where implementation succeeded but the file wasn't moved (e.g., due to BUG-327). The verify phase should also check for implementation markers in the issue file content and in the Claude session output.

## Current Behavior

Phase 3 checks: "Was the issue file moved to `completed/`?" If not, it reports the issue as not processed, even when the implementation session output clearly shows successful implementation.

## Expected Behavior

Phase 3 should use multiple signals to determine completion:
1. File moved to `completed/` (current check)
2. Issue file content contains implementation markers (e.g., "Status: Implemented")
3. Session output contains success indicators (e.g., "has been implemented", code changes described)

If implementation succeeded but file wasn't moved, verify phase should either move it automatically or flag it as "implemented but needs completion" rather than silently reporting 0 processed.

## Motivation

Without this, `ll-auto` silently under-reports its own success. Users see "Issues processed: 0" when work was actually completed, eroding trust in the automation tool. This is especially important as ll-auto is used for unattended batch processing.

## Proposed Solution

Add fallback checks to the verify phase:

```python
# After checking file location:
if not moved_to_completed:
    # Check issue file content for implementation markers
    content = read_issue_file(issue_path)
    if "Status: Implemented" in content or "Implemented" in content:
        # Move file to completed
        move_to_completed(issue_path)
        log(f"{issue_id} implemented but not moved - auto-completing")
```

## Scope Boundaries

- Only applies to `ll-auto` verify phase, not interactive `/ll:manage_issue`
- Should not attempt to re-run failed implementations
- Should not modify issue content, only move files if implementation markers found

## Implementation Steps

1. Add content-based implementation detection to verify phase
2. Add session output parsing for success indicators
3. Auto-move to completed when implementation is confirmed but file wasn't moved
4. Log clearly when auto-completion happens

## Impact

- **Priority**: P3 - Cosmetic/reporting issue; work is still done, just not tracked
- **Effort**: Small - Add fallback checks to existing verify logic
- **Risk**: Low - Additive change, doesn't modify core flow
- **Breaking Change**: No

## Blocked By

- ENH-309: cli.py must be split into package first (structural change)

## Related Key Documentation

_No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-auto`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3
