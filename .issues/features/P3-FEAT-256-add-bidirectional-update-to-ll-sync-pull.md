---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# FEAT-256: Add bidirectional update to ll-sync pull

## Summary

The `pull_issues()` method only creates new local issues from GitHub. If a GitHub issue that is already tracked locally has been updated (title changed, body edited, labels modified), the pull command silently skips it with "already tracked". The `push_issues()` method supports updating via `_update_github_issue`, but the reverse direction is missing, despite the module docstring claiming "bidirectional sync".

## Location

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 594-596 (at scan commit: a8f4144)
- **Anchor**: `in method GitHubSyncManager.pull_issues, skip already-tracked logic`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/sync.py#L594-L596)
- **Code**:
```python
# Skip if already tracked locally
if gh_number in local_github_numbers:
    result.skipped.append(f"#{gh_number} (already tracked)")
    continue
```

## Current Behavior

`ll-sync pull` is a one-time import operation. Already-tracked issues are silently skipped, even if updated on GitHub.

## Expected Behavior

When a tracked issue has been updated on GitHub, `ll-sync pull` should detect the changes and update the local file accordingly (or offer a `--update` flag to enable this behavior).

## Proposed Solution

Compare GitHub issue `updated_at` timestamp against the local file's `last_synced` frontmatter field. If the GitHub issue is newer, update the local file content. Add a `last_synced` field to frontmatter during push/pull operations.

## Impact

- **Severity**: Medium
- **Effort**: Large
- **Risk**: Medium

## Labels

`feature`, `priority-p3`

---

## Status
**Open** | Created: 2026-02-06T03:41:30Z | Priority: P3
