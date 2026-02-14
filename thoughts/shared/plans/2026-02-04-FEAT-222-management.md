# FEAT-222: Sync Issues with GitHub Issues - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-222-sync-issues-with-github.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The little-loops project currently:
- Maintains issues exclusively as local markdown files in `.issues/`
- Has no integration with external issue tracking systems
- Uses frontmatter in issue files to store metadata like `discovered_date`, `discovered_by`
- Has existing patterns for skills, CLI tools, and configuration

### Key Discoveries
- Skills are defined in `skills/*/SKILL.md` with YAML frontmatter containing `description` and trigger keywords (`skills/capture-issue/SKILL.md:1-6`)
- Configuration uses `config-schema.json` for JSON Schema and `scripts/little_loops/config.py` for dataclasses (`config.py:303-348`)
- Frontmatter parsing is simple regex-based, not YAML library (`issue_parser.py:338-376`)
- CLI entry points are registered in `pyproject.toml:47-54` and implemented in `cli.py`
- Subprocess pattern for external tools uses `subprocess.run()` (`git_operations.py:178-199`)

## Desired End State

A fully functional GitHub Issues sync feature that allows users to:
1. **Push local issues to GitHub**: Create GitHub Issues from local `.issues/` files
2. **Pull GitHub Issues locally**: Create local `.issues/` files from GitHub Issues
3. **Track sync state**: Store GitHub issue number and sync metadata in frontmatter
4. **Configure sync behavior**: Enable/disable via `ll-config.json`

### How to Verify
- Running `/ll:sync-issues push` creates corresponding GitHub Issues
- Running `/ll:sync-issues pull` creates local issue files from GitHub
- Frontmatter includes `github_issue`, `github_url`, `last_synced` fields after sync
- Configuration can enable/disable the feature
- Tests pass for new functionality

## What We're NOT Doing

- **Bidirectional conflict resolution** - Deferred to future enhancement; V1 uses simple "last write wins" or warns
- **Real-time sync** - No webhooks or automatic sync; manual trigger only
- **Label mapping for custom categories** - V1 only handles standard BUG/FEAT/ENH types
- **Comment sync** - Only syncing issue body, not discussion threads
- **Milestone/project board sync** - Out of scope for V1

## Problem Analysis

Users need to share issue tracking with team members who don't use Claude Code CLI. GitHub Issues provides a familiar interface that integrates with PR workflows. The local `.issues/` system is powerful for automation but lacks visibility for non-CLI users.

## Solution Approach

Based on research findings and existing patterns:

1. **Configuration**: Add `sync` section to schema and config module following existing patterns
2. **Skill**: Create `/ll:sync-issues` skill that delegates to a command
3. **Command**: Create `sync_issues.md` command with push/pull/status actions
4. **Python CLI** (optional future): `ll-sync` for automation pipelines
5. **Frontmatter extension**: Add GitHub sync fields to issue files

The implementation uses `gh` CLI for GitHub operations since it handles authentication and provides JSON output. This avoids adding GitHub API dependencies.

## Implementation Phases

### Phase 1: Configuration Schema and Dataclass

#### Overview
Add the `sync` configuration section to enable/disable the feature and configure GitHub settings.

#### Changes Required

**File**: `config-schema.json`
**Changes**: Add `sync` property in the properties object (after `sprints` section, lines 591-592)

```json
    "sync": {
      "type": "object",
      "description": "GitHub Issues synchronization settings (opt-in feature, disabled by default)",
      "properties": {
        "enabled": {
          "type": "boolean",
          "description": "Enable GitHub Issues sync feature",
          "default": false
        },
        "provider": {
          "type": "string",
          "enum": ["github"],
          "description": "Issue tracking provider (currently only GitHub supported)",
          "default": "github"
        },
        "github": {
          "type": "object",
          "description": "GitHub-specific sync settings",
          "properties": {
            "repo": {
              "type": ["string", "null"],
              "description": "GitHub repository (owner/repo format, auto-detected if null)",
              "default": null
            },
            "label_mapping": {
              "type": "object",
              "description": "Map issue types to GitHub labels",
              "additionalProperties": { "type": "string" },
              "default": {
                "BUG": "bug",
                "FEAT": "enhancement",
                "ENH": "enhancement"
              }
            },
            "priority_labels": {
              "type": "boolean",
              "description": "Add priority as GitHub label (e.g., 'P1')",
              "default": true
            },
            "sync_completed": {
              "type": "boolean",
              "description": "Also sync completed issues (close on GitHub)",
              "default": false
            },
            "state_file": {
              "type": "string",
              "description": "File to track sync state",
              "default": ".claude/ll-sync-state.json"
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    }
```

