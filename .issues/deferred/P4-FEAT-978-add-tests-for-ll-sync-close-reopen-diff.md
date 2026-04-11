---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# FEAT-978: Add tests for `ll-sync` close/reopen/diff subcommands

## Summary

The `ll-sync` CLI (`main_sync`) implements `close`, `reopen`, and `diff` subcommands that map to `GitHubSyncManager` methods. The existing test file (`test_cli_sync.py`) covers `status`, `push`, and `pull` but has zero tests for these three subcommands. Adding test coverage ensures the argument wiring and manager method dispatch work correctly.

## Location

- **File**: `scripts/little_loops/cli/sync.py`
- **Line(s)**: 148–175 (at scan commit: 96d74cda)
- **Anchor**: `in function main_sync` — `elif args.action == "close":`, `elif args.action == "reopen":`, `elif args.action == "diff":`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/cli/sync.py#L148-L175)
- **Code**:
```python
elif args.action == "diff":
    result = manager.diff_issue(args.issue_id) if args.issue_id else manager.diff_all()
    ...
elif args.action == "close":
    manager.close_issues(args.issue_ids or [], all_completed=args.all_completed)
    ...
elif args.action == "reopen":
    manager.reopen_issues(args.issue_ids or [], all_reopened=args.all_reopened)
    ...
```

## Current Behavior

`ll-sync close`, `ll-sync reopen`, and `ll-sync diff` have no unit test coverage. The `GitHubSyncManager` method dispatch, argument handling (`--all-completed`, `--all-reopened`, `--issue-id`), and output formatting for these branches are untested.

## Expected Behavior

Tests in `test_cli_sync.py` cover each branch: correct manager method is called, correct arguments are forwarded, and output is produced for success and error cases.

## Motivation

These are user-facing operations that interact with GitHub. Without tests, regressions in argument wiring or method dispatch are not caught by CI. The `push` and `pull` subcommands have test coverage as a model to follow.

## Use Case

A developer runs `ll-sync close --all-completed` to close all resolved issues on GitHub. The test verifies that `GitHubSyncManager.close_issues` is called with `all_completed=True` and that the appropriate output is printed.

## Acceptance Criteria

- [ ] Test for `close` with `--all-completed` flag calls `manager.close_issues([], all_completed=True)`
- [ ] Test for `close` with specific `--issue-ids` calls `manager.close_issues(["ID1", "ID2"], all_completed=False)`
- [ ] Test for `reopen` with `--all-reopened` flag calls `manager.reopen_issues([], all_reopened=True)`
- [ ] Test for `diff` with `--issue-id` calls `manager.diff_issue(issue_id)`
- [ ] Test for `diff` without `--issue-id` calls `manager.diff_all()`
- [ ] All tests mock `GitHubSyncManager` following the pattern in existing `test_cli_sync.py` tests

## Proposed Solution

Follow the existing `test_push_*` and `test_pull_*` test patterns in `test_cli_sync.py`:

```python
def test_close_all_completed(mock_sync_manager):
    with patch("little_loops.cli.sync.GitHubSyncManager", return_value=mock_sync_manager):
        result = runner.invoke(main_sync, ["close", "--all-completed"])
    mock_sync_manager.close_issues.assert_called_once_with([], all_completed=True)
    assert result.exit_code == 0
```

## Integration Map

### Files to Modify
- `scripts/tests/test_cli_sync.py` — add test classes/functions for close, reopen, diff

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sync.py` — the code under test (no changes needed)

### Similar Patterns
- Existing `test_push_*` and `test_pull_*` tests in `test_cli_sync.py` — follow these patterns

### Tests
- `scripts/tests/test_cli_sync.py` — the only file to modify

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Review existing `test_push_*` tests in `test_cli_sync.py` to understand the mock/runner pattern
2. Add `TestSyncClose`, `TestSyncReopen`, `TestSyncDiff` test classes covering the acceptance criteria above
3. Run `python -m pytest scripts/tests/test_cli_sync.py -v` to confirm all pass

## Impact

- **Priority**: P4 — Test coverage gap for user-facing operations; no behavioral change
- **Effort**: Small — Following established test patterns in the same file
- **Risk**: Low — Test-only change
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `testing`, `sync`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4
