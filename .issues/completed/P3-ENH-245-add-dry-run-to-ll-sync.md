---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-245: Add --dry-run support to ll-sync

## Summary

Unlike `ll-auto`, `ll-parallel`, `ll-sprint`, and `ll-loop` which all support `--dry-run` mode, `ll-sync` has no dry-run capability. Both `push_issues()` and `pull_issues()` immediately create/update GitHub Issues or local files without preview. The `add_dry_run_arg` utility is already available in `cli_args.py` but unused by sync.

## Location

- **File**: `scripts/little_loops/cli.py`
- **Line(s)**: 2108-2190 (at scan commit: a8f4144)
- **Anchor**: `in function main_sync`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/cli.py#L2116-L2190)

## Current Behavior

No dry-run support. Push and pull operations immediately execute against GitHub and local filesystem.

## Expected Behavior

`ll-sync push --dry-run` should show what issues would be pushed without creating GitHub Issues. `ll-sync pull --dry-run` should show what issues would be created locally without writing files.

## Proposed Solution

Add `add_dry_run_arg(parser)` to the sync CLI setup, pass the flag through to `GitHubSyncManager`, and short-circuit actual writes when `dry_run=True`.

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p3`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-06
- **Status**: Completed

### Changes Made
- `scripts/little_loops/sync.py`: Added `dry_run` parameter to `GitHubSyncManager.__init__`, added dry-run guards in `_push_single_issue` and `pull_issues`
- `scripts/little_loops/cli.py`: Added `add_dry_run_arg(parser)` to `main_sync`, pass `dry_run` to manager, display `[DRY RUN]` header
- `scripts/tests/test_sync.py`: Added 6 tests in `TestDryRun` class covering push/pull dry-run behavior

### Verification Results
- Tests: PASS (2483 passed)
- Lint: PASS
- Types: PASS
