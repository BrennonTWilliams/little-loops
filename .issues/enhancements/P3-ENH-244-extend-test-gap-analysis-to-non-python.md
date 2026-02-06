---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-244: Extend test gap analysis to non-Python file types

## Summary

The `_find_test_file()` function in `issue_history.py` only checks Python files, with the comment "Only check Python files for now". Since little-loops can be used with any project type, extending test file discovery to support common patterns for JavaScript, TypeScript, Go, etc. would make test gap analysis useful for non-Python projects.

## Location

- **File**: `scripts/little_loops/issue_history.py`
- **Line(s)**: 1221 (at scan commit: a8f4144)
- **Anchor**: `in function _find_test_file`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/issue_history.py#L1221)
- **Code**:
```python
def _find_test_file(source_path: str) -> str | None:
    if not source_path.endswith(".py"):
        return None  # Only check Python files for now
```

## Current Behavior

Non-Python files are always skipped for test gap analysis.

## Expected Behavior

Support common testing patterns: `*.test.ts`, `*.spec.js`, `*_test.go`, etc.

## Proposed Solution

Add a mapping of file extensions to their common test file patterns and search for each.

## Impact

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low

## Labels

`enhancement`, `priority-p3`

---

## Status
**Open** | Created: 2026-02-06T03:41:30Z | Priority: P3
