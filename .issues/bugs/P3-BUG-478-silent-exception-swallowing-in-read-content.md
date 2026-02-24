---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# BUG-478: Silent exception swallowing in `IssueParser._read_content`

## Summary

`IssueParser._read_content` catches all exceptions and returns an empty string, causing unreadable issue files to be silently parsed with blank titles, no dependencies, and no product impact. The exception type is discarded entirely — not even logged at debug level.

## Location

- **File**: `scripts/little_loops/issue_parser.py`
- **Line(s)**: 334-338 (at scan commit: 95d4139)
- **Anchor**: `in method IssueParser._read_content`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/95d4139206f3659159b727db57578ffb2930085b/scripts/little_loops/issue_parser.py#L334-L338)
- **Code**:
```python
def _read_content(self, issue_path: Path) -> str:
    try:
        return issue_path.read_text(encoding="utf-8")
    except Exception:
        return ""
```

## Current Behavior

Any exception (PermissionError, encoding error, disk error) is silently swallowed. The caller `parse_file` proceeds with `content = ""`, resulting in a parsed issue with the filename stem as title, no dependencies, and no blocked-by information. No error is logged.

## Expected Behavior

File read errors should be logged as warnings so users can diagnose why issues appear with missing data. At minimum, the exception type and file path should be logged.

## Steps to Reproduce

1. Create an issue file with `chmod 000` permissions
2. Run any command that calls `find_issues` (e.g., `ll-auto`, `ll-parallel`)
3. Observe the issue is parsed with blank title and no dependencies, with no error output

## Proposed Solution

Log the exception at warning level before returning the empty string:

```python
def _read_content(self, issue_path: Path) -> str:
    try:
        return issue_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read {issue_path.name}: {e}")
        return ""
```

## Implementation Steps

1. Add `logger.warning` call to `_read_content` except block with file path and exception
2. Add test with unreadable file to verify warning is logged

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — add logging to `_read_content` except block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — `parse_file` calls `_read_content`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` — add test with unreadable file to verify warning is logged

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Silent data loss makes debugging difficult
- **Effort**: Small — Add single logging line
- **Risk**: Low — Additive change, no behavior change on happy path
- **Breaking Change**: No

## Labels

`bug`, `error-handling`, `logging`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
