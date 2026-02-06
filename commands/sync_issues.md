---
description: |
  Sync local issues with GitHub Issues (push/pull/status).

  Trigger keywords: "sync issues", "push to github", "pull from github", "github sync", "sync with github", "export issues", "import issues from github"
allowed-tools:
  - Bash(gh:*)
  - Bash(git:*)
arguments:
  - name: action
    description: Action to perform (push|pull|status)
    required: true
  - name: issue_id
    description: Specific issue ID to sync (optional, syncs all if omitted)
    required: false
---

# Sync Issues with GitHub

Synchronize local `.issues/` files with GitHub Issues.

## Configuration Check

This command requires sync to be enabled. Check `{{config.sync.enabled}}`.

If not enabled, instruct the user to add to `.claude/ll-config.json`:
```json
{
  "sync": {
    "enabled": true
  }
}
```

## Prerequisites

Verify GitHub CLI is authenticated:
```bash
gh auth status
```

If not authenticated, instruct user to run `gh auth login`.

## Arguments

- **action** (required): `push`, `pull`, or `status`
- **issue_id** (optional): Specific issue ID to sync (e.g., `BUG-123`)

## Actions

### Push (Local → GitHub)

Push local issues to GitHub Issues.

1. **Find issues to sync**:
   - If `issue_id` provided, find that specific issue
   - Otherwise, find all issues in `{{config.issues.base_dir}}` (bugs, features, enhancements)
   - Skip issues already synced (have `github_issue` in frontmatter) unless content changed

2. **For each issue to push**:

   a. **Read issue content** and parse:
      - Title from `# ISSUE-ID: Title` header
      - Body from markdown content (exclude frontmatter)
      - Type from issue ID prefix (BUG, FEAT, ENH)
      - Priority from filename prefix (P0-P5)

   b. **Determine labels** based on config:
      - Map issue type to GitHub label: `{{config.sync.github.label_mapping}}`
      - Add priority label if `{{config.sync.github.priority_labels}}` is true

   c. **Check if already exists on GitHub**:
      ```bash
      # If issue has github_issue in frontmatter, check if it exists
      gh issue view {github_issue} --json number,state 2>/dev/null
      ```

   d. **Create or update**:
      ```bash
      # Create new issue
      gh issue create \
        --title "{ISSUE-ID}: {title}" \
        --body "{body}" \
        --label "{type_label}" \
        --label "{priority_label}"

      # Or update existing
      gh issue edit {github_issue} \
        --title "{ISSUE-ID}: {title}" \
        --body "{body}"
      ```

   e. **Update local frontmatter** with GitHub info:
      ```yaml
      ---
      github_issue: 123
      github_url: https://github.com/owner/repo/issues/123
      last_synced: 2026-02-04T12:00:00Z
      ---
      ```

3. **Report results**:
   ```
   SYNC PUSH COMPLETE
   - Created: 3 issues
   - Updated: 1 issue
   - Skipped: 2 issues (unchanged)
   ```

### Pull (GitHub → Local)

Pull GitHub Issues to local files.

1. **List GitHub Issues**:
   ```bash
   gh issue list --json number,title,body,labels,state,url --limit 100
   ```

2. **Filter issues**:
   - Only issues with recognized labels (bug, enhancement)
   - Skip issues already tracked locally (match by title pattern `{TYPE}-{NUM}:`)
   - Skip closed issues unless `{{config.sync.github.sync_completed}}` is enabled

3. **For each issue to pull**:

   a. **Parse issue data**:
      - Extract issue type from labels (bug → BUG, enhancement → FEAT)
      - Extract priority from labels (P0-P5) or default to P3
      - Parse title to extract local issue ID if present

   b. **Generate local filename**:
      ```
      P{priority}-{TYPE}-{next_number}-{slug}.md
      ```

   c. **Create local file** with frontmatter:
      ```markdown
      ---
      github_issue: 123
      github_url: https://github.com/owner/repo/issues/123
      last_synced: 2026-02-04T12:00:00Z
      discovered_by: github_sync
      ---

      # {TYPE}-{NNN}: {title}

      {body}

      ## Labels

      `{labels}`
      ```

4. **Report results**:
   ```
   SYNC PULL COMPLETE
   - Created: 5 local issues
   - Skipped: 10 issues (already tracked)
   ```

### Status

Show sync status without making changes.

1. **Count local issues**:
   ```bash
   find {{config.issues.base_dir}} -name "*.md" -not -path "*/completed/*" | wc -l
   ```

2. **Count synced issues** (have `github_issue` in frontmatter):
   - Read each issue file and check for `github_issue:` in frontmatter

3. **Count GitHub Issues**:
   ```bash
   gh issue list --json number --jq 'length'
   ```

4. **Report status**:
   ```
   SYNC STATUS
   ================================================================================
   Provider: GitHub
   Repository: {detected from gh repo view}

   Local Issues:     15
   Synced to GitHub: 8
   GitHub Issues:    12

   Unsynced local:   7  (local only, not on GitHub)
   GitHub-only:      4  (on GitHub, not local)
   ================================================================================
   ```

## Frontmatter Fields

After sync, issue files include these frontmatter fields:

| Field | Description |
|-------|-------------|
| `github_issue` | GitHub issue number |
| `github_url` | Full URL to GitHub issue |
| `last_synced` | ISO timestamp of last sync |

## Error Handling

- **gh not installed**: Suggest `brew install gh` or platform-appropriate install
- **gh not authenticated**: Suggest `gh auth login`
- **Rate limiting**: Warn and suggest waiting
- **Permission denied**: Check repo access permissions
- **Sync not enabled**: Show config instructions

## Output Format

```
================================================================================
SYNC {ACTION} COMPLETE
================================================================================

## SUMMARY
- Action: {action}
- Direction: {local_to_github | github_to_local | status_check}
- Issues processed: {count}

## CHANGES
- Created: {count}
- Updated: {count}
- Skipped: {count}

## ISSUES
{for each issue}
- {ISSUE-ID}: {action} → GitHub #{number}
{endfor}

================================================================================
```

## Examples

```bash
# Check sync status
/ll:sync_issues status

# Push all local issues to GitHub
/ll:sync_issues push

# Push a specific issue
/ll:sync_issues push BUG-123

# Pull all GitHub Issues to local
/ll:sync_issues pull
```
