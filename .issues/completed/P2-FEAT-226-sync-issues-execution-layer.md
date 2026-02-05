---
discovered_date: 2026-02-05
discovered_by: investigation
related_issues: [FEAT-222]
---

# FEAT-226: Implement Sync Issues Execution Layer

## Summary

Implement the missing execution layer for the `/ll:sync_issues` command. FEAT-222 established the configuration schema, skill definition, and command specification, but the actual Python code to perform sync operations was never implemented.

## Context

FEAT-222 was marked complete after implementing:
- Configuration schema in `config-schema.json`
- `GitHubSyncConfig` and `SyncConfig` dataclasses in `config.py`
- Skill definition in `skills/sync-issues/SKILL.md`
- Command specification in `commands/sync_issues.md`
- 13 configuration tests

However, the command currently cannot execute any sync operations because there is no Python code to:
- Invoke `gh` CLI commands
- Parse GitHub API responses
- Update issue frontmatter with sync metadata
- Track sync state

When a user runs `/ll:sync_issues push`, the system loads the spec but has no handler to execute it.

## Current Behavior

- `/ll:sync_issues` command exists but cannot perform actual sync operations
- Configuration can be loaded and validated
- No Python module exists to execute push/pull/status actions

## Expected Behavior

After implementation, users should be able to:

1. **Push**: `ll:sync_issues push` creates/updates GitHub Issues from local `.issues/` files
2. **Pull**: `ll:sync_issues pull` creates/updates local `.issues/` files from GitHub Issues
3. **Status**: `ll:sync_issues status` reports sync state overview

## Proposed Solution

### 1. Create `scripts/little_loops/sync.py`

Core sync module with:

```python
class GitHubSyncManager:
    """Manages bidirectional sync between local issues and GitHub Issues."""

    def __init__(self, config: SyncConfig, issues_dir: Path):
        ...

    def push_issues(self, issues: list[Path] | None = None) -> SyncResult:
        """Push local issues to GitHub. Creates new or updates existing."""
        ...

    def pull_issues(self, labels: list[str] | None = None) -> SyncResult:
        """Pull GitHub Issues to local files."""
        ...

    def get_status(self) -> SyncStatus:
        """Return overview of sync state."""
        ...
```

### 2. Implement Push Logic

Per the command spec in `commands/sync_issues.md`:
- Find all issue files in `.issues/` (excluding completed unless `sync_completed: true`)
- Parse each file's frontmatter and content
- Determine GitHub labels from type and priority
- Check if `github_issue` exists in frontmatter:
  - If yes: Update existing issue via `gh issue edit`
  - If no: Create new issue via `gh issue create`
- Update local frontmatter with `github_issue`, `github_url`, `last_synced`

### 3. Implement Pull Logic

Per the command spec:
- List GitHub Issues via `gh issue list --json`
- Filter by configured labels (ll-tracked or type-specific)
- For each GitHub Issue:
  - Check if local file exists (via `github_issue` in frontmatter)
  - If yes: Update local file content
  - If no: Create new local file with appropriate naming

### 4. Implement Status Logic

- Count local issues (total, synced, unsynced)
- Count GitHub Issues with relevant labels
- Report last sync timestamps
- Identify conflicts (local changes since last sync)

### 5. Frontmatter Handling

Extend existing `issue_parser.py` or create utility functions:
- Parse existing frontmatter from issue files
- Merge sync metadata (`github_issue`, `github_url`, `last_synced`)
- Write updated frontmatter back to files

### 6. State File Management

Use `state_file` from config (default: `.claude/sync-state.json`):
- Track sync history per issue
- Store checksums for conflict detection
- Record last successful sync timestamps

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `scripts/little_loops/sync.py` | Create | Core sync implementation |
| `scripts/little_loops/cli.py` | Modify | Add sync command handlers |
| `scripts/tests/test_sync.py` | Create | Comprehensive sync tests |
| `scripts/little_loops/__init__.py` | Modify | Export sync module |

## Test Coverage Required

1. **Unit tests** for `GitHubSyncManager`:
   - Push single issue (new)
   - Push single issue (update existing)
   - Push multiple issues
   - Pull issues from GitHub
   - Status reporting
   - Frontmatter parsing/updating

2. **Integration tests** (mocked `gh` CLI):
   - End-to-end push flow
   - End-to-end pull flow
   - Conflict detection scenarios
   - Error handling (auth failures, network issues)

## Impact

- **Priority**: P2 (completes a user-facing feature that's currently non-functional)
- **Effort**: Medium (clear spec exists, implementation is straightforward)
- **Risk**: Low (uses existing `gh` CLI, well-defined behavior)

## Acceptance Criteria

- [ ] `scripts/little_loops/sync.py` exists with `GitHubSyncManager` class
- [ ] Push operation creates/updates GitHub Issues from local files
- [ ] Pull operation creates/updates local files from GitHub Issues
- [ ] Status operation reports sync overview
- [ ] Frontmatter is updated with sync metadata after push
- [ ] State file tracks sync history
- [ ] Tests cover all three operations with mocked `gh` CLI
- [ ] All existing tests continue to pass

## Labels

`feature`, `sync`, `github-integration`, `execution-layer`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-05
- **Status**: Completed

### Changes Made
- `scripts/little_loops/sync.py`: Created with `GitHubSyncManager` class, `SyncResult`/`SyncStatus` dataclasses, and helper functions for frontmatter parsing/updating and `gh` CLI invocation
- `scripts/little_loops/cli.py`: Added `main_sync()` entry point for `ll-sync` command with status/push/pull subcommands
- `scripts/little_loops/__init__.py`: Exported `GitHubSyncManager`, `SyncResult`, `SyncStatus`
- `scripts/pyproject.toml`: Added `ll-sync` CLI entry point
- `scripts/tests/test_sync.py`: Created 39 comprehensive tests covering dataclasses, frontmatter utilities, GitHub helpers, and GitHubSyncManager

### Verification Results
- Tests: PASS (2455 passed, 4 skipped)
- Lint: PASS
- Types: PASS
