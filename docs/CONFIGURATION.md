# Configuration Reference

little-loops uses `.claude/ll-config.json` for project-specific settings. All settings have sensible defaults. Run `/ll:init` to auto-detect your project type and generate a config file.

For interactive editing, use `/ll:configure`.

## Full Configuration Example

```json
{
  "$schema": "./config-schema.json",

  "project": {
    "name": "my-project",
    "src_dir": "src/",
    "test_dir": "tests",
    "test_cmd": "pytest tests/",
    "lint_cmd": "ruff check src/",
    "type_cmd": "mypy src/",
    "format_cmd": "ruff format src/",
    "build_cmd": null,
    "run_cmd": null
  },

  "issues": {
    "base_dir": ".issues",
    "categories": {
      "bugs": { "prefix": "BUG", "dir": "bugs", "action": "fix" },
      "features": { "prefix": "FEAT", "dir": "features", "action": "implement" },
      "enhancements": { "prefix": "ENH", "dir": "enhancements", "action": "improve" }
    },
    "completed_dir": "completed",
    "priorities": ["P0", "P1", "P2", "P3", "P4", "P5"],
    "templates_dir": null,
    "capture_template": "full",
    "duplicate_detection": {
      "exact_threshold": 0.8,
      "similar_threshold": 0.5
    }
  },

  "automation": {
    "timeout_seconds": 3600,
    "state_file": ".auto-manage-state.json",
    "worktree_base": ".worktrees",
    "max_workers": 2,
    "stream_output": true
  },

  "parallel": {
    "max_workers": 2,
    "p0_sequential": true,
    "worktree_base": ".worktrees",
    "state_file": ".parallel-manage-state.json",
    "timeout_per_issue": 3600,
    "max_merge_retries": 2,
    "stream_subprocess_output": false,
    "command_prefix": "/ll:",
    "ready_command": "ready_issue {{issue_id}}",
    "manage_command": "manage_issue {{issue_type}} {{action}} {{issue_id}}",
    "worktree_copy_files": [".env"]
  },

  "commands": {
    "pre_implement": null,
    "post_implement": null,
    "custom_verification": []
  },

  "scan": {
    "focus_dirs": ["src/", "tests/"],
    "exclude_patterns": ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"],
    "custom_agents": []
  },

  "prompt_optimization": {
    "enabled": true,
    "mode": "quick",
    "confirm": true,
    "bypass_prefix": "*",
    "clarity_threshold": 6
  },

  "continuation": {
    "enabled": true,
    "auto_detect_on_session_start": true,
    "include_todos": true,
    "include_git_status": true,
    "include_recent_files": true,
    "max_continuations": 3,
    "prompt_expiry_hours": 24
  },

  "context_monitor": {
    "enabled": true,
    "auto_handoff_threshold": 80,
    "context_limit_estimate": 150000
  },

  "sprints": {
    "sprints_dir": ".sprints",
    "default_timeout": 3600,
    "default_max_workers": 4
  },

  "sync": {
    "enabled": false,
    "provider": "github",
    "github": {
      "repo": null,
      "label_mapping": {
        "BUG": "bug",
        "FEAT": "enhancement",
        "ENH": "enhancement"
      },
      "priority_labels": true,
      "sync_completed": false,
      "state_file": ".claude/ll-sync-state.json"
    }
  },

  "documents": {
    "enabled": false,
    "categories": {}
  }
}
```

## Configuration Sections

### `project`

Project-level settings for commands:

| Key | Default | Description |
|-----|---------|-------------|
| `name` | Directory name | Project name |
| `src_dir` | `src/` | Source code directory |
| `test_dir` | `tests` | Test directory path |
| `test_cmd` | `pytest` | Command to run tests |
| `lint_cmd` | `ruff check .` | Command to run linter |
| `type_cmd` | `mypy` | Command for type checking |
| `format_cmd` | `ruff format .` | Command to format code |
| `build_cmd` | `null` | Optional build command |
| `run_cmd` | `null` | Optional run/start command (smoke test) |

### `issues`

Issue management settings:

| Key | Default | Description |
|-----|---------|-------------|
| `base_dir` | `.issues` | Base directory for issues |
| `categories` | See above | Issue category definitions |
| `completed_dir` | `completed` | Where completed issues go |
| `priorities` | `[P0-P5]` | Valid priority prefixes |
| `templates_dir` | `null` | Directory for issue templates |
| `capture_template` | `"full"` | Default template style for captured issues (`"full"` or `"minimal"`) |
| `duplicate_detection.exact_threshold` | `0.8` | Jaccard similarity threshold for exact duplicates (0.5-1.0) |
| `duplicate_detection.similar_threshold` | `0.5` | Jaccard similarity threshold for similar issues (0.1-0.9) |

**Custom Categories**: The three core categories (bugs, features, enhancements) are always included automatically. You can add custom categories and they will be merged with the required ones:

```json
{
  "issues": {
    "categories": {
      "documentation": {"prefix": "DOC", "dir": "documentation", "action": "document"},
      "tech-debt": {"prefix": "TECH-DEBT", "dir": "tech-debt", "action": "address"}
    }
  }
}
```

Each category requires a `prefix` (issue ID prefix), and optionally `dir` (subdirectory name, defaults to category key) and `action` (verb for commit messages, defaults to "address").

### `automation`

Sequential automation settings (ll-auto):

| Key | Default | Description |
|-----|---------|-------------|
| `timeout_seconds` | `3600` | Per-issue timeout |
| `state_file` | `.auto-manage-state.json` | State persistence |
| `worktree_base` | `.worktrees` | Git worktree directory |
| `max_workers` | `2` | Parallel workers |
| `stream_output` | `true` | Stream subprocess output |

