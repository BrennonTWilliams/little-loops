---
id: ENH-1423
type: ENH
priority: P2
status: open
parent_issue: ENH-1419
---

# ENH-1423: Decouple Issue Status — ll-sync

## Summary

Update `ll-sync` (`GitHubSyncManager`) to scan type dirs and use `IssueInfo.status` frontmatter for open/closed mapping instead of directory location. Depends on ENH-1417. Can run in parallel with ENH-1422, ENH-1424, ENH-1425, ENH-1426 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

## Motivation

`GitHubSyncManager` currently globs `get_completed_dir()` to determine which issues are closed on GitHub. Removing this directory coupling allows issues to live in type-scoped directories and still sync correctly by reading `status: done` from frontmatter.

## Proposed Solution

### `sync.py` — `GitHubSyncManager`

- `_get_local_issues()` (lines 264–284): scan all type dirs (bugs/, features/, enhancements/); use `IssueInfo.status` to map to GitHub open/closed instead of directory check
- `close_issues()` (lines 926–931): replace `get_completed_dir().glob()` with a scan of type dirs filtering for `status: done`
- `reopen_issues()` (line 1079): replace `issue_path.parent == completed_dir` check with `IssueInfo.status != "done"` (or equivalent)
- `_find_local_issue()` (lines 741–761): replace re-glob of `get_completed_dir()` with type-dir-only search using `IssueInfo.status`

## Implementation Steps

1. Update `scripts/little_loops/sync.py:GitHubSyncManager._get_local_issues()` — scan type dirs; map `IssueInfo.status` to open/closed
2. Update `scripts/little_loops/sync.py:close_issues()` — replace `get_completed_dir().glob()` with status-field scan
3. Update `scripts/little_loops/sync.py:reopen_issues()` — replace directory parent check with status field check
4. Update `scripts/little_loops/sync.py:_find_local_issue()` — type-dir-only search
5. Update `scripts/tests/test_cli_sync.py` — add `status: done` frontmatter to completed issue fixtures in `mock_config` setup; remove `completed/` directory creation
6. Update `scripts/tests/test_sync.py` — `GitHubSyncManager` directory-to-remote-state mapping → `IssueInfo.status` field mapping
7. Update `scripts/tests/test_cli.py` — replace hard-coded `"completed_dir": "completed"` config dict entries at lines 293, 480, 1471, 1586, 2370 with `status:` frontmatter in fixture issue files; remove `completed/` directory creation in test setup

## Files to Modify

- `scripts/little_loops/sync.py`
- `scripts/tests/test_cli_sync.py`
- `scripts/tests/test_sync.py`
- `scripts/tests/test_cli.py`

## Acceptance Criteria

- `ll-sync` maps `status: done` → remote closed and `status: open` → remote open without directory checks
- `close_issues --all-completed` scans type dirs for `status: done` instead of `get_completed_dir().glob()`
- `_find_local_issue()` finds issues in type dirs regardless of status
- Zero calls to `get_completed_dir()` or `get_deferred_dir()` remain in `sync.py` after changes
- All updated tests pass

## Integration Map

### Key Anchors

| File | Function | Directory Logic | Line(s) |
|------|----------|-----------------|---------|
| `sync.py` | `_get_local_issues()` | globs active dirs + `get_completed_dir()` | 264–284 |
| `sync.py` | `close_issues()` | globs `get_completed_dir()` when `all_completed=True` | 926–931 |
| `sync.py` | `reopen_issues()` | `issue_path.parent == completed_dir` | 1079 |
| `sync.py` | `_find_local_issue()` | re-globs `get_completed_dir()` unconditionally | 741–761 |

### Breaking Tests

- `scripts/tests/test_cli_sync.py` — `mock_config` fixture calls `(issues_dir / "completed").mkdir(parents=True)`; must add `status: done` frontmatter instead
- `scripts/tests/test_cli.py` — hard-codes `"completed_dir": "completed"` at lines 293, 480, 1471, 1586, 2370; creates `completed/` dirs directly

## Session Log
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
