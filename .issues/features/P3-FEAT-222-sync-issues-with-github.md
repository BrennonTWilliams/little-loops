---
discovered_date: 2026-02-03
discovered_by: capture_issue
---

# FEAT-222: Sync Issues with GitHub Issues

## Summary

Add a `/ll:sync_issues` slash command and corresponding Agent Skill that enables bidirectional synchronization between local `.issues/` files and GitHub Issues. When enabled via configuration, users can push local issues to GitHub and pull GitHub Issues into local files.

## Context

User description: "Sync-Issues feature - if enabled, allows a `/ll:sync_issues` slash command + Agent Skill that push/pulls Issues from our `.issues/` Issue files to/from Github Issues"

This would bridge the gap between the local file-based issue tracking system and GitHub's issue tracking, enabling teams to:
- Share issues with non-CLI users via GitHub's web interface
- Leverage GitHub's notifications and assignment features
- Keep local and remote issue tracking in sync

## Current Behavior

Currently, little-loops maintains issues exclusively as local markdown files in `.issues/`. There is no integration with external issue tracking systems like GitHub Issues.

## Expected Behavior

When enabled, users should be able to:

1. **Push local issues to GitHub**: Create/update GitHub Issues from local `.issues/` files
2. **Pull GitHub Issues locally**: Create/update local `.issues/` files from GitHub Issues
3. **Bidirectional sync**: Detect conflicts and handle merge scenarios
4. **Selective sync**: Choose which issues to sync (by type, priority, label, etc.)

## Proposed Solution

### Configuration

Add to `ll-config.json`:
```json
{
  "sync": {
    "enabled": false,
    "provider": "github",
    "github": {
      "repo": "owner/repo",
      "label_mapping": {
        "BUG": "bug",
        "FEAT": "enhancement",
        "ENH": "enhancement"
      },
      "priority_labels": true,
      "sync_completed": false
    }
  }
}
```

### Components

1. **Skill**: `skills/sync-issues.md` - User-invocable `/ll:sync_issues` command
2. **Agent**: `agents/sync-issues-agent.md` - For complex sync operations
3. **Python CLI**: `scripts/little_loops/ll_sync.py` - Core sync logic using `gh` CLI

### Sync Metadata

Track sync state in issue frontmatter:
```yaml
---
github_issue: 123
github_url: https://github.com/owner/repo/issues/123
last_synced: 2026-02-03T10:30:00Z
sync_hash: abc123
---
```

### Conflict Resolution

- Compare `last_synced` timestamps
- Hash-based change detection
- User prompt for manual conflict resolution

## Impact

- **Priority**: P3 (useful but not blocking core workflows)
- **Effort**: Medium-High (requires careful state management and conflict handling)
- **Risk**: Medium (external API dependency, potential for sync conflicts)

## Related Key Documentation

_No documents linked. Run `/ll:align_issues` to discover relevant docs._

## Labels

`feature`, `captured`, `github-integration`, `sync`

---

## Status

**Open** | Created: 2026-02-03 | Priority: P3