### `parallel`

Parallel automation settings with git worktree isolation (ll-parallel):

| Key | Default | Description |
|-----|---------|-------------|
| `max_workers` | `2` | Number of parallel workers |
| `p0_sequential` | `true` | Process P0 issues sequentially |
| `worktree_base` | `.worktrees` | Git worktree directory |
| `state_file` | `.parallel-manage-state.json` | State persistence |
| `timeout_per_issue` | `3600` | Per-issue timeout in seconds |
| `max_merge_retries` | `2` | Rebase attempts before failing |
| `stream_subprocess_output` | `false` | Stream Claude CLI output |
| `command_prefix` | `/ll:` | Prefix for slash commands |
| `ready_command` | `ready_issue {{issue_id}}` | Ready command template |
| `manage_command` | `manage_issue {{issue_type}} {{action}} {{issue_id}}` | Manage command template |
| `worktree_copy_files` | `[".env"]` | Files to copy to worktrees (.claude/ is always copied automatically) |

### `product`

Product analysis configuration for `/ll:scan-product`:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable product-focused issue analysis |
| `goals_file` | `.claude/ll-goals.md` | Path to product goals/vision document |
| `analyze_user_impact` | `true` | Include user impact assessment in issues |
| `analyze_business_value` | `true` | Include business value scoring in issues |

To enable product scanning, set `product.enabled: true` and create a goals file with your product vision, personas, and strategic priorities.

### `scan`

Codebase scanning configuration:

| Key | Default | Description |
|-----|---------|-------------|
| `focus_dirs` | `["src/", "tests/"]` | Directories to scan |
| `exclude_patterns` | Standard patterns | Paths to exclude from scanning |

### `prompt_optimization`

Automatic prompt optimization settings (`/ll:toggle-autoprompt`):

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Enable automatic prompt optimization |
| `mode` | `"quick"` | Optimization mode (`"quick"` or `"thorough"`) |
| `confirm` | `true` | Show diff and ask for confirmation before applying |
| `bypass_prefix` | `*` | Prefix to bypass optimization |
| `clarity_threshold` | `6` | Minimum clarity score (1-10) to pass through unchanged |

### `continuation`

Session continuation and handoff settings (`/ll:handoff`, `/ll:resume`):

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Enable continuation prompt features |
| `auto_detect_on_session_start` | `true` | Check for continuation prompt when session starts |
| `include_todos` | `true` | Include todo list state in continuation prompt |
| `include_git_status` | `true` | Include git status in continuation prompt |
| `include_recent_files` | `true` | Include recently modified files in continuation prompt |
| `max_continuations` | `3` | Max automatic session continuations for CLI tools |
| `prompt_expiry_hours` | `24` | Hours before continuation prompt is considered stale |

### `context_monitor`

Context window monitoring for automatic session handoff. See [Session Handoff Guide](SESSION_HANDOFF.md) for full details.

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable context window monitoring |
| `auto_handoff_threshold` | `80` | Context usage percentage to trigger handoff warning |
| `context_limit_estimate` | `150000` | Estimated context window size in tokens |

### `sprints`

Sprint management settings (ll-sprint, `/ll:create-sprint`):

| Key | Default | Description |
|-----|---------|-------------|
| `sprints_dir` | `.sprints` | Directory for sprint definitions |
| `default_timeout` | `3600` | Default timeout per issue in seconds |
| `default_max_workers` | `4` | Worker count for parallel execution within waves (1-8) |

### `sync`

GitHub Issues synchronization for `/ll:sync-issues`:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable GitHub Issues sync feature |
| `provider` | `"github"` | Issue tracking provider (currently only GitHub) |
| `github.repo` | `null` | GitHub repository in owner/repo format (auto-detected if null) |
| `github.label_mapping` | `{"BUG": "bug", ...}` | Map issue types to GitHub labels |
| `github.priority_labels` | `true` | Add priority as GitHub label (e.g., "P1") |
| `github.sync_completed` | `false` | Also sync completed issues (close on GitHub) |
| `github.state_file` | `.claude/ll-sync-state.json` | File to track sync state |

To enable sync, set `sync.enabled: true`. The repository is auto-detected from your git remote; set `sync.github.repo` to override.

### `documents`

Document category tracking for `/ll:align-issues`:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable document category tracking |
| `categories` | `{}` | Document categories with file lists |

To enable document tracking, set `documents.enabled: true` and define categories:

```json
{
  "documents": {
    "enabled": true,
    "categories": {
      "architecture": {
        "description": "System design and technical decisions",
        "files": ["docs/ARCHITECTURE.md", "docs/API.md"]
      }
    }
  }
}
```

Each category requires a `files` array of relative paths. The optional `description` field documents what the category covers.

## Variable Substitution

Commands use `{{config.*}}` for configuration values:

```markdown
# In command templates
{{config.project.src_dir}}     # -> "src/"
{{config.project.test_cmd}}    # -> "pytest"
{{config.issues.base_dir}}     # -> ".issues"
```

## Command Override

Projects can override plugin commands by placing files in `.claude/commands/ll/`.

Override priority:
1. Project `.claude/commands/ll/*.md` (highest)
2. Plugin `commands/*.md`
3. Default behavior

### Example Override

To add project-specific verification to `manage_issue`:

```bash
# .claude/commands/ll/manage_issue.md
# Copy from plugin and modify as needed
```
