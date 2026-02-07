---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# BUG-234: Issue number collision when pulling from GitHub

## Summary

`GitHubSyncManager._get_next_issue_number()` only scans active issue directories (and completed only if `sync_completed` is True, which defaults to False). This means pulled issues can receive IDs that collide with completed issues.

## Location

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 703-713 (at scan commit: a8f4144)
- **Anchor**: `in method GitHubSyncManager._get_next_issue_number`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/sync.py#L703-L713)
- **Code**:
```python
def _get_next_issue_number(self, issue_type: str) -> int:
    """Get next available issue number for type."""
    max_num = 0
    pattern = re.compile(rf"{issue_type}-(\d+)")

    for issue_path in self._get_local_issues():  # Only scans active + optionally completed
        match = pattern.search(issue_path.name)
        if match:
            max_num = max(max_num, int(match.group(1)))

    return max_num + 1
```

## Current Behavior

With `sync_completed: false` (the default), completed issues are not scanned. If `BUG-042` exists in `completed/` but all active bugs have lower numbers, a new pulled bug could also receive `BUG-042`.

## Expected Behavior

The completed directory should always be scanned for number conflicts, regardless of `sync_completed` setting. Alternatively, use the global `get_next_issue_number` from `issue_parser.py` which already scans all directories.

## Reproduction Steps

1. Have completed issue BUG-042 with no active bugs above 041
2. Run `ll-sync pull` with `sync_completed: false`
3. A new bug is assigned BUG-042, colliding with the completed issue

## Proposed Solution

Always scan the completed directory for number conflicts, or delegate to the existing `get_next_issue_number()` function from `issue_parser.py` which already handles this correctly.

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p2`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-06
- **Status**: Completed

### Changes Made
- `scripts/little_loops/sync.py`: Replaced private `_get_next_issue_number()` with `get_next_issue_number()` from `issue_parser.py`, which always scans all directories including completed
- `scripts/tests/test_sync.py`: Replaced old test with collision-specific test proving completed issues are considered

### Verification Results
- Tests: PASS (2461 passed)
- Lint: PASS
- Types: PASS
