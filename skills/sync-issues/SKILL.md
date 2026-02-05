---
description: |
  Sync local .issues/ files with GitHub Issues. Push local issues to GitHub, pull GitHub Issues locally, or check sync status.

  Trigger keywords: "sync issues", "push to github", "pull from github", "github sync", "sync with github", "export issues", "import issues from github"
---

# Sync Issues Skill

This skill handles bidirectional synchronization between local `.issues/` files and GitHub Issues.

## When to Activate

Proactively offer or invoke this skill when the user:
- Wants to share issues with team members via GitHub
- Mentions GitHub Issues or syncing issues
- Wants to export local issues to GitHub
- Wants to import issues from GitHub

## How to Use

When this skill activates, invoke the command:

```
/ll:sync_issues [action]
```

### Actions

| Action | Description |
|--------|-------------|
| `push` | Push local issues to GitHub (create/update) |
| `pull` | Pull GitHub Issues to local files (create/update) |
| `status` | Show sync status without making changes |

### Examples

| User Says | Action |
|-----------|--------|
| "Sync our issues to GitHub" | `/ll:sync_issues push` |
| "Pull issues from GitHub" | `/ll:sync_issues pull` |
| "What's the sync status?" | `/ll:sync_issues status` |
| "Push BUG-123 to GitHub" | `/ll:sync_issues push BUG-123` |

## Prerequisites

1. **Enable sync** in `.claude/ll-config.json`:
   ```json
   {
     "sync": {
       "enabled": true
     }
   }
   ```

2. **GitHub CLI** (`gh`) must be installed and authenticated:
   ```bash
   gh auth status
   ```

## Integration

After syncing:
- Local issues have `github_issue` and `github_url` in frontmatter
- GitHub Issues have labels matching issue type and priority
- Run `/ll:commit` to commit updated frontmatter
