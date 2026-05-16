---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 86
---

# ENH-825: `pull_issues` hardcoded limit of 100 GitHub issues

## Summary

`GitHubSyncManager.pull_issues` caps the `gh issue list` call at `"100"` (hardcoded string literal). Repositories with more than 100 open issues silently return only the first 100, with no warning. The `get_status` method already uses `"500"` for the same type of call.

## Location

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 520-526 (at scan commit: 8c6cf90)
- **Anchor**: `in method GitHubSyncManager.pull_issues`
- **Code**:
```python
gh_args = [
    "issue",
    "list",
    "--json",
    "number,title,body,labels,state,url",
    "--limit",
    "100",
]
```

## Current Behavior

`pull_issues` fetches at most 100 GitHub issues regardless of repository size. No warning is emitted when the returned count equals the limit.

## Expected Behavior

The limit should be configurable via `SyncConfig` or at minimum match the `"500"` used in `get_status`. A log warning should be emitted when the returned count equals the limit, indicating potential truncation.

## Motivation

Users syncing repositories with 100+ issues will silently miss issues during `ll-sync pull`, leading to incomplete local state. This is particularly problematic for large projects adopting ll-sync for the first time.

## Proposed Solution

1. Add a `pull_limit` field to `SyncConfig` (default 500)
2. Replace the hardcoded `"100"` with `str(self.sync_config.github.pull_limit)`
3. After fetching, emit a warning if `len(issues) >= pull_limit`

## Scope Boundaries

- Out of scope: Pagination (gh handles this internally up to 500)
- Out of scope: Changing `get_status` behavior

## Impact

- **Priority**: P3 - Silent data truncation for repositories with 100+ issues
- **Effort**: Small - One config field + string replacement + warning log
- **Risk**: Low - Increases default limit, additive config change
- **Breaking Change**: No

## Labels

`enhancement`, `sync`

## Status

**Completed** | Created: 2026-03-19 | Priority: P3

## Resolution

Implemented 2026-04-02.

- Added `pull_limit: int = 500` field to `GitHubSyncConfig` in `scripts/little_loops/config/features.py`
- Updated `from_dict` to read `pull_limit` from config dict (default 500)
- Replaced hardcoded `"100"` in `GitHubSyncManager.pull_issues` (`scripts/little_loops/sync.py`) with `str(self.sync_config.github.pull_limit)`
- Added warning log when `len(github_issues) >= pull_limit` indicating potential truncation
- Added 5 new tests covering: default value, config override, limit used in gh call, warning on truncation, no warning below limit


## Verification Notes

- **Verified**: 2026-03-19 — VALID
- File `scripts/little_loops/sync.py` exists; hardcoded `"100"` confirmed at line 526 (within stated range 520-526)
- `get_status` confirmed using `"500"` at line 720, consistent with the inconsistency described
- No code changes since scan commit; all claims accurate

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-03T04:15:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-worker-enh-825-20260402-231009/a3e93dd3-4ef0-4214-8570-b7139444e731.jsonl`
- `/ll:manage-issue` - 2026-04-02T23:10:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-worker-enh-825-20260402-231009/a3e93dd3-4ef0-4214-8570-b7139444e731.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:verify-issues` - 2026-04-01T17:45:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc051ae-f218-443d-ad6a-bad1a1757fb1.jsonl`
- `/ll:verify-issues` - 2026-03-19T22:38:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc051ae-f218-443d-ad6a-bad1a1757fb1.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
- `/ll:ready-issue` - 2026-04-02T23:10:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
