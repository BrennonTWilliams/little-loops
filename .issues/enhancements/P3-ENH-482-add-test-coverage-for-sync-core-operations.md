---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# ENH-482: Add test coverage for sync.py core sync operations

## Summary

The public API methods of `GitHubSyncManager` (`push_issues`, `pull_issues`, `get_status`) have no test coverage. Tests exist for data classes and individual helpers, but not for the end-to-end sync flows.

## Current Behavior

`test_sync.py` covers `SyncResult`, `SyncStatus`, frontmatter parsing, and individual helper functions (`_parse_issue_title`, `_get_issue_body`, `_check_gh_auth`, `_get_repo_name`, `_extract_issue_id`, `_get_labels_for_issue`). Edge cases like dry-run mode, frontmatter update after create, and the `sync_completed` flag are untested.

## Expected Behavior

Tests exist that mock `_run_gh_command` and verify that:
- `push_issues` creates/updates issues correctly and handles dry-run
- `pull_issues` creates local files from GitHub data and skips existing
- `get_status` assembles counts accurately

## Motivation

The sync module interacts with GitHub and modifies local files. Without tests for the core operations, regressions in the push/pull/status flow go undetected until users encounter them.

## Proposed Solution

Add a `TestGitHubSyncManager` class in `test_sync.py` using `unittest.mock.patch` on `little_loops.sync._run_gh_command` to simulate GitHub API responses for the three public methods.

## Scope Boundaries

- **In scope**: Unit tests for `push_issues`, `pull_issues`, `get_status` with mocked GitHub API
- **Out of scope**: Integration tests against live GitHub, refactoring sync.py internals

## Implementation Steps

1. Add `TestGitHubSyncManager` class to `test_sync.py`
2. Mock `_run_gh_command` to return controlled GitHub API responses
3. Test `push_issues` with new issue, existing issue, and dry-run scenarios
4. Test `pull_issues` with new remote issue, already-local issue, and closed issue
5. Test `get_status` count accuracy

## Integration Map

### Files to Modify
- `scripts/tests/test_sync.py` — add new test class

### Dependent Files (Callers/Importers)
- N/A — test-only change

### Similar Patterns
- Existing mock patterns in `test_sync.py` for helper functions

### Tests
- `scripts/tests/test_sync.py` — new tests

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Important coverage gap for user-facing feature
- **Effort**: Medium — Multiple test scenarios with mocking
- **Risk**: Low — Test-only addition
- **Breaking Change**: No

## Labels

`enhancement`, `testing`, `sync`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