**File**: `scripts/little_loops/config.py`
**Changes**: Add `SyncConfig` dataclass and integrate into `BRConfig`

After `SprintsConfig` class (around line 300), add:

```python
@dataclass
class GitHubSyncConfig:
    """GitHub-specific sync configuration."""

    repo: str | None = None
    label_mapping: dict[str, str] = field(
        default_factory=lambda: {"BUG": "bug", "FEAT": "enhancement", "ENH": "enhancement"}
    )
    priority_labels: bool = True
    sync_completed: bool = False
    state_file: str = ".claude/ll-sync-state.json"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GitHubSyncConfig:
        """Create GitHubSyncConfig from dictionary."""
        return cls(
            repo=data.get("repo"),
            label_mapping=data.get(
                "label_mapping", {"BUG": "bug", "FEAT": "enhancement", "ENH": "enhancement"}
            ),
            priority_labels=data.get("priority_labels", True),
            sync_completed=data.get("sync_completed", False),
            state_file=data.get("state_file", ".claude/ll-sync-state.json"),
        )


@dataclass
class SyncConfig:
    """Issue sync configuration."""

    enabled: bool = False
    provider: str = "github"
    github: GitHubSyncConfig = field(default_factory=GitHubSyncConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SyncConfig:
        """Create SyncConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            provider=data.get("provider", "github"),
            github=GitHubSyncConfig.from_dict(data.get("github", {})),
        )
```

Update `__all__` list to include new classes.

Update `BRConfig._parse_config()` to add:
```python
self._sync = SyncConfig.from_dict(self._raw_config.get("sync", {}))
```

Add property:
```python
@property
def sync(self) -> SyncConfig:
    """Get sync configuration."""
    return self._sync
```

Update `to_dict()` method to include sync config.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_config.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Config schema validates: `python -c "import json; json.load(open('config-schema.json'))"`

**Manual Verification**:
- [ ] Adding `"sync": {"enabled": true}` to ll-config.json loads without error
- [ ] `config.sync.enabled` returns expected boolean value

---

### Phase 2: Skill Definition

#### Overview
Create the `/ll:sync-issues` skill that triggers when users want to sync with GitHub.

#### Changes Required

**File**: `skills/sync-issues/SKILL.md` (new file)
**Changes**: Create skill definition

```markdown
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
/ll:sync-issues [action]
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
| "Sync our issues to GitHub" | `/ll:sync-issues push` |
| "Pull issues from GitHub" | `/ll:sync-issues pull` |
| "What's the sync status?" | `/ll:sync-issues status` |
| "Push BUG-123 to GitHub" | `/ll:sync-issues push BUG-123` |

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
```

#### Success Criteria

**Automated Verification**:
- [ ] Skill file exists: `test -f skills/sync-issues/SKILL.md`
- [ ] Valid YAML frontmatter: `python -c "import yaml; yaml.safe_load(open('skills/sync-issues/SKILL.md').read().split('---')[1])"`

**Manual Verification**:
- [ ] Skill appears in `/ll:help` output
- [ ] Trigger keywords activate the skill

---

### Phase 3: Command Implementation

#### Overview
Create the `/ll:sync-issues` command that performs the actual sync operations.

#### Changes Required

**File**: `commands/sync_issues.md` (new file)
**Changes**: Create command definition

```markdown
---
description: Sync local issues with GitHub Issues (push/pull/status)
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

This command requires sync to be enabled in `{{config.sync.enabled}}`.

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

## Actions

### Push (Local → GitHub)

Push local issues to GitHub Issues.

1. **Find issues to sync**:
   - If `issue_id` provided, find that specific issue
   - Otherwise, find all issues in `.issues/` (bugs, features, enhancements)
   - Skip issues already synced (have `github_issue` in frontmatter) unless content changed

2. **For each issue to push**:

   a. **Read issue content** and parse:
      - Title from `# ISSUE-ID: Title` header
      - Body from markdown content (exclude frontmatter)
      - Type from issue ID prefix (BUG, FEAT, ENH)
      - Priority from filename prefix (P0-P5)

   b. **Determine labels**:
      ```bash
      # Map issue type to GitHub label
      # BUG → bug, FEAT → enhancement, ENH → enhancement
      # Add priority label if configured (e.g., P1)
      ```

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
        --label "{priority_label}" \
        --json number,url

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
   - Skip closed issues unless `sync_completed` is enabled

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
   ```bash
   grep -l "github_issue:" {{config.issues.base_dir}}/*/*.md 2>/dev/null | wc -l
   ```

