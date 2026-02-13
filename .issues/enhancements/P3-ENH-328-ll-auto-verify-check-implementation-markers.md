---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-328: ll-auto verify phase should check implementation markers

## Summary

The `ll-auto` verify phase (Phase 3) already has 4 fallback checks (file-move, plan detection, git evidence, auto-complete). This enhancement adds issue file content marker checking (e.g., "Status: Implemented") as an additional fallback signal for cases where implementation succeeded but existing checks don't catch it.

## Current Behavior

Phase 3 already has 4 fallback checks:
1. `verify_issue_completed()` — checks if file was moved to `completed/`
2. `detect_plan_creation()` — checks if a plan was created (returncode 0 but not verified)
3. `verify_work_was_done()` — checks git evidence of code changes
4. `complete_issue_lifecycle()` — auto-completes if work was confirmed

However, there is no check for implementation markers in the issue file content itself (e.g., "Status: Implemented"). This means cases where the issue file was updated with implementation status but git evidence is ambiguous are not caught.

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

- ENH-308: sprint sequential retry for merge-failed issues (shared cli.py)

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` - Add content marker check to verify logic in `process_issue_inplace()`

### Dependent Files (Callers/Importers)
- N/A - verify phase is internal to ll-auto

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_cli.py` - Test verify phase with implementation markers

### Documentation
- N/A

### Configuration
- N/A

## Related Key Documentation

_No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-auto`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3

---

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: NEEDS_UPDATE
- **File references stale**: Verify phase logic is in `scripts/little_loops/issue_manager.py:540-597` (inside `process_issue_inplace()`), NOT in `main_auto()` or `cli.py`. `main_auto()` in `cli/auto.py` is a thin wrapper delegating to `AutoManager.run()`.
- **Current behavior overstated**: The issue says "only checks whether the issue file was moved to completed/". In reality, the verify phase already has 4 fallback checks:
  1. Checks `verify_issue_completed()` (file moved)
  2. If returncode 0 but not verified, checks for plan creation (`detect_plan_creation()`)
  3. If no plan, calls `verify_work_was_done()` to check git evidence of code changes
  4. If work was done, calls `complete_issue_lifecycle()` to auto-complete
- **Still valid**: No check for implementation markers in issue file content (e.g., "Status: Implemented") exists. Enhancement scope should be narrowed to: "add issue file content marker checking as an additional fallback signal."
- **Blocker ENH-308 note**: ENH-308 still open but its own ENH-344 blocker is now resolved

---

## Tradeoff Review Note

**Reviewed**: 2026-02-12 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Verification notes show scope is narrower than described (fallback logic already exists for git evidence). Needs refinement to focus specifically on adding content marker checking as an additional fallback signal only.
