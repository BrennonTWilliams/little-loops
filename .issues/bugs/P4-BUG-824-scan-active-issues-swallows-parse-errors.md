---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
---

# BUG-824: `scan_active_issues` swallows all parse errors silently

## Summary

`scan_active_issues` in `parsing.py` catches `Exception` with a bare `pass` when reading and parsing issue files. The issue is still appended to results with `discovered_date=None`, making corrupted files or permission errors invisible to callers — indistinguishable from issues that simply lack a `discovered_date` field.

## Location

- **File**: `scripts/little_loops/issue_history/parsing.py`
- **Line(s)**: 363-370 (at scan commit: 8c6cf90)
- **Anchor**: `in function scan_active_issues`
- **Code**:
```python
try:
    content = file_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    discovered_date = _parse_discovered_date(fm)
except Exception:
    pass
```

## Current Behavior

Any exception (`PermissionError`, `UnicodeDecodeError`, `IsADirectoryError`, or internal errors from `parse_frontmatter`) is silently swallowed. The issue is still appended to results with `discovered_date=None`.

## Expected Behavior

Parse errors should be logged at WARNING level so users can identify and fix corrupted issue files. The issue should still be appended to results (graceful degradation), but the error should be visible.

## Steps to Reproduce

1. Create an issue file with invalid UTF-8 bytes in `.issues/bugs/`
2. Call `scan_active_issues`
3. The file appears in results with `discovered_date=None`, no error logged

## Proposed Solution

Replace `except Exception: pass` with `except Exception as e: logger.warning(f"Failed to parse {file_path}: {e}")`. This preserves the graceful degradation while making errors visible.

## Impact

- **Priority**: P4 - Silent data quality issue; corrupted files go unnoticed
- **Effort**: Small - One-line change to add logging
- **Risk**: Low - Only adds logging, does not change control flow
- **Breaking Change**: No

## Labels

`bug`, `issue-history`, `error-handling`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Session Log
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