3. **Count GitHub Issues**:
   ```bash
   gh issue list --json number --jq 'length'
   ```

4. **Report status**:
   ```
   SYNC STATUS
   - Local issues: 15
   - Synced to GitHub: 8
   - GitHub issues: 12
   - Unsynced local: 7
   - GitHub-only: 4
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

## Output Format

```
================================================================================
SYNC {ACTION} COMPLETE
================================================================================

## SUMMARY
- Action: {action}
- Direction: {local_to_github | github_to_local}
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
```

#### Success Criteria

**Automated Verification**:
- [ ] Command file exists: `test -f commands/sync_issues.md`
- [ ] Valid YAML frontmatter in command
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] `/ll:sync-issues status` shows current sync state
- [ ] `/ll:sync-issues push` creates GitHub issues from local files
- [ ] `/ll:sync-issues pull` creates local files from GitHub issues

---

### Phase 4: Tests

#### Overview
Add tests for the new configuration classes.

#### Changes Required

**File**: `scripts/tests/test_config.py`
**Changes**: Add tests for SyncConfig

```python
class TestSyncConfig:
    """Tests for SyncConfig."""

    def test_default_values(self) -> None:
        """Default values when no config provided."""
        config = SyncConfig.from_dict({})
        assert config.enabled is False
        assert config.provider == "github"
        assert config.github.repo is None
        assert config.github.priority_labels is True

    def test_enabled_config(self) -> None:
        """Enabled sync configuration."""
        config = SyncConfig.from_dict({
            "enabled": True,
            "github": {
                "repo": "owner/repo",
                "priority_labels": False,
            }
        })
        assert config.enabled is True
        assert config.github.repo == "owner/repo"
        assert config.github.priority_labels is False

    def test_label_mapping(self) -> None:
        """Custom label mapping."""
        config = SyncConfig.from_dict({
            "github": {
                "label_mapping": {"BUG": "defect", "FEAT": "feature"}
            }
        })
        assert config.github.label_mapping["BUG"] == "defect"
        assert config.github.label_mapping["FEAT"] == "feature"


class TestBRConfigSync:
    """Tests for BRConfig sync integration."""

    def test_sync_property_exists(self, temp_config: BRConfig) -> None:
        """BRConfig has sync property."""
        assert hasattr(temp_config, "sync")
        assert isinstance(temp_config.sync, SyncConfig)

    def test_sync_in_to_dict(self, temp_config: BRConfig) -> None:
        """Sync config included in to_dict output."""
        result = temp_config.to_dict()
        assert "sync" in result
        assert "enabled" in result["sync"]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_config.py -v -k sync`
- [ ] All tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] Test coverage includes new config classes

---

### Phase 5: Documentation Update

#### Overview
Update CLAUDE.md and help command to document the new feature.

#### Changes Required

**File**: `.claude/CLAUDE.md`
**Changes**: Add sync feature to Commands section

In the Commands section, add:
```markdown
- `/ll:sync-issues` - Sync issues with GitHub Issues (requires `sync.enabled`)
```

**File**: `commands/help.md`
**Changes**: Ensure sync_issues appears in help output (automatic from command file)

#### Success Criteria

**Automated Verification**:
- [ ] CLAUDE.md contains sync_issues reference
- [ ] Help command lists sync_issues

**Manual Verification**:
- [ ] `/ll:help` shows sync_issues command with description

---

## Testing Strategy

### Unit Tests
- `SyncConfig.from_dict()` with various inputs
- `GitHubSyncConfig.from_dict()` with defaults and overrides
- `BRConfig.sync` property access
- `BRConfig.to_dict()` includes sync section

### Integration Tests
- Loading config file with sync section enabled
- Config validation against schema

### Manual Testing
- Enable sync in config and verify no errors
- Run `/ll:sync-issues status` to verify gh CLI integration
- Create a test issue and push to GitHub
- Pull an issue from GitHub to verify local file creation

## References

- Original issue: `.issues/features/P3-FEAT-222-sync-issues-with-github.md`
- Similar config pattern: `scripts/little_loops/config.py:285-300` (SprintsConfig)
- Skill pattern: `skills/capture-issue/SKILL.md:1-73`
- Command pattern: `commands/capture_issue.md`
- Frontmatter parsing: `scripts/little_loops/issue_parser.py:338-376`
