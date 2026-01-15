---
discovered_commit: 4dea1b4a40efb6abdf0fe660d57cddb64b34eb7c
discovered_date: 2026-01-14
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# BUG-051: Issue lifecycle: git mv fails when source not under version control

## Summary

When completing issue lifecycle (moving issue file to `completed/`), the `git mv` command fails because the source file is not under version control. This is a different error than BUG-009 (destination exists) and indicates the source file was never added to git or was removed from git tracking.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 1
**Affected External Issues**: BUG-745

### Sample Log Output

```
[23:16:27] Closing BUG-745: Closed - Invalid (reason: invalid_ref)
[23:16:27] git mv failed: fatal: not under version control, source=.issues/bugs/P0-BUG-745-mesh-vertex-count-function-reference-type-error-in-verification-context.md, destination=.issues/completed/P0-BUG-745-mesh-vertex-count-function-reference-type-error-in-verification-context.md

[23:16:28] Committed: 6609519b
[23:16:28] Closed BUG-745: Closed - Invalid
```

## Current Behavior

1. Issue BUG-745 is processed and closed as "Invalid" (reason: invalid_ref)
2. System attempts to move issue file to `completed/` using `git mv`
3. `git mv` fails with "fatal: not under version control"
4. The commit proceeds anyway (6609519b)
5. Issue file state is potentially inconsistent (not moved, not tracked)

## Expected Behavior

Before attempting `git mv`:
1. Check if source file exists and is under version control
2. If source is not tracked, add it to git first (`git add`) OR copy file directly then remove source
3. Ensure consistent state regardless of git tracking status

## Root Cause Analysis

This is distinct from BUG-009 (destination exists). The error "not under version control" suggests:
- Source file was created but never added to git
- Source file was removed from git index but exists on disk
- Issue file creation process didn't ensure git tracking

For invalid closures, the issue file may have been created but not properly tracked.

## Affected Components

- **Tool**: ll-parallel
- **Likely Module**: `scripts/little_loops/issue_lifecycle.py` (file movement logic)

## Proposed Investigation

1. Review issue file creation process to ensure git tracking
2. Check if "Invalid" closure path has different handling for issue files
3. Add pre-check before `git mv` to handle untracked sources
4. Consider using `git mv --force` or handle with copy+rm

## Impact

- **Severity**: Medium (P2)
- **Frequency**: 1 occurrence in single run
- **Data Risk**: Medium - issue files may not be properly tracked in git

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-14
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_lifecycle.py`: Added `_is_git_tracked()` helper function to check if a file is under git version control
- `scripts/little_loops/issue_lifecycle.py`: Modified `_move_issue_to_completed()` to check source tracking before attempting `git mv`
- `scripts/little_loops/issue_lifecycle.py`: If source is tracked, use `git mv` for history preservation
- `scripts/little_loops/issue_lifecycle.py`: If source is not tracked, use manual copy+delete directly (skip `git mv` attempt)
- `scripts/tests/test_issue_lifecycle.py`: Added `test_untracked_source_skips_git_mv()` test case
- `scripts/tests/test_issue_lifecycle.py`: Added `test_tracked_source_uses_git_mv()` test case
- `scripts/tests/test_issue_lifecycle.py`: Updated existing tests to handle `git ls-files` calls

### Verification Results
- Tests: PASS (39/39 tests in test_issue_lifecycle.py, 1128/1128 total tests)
- Lint: PASS
- Types: PASS

---

## Status
**Completed** | Created: 2026-01-14 | Priority: P2
