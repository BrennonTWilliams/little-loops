---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-249: Cache _get_local_github_numbers results

## Summary

`GitHubSyncManager._get_local_github_numbers()` reads every local issue file and parses frontmatter on each call. It is called from both `pull_issues()` and `get_status()`, causing redundant I/O. In `get_status()`, the file list is also gathered separately, doubling the work.

## Location

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 616-625 (at scan commit: a8f4144)
- **Anchor**: `in method GitHubSyncManager._get_local_github_numbers`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/sync.py#L616-L625)
- **Code**:
```python
def _get_local_github_numbers(self) -> set[int]:
    numbers: set[int] = set()
    for issue_path in self._get_local_issues():
        content = issue_path.read_text(encoding="utf-8")
        frontmatter = _parse_issue_frontmatter(content)
        gh_num = frontmatter.get("github_issue")
        if gh_num is not None:
            numbers.add(int(gh_num))
    return numbers
```

## Current Behavior

Reads all issue files from disk and parses frontmatter on every call.

## Expected Behavior

Cache results for the duration of a single sync operation, or accept pre-fetched issue files to avoid redundant I/O.

## Proposed Solution

Accept an optional `issue_files` parameter, or cache with a per-operation instance attribute.

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p4`

---

## Status
**Closed (Won't Fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P4

**Closure reason**: Premature optimization. Reads a small directory of files; I/O cost is trivial. Caching adds staleness risk for no user-visible benefit.
