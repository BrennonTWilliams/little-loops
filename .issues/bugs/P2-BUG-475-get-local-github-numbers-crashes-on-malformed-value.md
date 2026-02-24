---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# BUG-475: `_get_local_github_numbers` crashes on malformed `github_issue` value

## Summary

`GitHubSyncManager._get_local_github_numbers` calls `int(gh_num)` without error handling. If any local issue file has a non-integer `github_issue` frontmatter value, the entire `pull` or `status` operation crashes with an unhandled `ValueError`.

## Location

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 609-617 (at scan commit: 95d4139)
- **Anchor**: `in method GitHubSyncManager._get_local_github_numbers`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/95d4139206f3659159b727db57578ffb2930085b/scripts/little_loops/sync.py#L609-L617)
- **Code**:
```python
def _get_local_github_numbers(self) -> set[int]:
    """Get set of GitHub issue numbers tracked locally."""
    numbers: set[int] = set()
    for issue_path in self._get_local_issues():
        content = issue_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content, coerce_types=True)
        gh_num = frontmatter.get("github_issue")
        if gh_num is not None:
            numbers.add(int(gh_num))     # line 617 — no error handling
    return numbers
```

## Current Behavior

If `github_issue` frontmatter contains a non-integer value (e.g., `"pending"`, `"abc"`, or an empty string), `int(gh_num)` raises `ValueError`. This exception propagates uncaught through `pull_issues` (line 571) and `get_status` (line 714), crashing the entire sync operation.

## Expected Behavior

Malformed `github_issue` values should be logged as warnings and skipped, not crash the entire operation.

## Steps to Reproduce

1. Set `github_issue: tbd` in any local issue's frontmatter
2. Run `ll-sync pull` or `ll-sync status`
3. Observe unhandled `ValueError` crash

## Root Cause

- **File**: `scripts/little_loops/sync.py`
- **Anchor**: `in method _get_local_github_numbers`
- **Cause**: Missing try/except around `int(gh_num)` conversion at line 617

## Proposed Solution

Wrap the conversion in a try/except:

```python
if gh_num is not None:
    try:
        numbers.add(int(gh_num))
    except (ValueError, TypeError):
        logger.warning(f"Malformed github_issue value in {issue_path.name}: {gh_num!r}")
```

## Integration Map

### Files to Modify
- `scripts/little_loops/sync.py` — add error handling in `_get_local_github_numbers`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sync.py` — `pull_issues` and `get_status` call this method

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_sync.py` — add test with malformed `github_issue` frontmatter value

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — Single malformed file crashes all sync operations
- **Effort**: Small — Add try/except wrapper
- **Risk**: Low — Defensive error handling
- **Breaking Change**: No

## Labels

`bug`, `sync`, `error-handling`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P2
