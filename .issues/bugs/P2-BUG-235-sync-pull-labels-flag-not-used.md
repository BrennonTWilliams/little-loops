---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# BUG-235: ll-sync pull --labels flag accepted but never used

## Summary

The `ll-sync pull --labels` CLI flag is parsed and passed to `GitHubSyncManager.pull_issues()`, but the `labels` parameter is never actually used to filter GitHub issues during the pull operation.

## Location

- **File**: `scripts/little_loops/cli.py`
- **Line(s)**: 2143-2148, 2184-2185 (at scan commit: a8f4144)
- **Anchor**: `in function main_sync, pull_parser argument`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/cli.py#L2143-L2148)
- **Code**:
```python
# CLI definition
pull_parser.add_argument(
    "--labels", "-l", type=str,
    help="Filter by labels (comma-separated)",
)

# Invocation
labels = args.labels.split(",") if args.labels else None
result = manager.pull_issues(labels)
```

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 553-614 (at scan commit: a8f4144)
- **Anchor**: `in method GitHubSyncManager.pull_issues`
- **Code**:
```python
def pull_issues(self, labels: list[str] | None = None) -> SyncResult:
    # labels parameter accepted but never used in the method body
```

## Current Behavior

Running `ll-sync pull --labels bug` parses the labels but does not actually filter by them. All issues are fetched and the labels argument is ignored.

## Expected Behavior

When `--labels` is provided, only GitHub issues with those labels should be pulled. The `gh issue list` command should include `--label` flags.

## Reproduction Steps

1. Run `ll-sync pull --labels bug`
2. Observe that all issues are pulled, not just those labeled "bug"

## Proposed Solution

Pass the labels to the `gh issue list` command in `pull_issues()`:
```python
cmd = ["gh", "issue", "list", "--json", "...", "--state", "open"]
if labels:
    for label in labels:
        cmd.extend(["--label", label])
```

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p2`

---

## Status
**Open** | Created: 2026-02-06T03:41:30Z | Priority: P2
