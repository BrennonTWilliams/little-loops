# ENH-245: Add --dry-run support to ll-sync - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-245-add-dry-run-to-ll-sync.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

`ll-sync` is the only CLI tool without `--dry-run` support. The other four tools (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`) all support it.

### Key Discoveries
- `add_dry_run_arg` is already imported at `cli.py:23` but not used by `main_sync()`
- `GitHubSyncManager.__init__` at `sync.py:275-289` has no `dry_run` parameter
- Push has 3 mutating sites: `gh issue create` (sync.py:458), `gh issue edit` (sync.py:492), `write_text` for frontmatter (sync.py:516)
- Pull has 2 mutating sites: `mkdir` (sync.py:644), `write_text` for local file (sync.py:666)
- `SyncResult` already tracks `created`, `updated`, `skipped` — can be reused to hold "would create/update" info

## Desired End State

- `ll-sync push --dry-run` shows what issues would be pushed (create vs update) without touching GitHub
- `ll-sync pull --dry-run` shows what issues would be created locally without writing files
- `-n` short flag works as alias
- `status` subcommand is unaffected (already read-only)
- Dry-run output uses existing `_print_sync_result()` formatting with a `[DRY RUN]` header

### How to Verify
- `ll-sync push --dry-run` exits 0, shows issues that would be created/updated, no `gh issue create/edit` calls made
- `ll-sync pull --dry-run` exits 0, shows issues that would be pulled, no files written
- All existing tests still pass
- New tests cover dry-run for both push and pull

## What We're NOT Doing

- Not adding dry-run to `status` — it's already read-only
- Not adding a `--dry-run` method like the parallel orchestrator's `_dry_run()` — the sync manager is simpler and benefits from inline guard checks
- Not modifying `_print_sync_result()` format — the existing format shows created/updated/skipped which is exactly what dry-run needs

## Solution Approach

Follow the Pattern A approach (constructor parameter + guard checks), as used by `ll-auto`. This is the most appropriate pattern because:
1. The sync manager has discrete mutating operations that can be individually guarded
2. The data gathering (auth check, repo resolution, local issue scan, GitHub issue list) should still run so the preview is accurate
3. The existing `SyncResult` structure can carry preview information naturally

## Implementation Phases

### Phase 1: Add `dry_run` Parameter to `GitHubSyncManager`

#### Overview
Wire `dry_run` from CLI args through to the sync manager.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add `add_dry_run_arg(parser)` to common args, pass `dry_run` to manager constructor, add dry-run header to output.

At line 2153, after `add_quiet_arg(parser)`:
```python
add_dry_run_arg(parser)
```

At line 2171, pass dry_run:
```python
manager = GitHubSyncManager(config, logger, dry_run=getattr(args, "dry_run", False))
```

At lines 2178-2188, add dry-run prefix to result output:
```python
elif args.action == "push":
    if getattr(args, "dry_run", False):
        logger.info("[DRY RUN] Showing what would be pushed (no changes will be made)")
    issue_ids = args.issue_ids if args.issue_ids else None
    result = manager.push_issues(issue_ids)
    _print_sync_result(result, logger)
    return 0 if result.success else 1

elif args.action == "pull":
    if getattr(args, "dry_run", False):
        logger.info("[DRY RUN] Showing what would be pulled (no changes will be made)")
    labels = args.labels.split(",") if args.labels else None
    result = manager.pull_issues(labels)
    _print_sync_result(result, logger)
    return 0 if result.success else 1
```

**File**: `scripts/little_loops/sync.py`
**Changes**: Add `dry_run` parameter to `__init__`, guard mutating operations.

At `__init__` (line 275-289):
```python
def __init__(
    self,
    config: BRConfig,
    logger: Logger,
    dry_run: bool = False,
) -> None:
    ...
    self.dry_run = dry_run
```

### Phase 2: Guard Push Mutating Operations

#### Overview
In dry-run mode, push should still read issue files and determine what would happen, but skip `gh issue create`, `gh issue edit`, and local frontmatter writes.

#### Changes Required

**File**: `scripts/little_loops/sync.py`

In `_push_single_issue` (line 404), add dry-run logic after determining create vs update:

```python
if self.dry_run:
    if github_number:
        result.updated.append(f"{issue_id} → #{github_number} (would update)")
        self.logger.info(f"Would update GitHub issue #{github_number} for {issue_id}")
    else:
        result.created.append(f"{issue_id} (would create)")
        self.logger.info(f"Would create GitHub issue for {issue_id}")
    return
```

This early return skips `_create_github_issue`, `_update_github_issue`, and `_update_local_frontmatter`.

### Phase 3: Guard Pull Mutating Operations

#### Overview
In dry-run mode, pull should still query GitHub and determine which issues would be created, but skip file writes.

#### Changes Required

**File**: `scripts/little_loops/sync.py`

In `_create_local_issue` (line 611), add dry-run guard before the `write_text` call. The cleanest approach is to guard at the call site in `pull_issues` (line 574):

In `pull_issues`, replace the `_create_local_issue` call block (lines 573-576):

```python
if self.dry_run:
    gh_title = gh_issue.get("title", f"Issue #{gh_number}")
    result.created.append(f"#{gh_number}: {gh_title} (would create as {issue_type})")
    self.logger.info(f"Would create local issue from GitHub #{gh_number}: {gh_title}")
else:
    try:
        self._create_local_issue(gh_issue, issue_type, result)
    except Exception as e:
        result.failed.append((f"#{gh_number}", str(e)))
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sync.py -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

### Phase 4: Add Tests

#### Overview
Add tests for the dry-run behavior in both push and pull paths.

#### Changes Required

**File**: `scripts/tests/test_sync.py`

Add a new test class `TestDryRun` with these tests:

1. `test_push_dry_run_does_not_call_gh_create` — Create manager with `dry_run=True`, push an unsynced issue, assert `_run_gh_command` not called with "issue create"
2. `test_push_dry_run_does_not_call_gh_edit` — Push a synced issue (has github_issue frontmatter), assert `_run_gh_command` not called with "issue edit"
3. `test_push_dry_run_does_not_write_frontmatter` — Assert local file is unchanged after dry-run push
4. `test_push_dry_run_populates_result` — Assert `result.created` and `result.updated` contain preview entries
5. `test_pull_dry_run_does_not_write_files` — Pull with dry_run=True, assert no new files created in issue dirs
6. `test_pull_dry_run_populates_result` — Assert `result.created` contains preview entries

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Dry-run push: no `gh` commands executed, no file writes, result populated
- Dry-run pull: no local files created, result populated
- Constructor: `dry_run` parameter stored correctly
- Default: `dry_run=False` preserves existing behavior

### Integration Tests
- Not needed — existing integration tests cover the non-dry-run paths, and dry-run is a simple guard pattern

## References

- Original issue: `.issues/enhancements/P3-ENH-245-add-dry-run-to-ll-sync.md`
- Pattern reference: `scripts/little_loops/issue_manager.py:687-690` (AutoManager dry-run)
- `add_dry_run_arg` utility: `scripts/little_loops/cli_args.py:14-21`
- Sync manager: `scripts/little_loops/sync.py:272-669`
- CLI entry point: `scripts/little_loops/cli.py:2108-2190`
