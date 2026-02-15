---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# BUG-422: subprocess.run without timeout in git operations

## Summary

Several `subprocess.run()` calls for git operations in `issue_lifecycle.py` lack timeout parameters. If git hangs (e.g., waiting for GPG passphrase, network issues, lock contention), these calls block indefinitely — particularly problematic in automated/parallel processing.

## Location

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Line(s)**: 269-274, 311-315 (at scan commit: 71616c7)
- **Anchor**: `in functions _cleanup_stale_source() and _move_issue_to_completed()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/71616c711e2fe9f5f1ececcf1c64552bca9d82ec/scripts/little_loops/issue_lifecycle.py#L269-L315)
- **Code**:
```python
subprocess.run(["git", "add", "-A"], capture_output=True, text=True)  # No timeout
subprocess.run(
    ["git", "commit", "-m", f"cleanup: remove stale {issue_id} from bugs/"],
    capture_output=True, text=True,  # No timeout
)

result = subprocess.run(
    ["git", "mv", str(original_path), str(completed_path)],
    capture_output=True, text=True,  # No timeout
)
```

## Current Behavior

Git subprocess calls block indefinitely if git hangs for any reason.

## Expected Behavior

All `subprocess.run()` calls should have a reasonable timeout (e.g., 30 seconds for git operations).

## Steps to Reproduce

1. Configure git to require interactive input (e.g., GPG signing without agent)
2. Trigger issue lifecycle operations (complete/close an issue)
3. Git command hangs waiting for input
4. Worker blocks indefinitely

## Actual Behavior

The automation worker hangs forever waiting for a git subprocess that will never complete.

## Root Cause

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Anchor**: `in functions _cleanup_stale_source() and _move_issue_to_completed()`
- **Cause**: `subprocess.run()` calls lack a `timeout` parameter.

## Proposed Solution

Add timeout to all git subprocess calls:

```python
subprocess.run(
    ["git", "add", "-A"],
    capture_output=True, text=True,
    timeout=30,
)
```

Wrap in try/except `subprocess.TimeoutExpired` for graceful handling.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py`
- `scripts/little_loops/issue_manager.py`

### Similar Patterns
- Check other `subprocess.run(["git"` calls across the codebase

### Tests
- `scripts/tests/test_issue_lifecycle.py`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `timeout=30` to all `subprocess.run()` calls in issue_lifecycle.py
2. Add try/except for `subprocess.TimeoutExpired`
3. Search for similar patterns in other modules

## Impact

- **Priority**: P3 - Affects automation reliability in edge cases
- **Effort**: Small - Adding timeout parameter to a few call sites
- **Risk**: Low - Additive change, no behavior change for normal operation
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `subprocess`, `reliability`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P3
