---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# BUG-690: Too-narrow except clause in `IssueManager.__init__` `gather_all_issue_ids` call

## Summary

The `try/except` around the `gather_all_issue_ids` import and call only catches `AttributeError` and `TypeError`. An `ImportError` (module missing), `OSError` (unreadable path), or any other exception from inside `gather_all_issue_ids` would propagate uncaught, crashing `IssueManager` construction entirely instead of gracefully degrading.

## Location

- **File**: `scripts/little_loops/issue_manager.py`
- **Line(s)**: 723-729 (at scan commit: 3e9beea)
- **Anchor**: `in method IssueManager.__init__()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/3e9beeaf2bbe8608104beb89fbc7e2e2259310d8/scripts/little_loops/issue_manager.py#L723-L729)
- **Code**:
```python
try:
    from little_loops.dependency_mapper import gather_all_issue_ids
    issues_dir = config.project_root / config.issues.base_dir
    all_known_ids = gather_all_issue_ids(issues_dir, config=config)
except (AttributeError, TypeError):
    pass
```

## Current Behavior

Only `AttributeError` and `TypeError` are caught. An `ImportError`, `OSError`, `FileNotFoundError`, or any unexpected exception from `gather_all_issue_ids` will propagate out of `__init__`, preventing `IssueManager` construction.

## Expected Behavior

The except clause should catch `Exception` (or at minimum add `ImportError` and `OSError`) to gracefully degrade when dependency mapping is unavailable, with optional logging of the swallowed exception.

## Steps to Reproduce

1. Corrupt or remove the `dependency_mapper` module
2. Instantiate `IssueManager`
3. `ImportError` crashes the constructor instead of gracefully skipping dependency mapping

## Root Cause

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `in method IssueManager.__init__()`
- **Cause**: The except clause was written to handle specific known failure modes but doesn't account for import failures or filesystem errors.

## Proposed Solution

Broaden the except clause to `except Exception` with a debug-level log:

```python
except Exception:
    # Dependency mapping unavailable — degrade gracefully
    pass
```

## Impact

- **Priority**: P3 - Edge case that mainly affects corrupted installations or unusual filesystem states
- **Effort**: Small - Single line change
- **Risk**: Low - Only broadens exception handling
- **Breaking Change**: No

## Labels

`bug`, `error-handling`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
