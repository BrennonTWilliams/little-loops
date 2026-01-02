# little-loops

Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing.

## Overview

little-loops is a Claude Code plugin that provides a complete development workflow toolkit. It includes:

- **30+ slash commands** for development workflows
- **4 specialized agents** for codebase analysis
- **Automation scripts** for autonomous issue processing
- **Configuration system** for project customization

## Installation

```bash
# From plugin marketplace (when available)
claude plugin install little-loops

# From git repository
claude plugin install https://github.com/little-loops/little-loops
```

## Quick Start

1. **Create a configuration file** (optional):

```bash
mkdir -p .claude
cat > .claude/ll-config.json << 'EOF'
{
  "$schema": "https://raw.githubusercontent.com/little-loops/little-loops/main/config-schema.json",
  "project": {
    "name": "my-project",
    "src_dir": "src/",
    "test_cmd": "pytest tests/",
    "lint_cmd": "ruff check src/"
  }
}
EOF
```

2. **Use commands**:

```bash
# Check code quality
/ll:check_code all

# Run tests
/ll:run_tests unit

# Manage issues
/ll:manage_issue bug fix BUG-001
```

3. **Run automation** (requires Python package):

```bash
# Install CLI tools
pip install ./little-loops/scripts

# Process issues automatically
ll-auto --max-issues 5
```

## Configuration

little-loops uses `.claude/ll-config.json` for project-specific settings. All settings have sensible defaults.

### Full Configuration Example

```json
{
  "$schema": "https://raw.githubusercontent.com/little-loops/little-loops/main/config-schema.json",

  "project": {
    "name": "my-project",
    "src_dir": "src/",
    "test_cmd": "pytest tests/",
    "lint_cmd": "ruff check src/",
    "type_cmd": "mypy src/",
    "format_cmd": "ruff format src/",
    "build_cmd": null
  },

  "issues": {
    "base_dir": ".issues",
    "categories": {
      "bugs": { "prefix": "BUG", "dir": "bugs", "action": "fix" },
      "features": { "prefix": "FEAT", "dir": "features", "action": "implement" },
      "enhancements": { "prefix": "ENH", "dir": "enhancements", "action": "improve" }
    },
    "completed_dir": "completed",
    "priorities": ["P0", "P1", "P2", "P3", "P4", "P5"]
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
    "include_p0": false,
    "stream_subprocess_output": false,
    "command_prefix": "/ll:",
    "ready_command": "ready_issue {{issue_id}}",
    "manage_command": "manage_issue {{issue_type}} {{action}} {{issue_id}}"
  },

  "commands": {
    "pre_implement": null,
    "post_implement": null,
    "custom_verification": []
  },

  "scan": {
    "focus_dirs": ["src/", "tests/"],
    "exclude_patterns": ["**/node_modules/**", "**/__pycache__/**"],
    "custom_agents": []
  }
}
```

### Configuration Sections

#### `project`

Project-level settings for commands:

| Key | Default | Description |
|-----|---------|-------------|
| `name` | Directory name | Project name |
| `src_dir` | `src/` | Source code directory |
| `test_cmd` | `pytest` | Command to run tests |
| `lint_cmd` | `ruff check .` | Command to run linter |
| `type_cmd` | `mypy` | Command for type checking |
| `format_cmd` | `ruff format .` | Command to format code |
| `build_cmd` | `null` | Optional build command |

#### `issues`

Issue management settings:

| Key | Default | Description |
|-----|---------|-------------|
| `base_dir` | `.issues` | Base directory for issues |
| `categories` | See above | Issue category definitions |
| `completed_dir` | `completed` | Where completed issues go |
| `priorities` | `[P0-P5]` | Valid priority prefixes |

#### `automation`

Sequential automation settings (ll-auto):

| Key | Default | Description |
|-----|---------|-------------|
| `timeout_seconds` | `3600` | Per-issue timeout |
| `state_file` | `.auto-manage-state.json` | State persistence |
| `worktree_base` | `.worktrees` | Git worktree directory |
| `max_workers` | `2` | Parallel workers |
| `stream_output` | `true` | Stream subprocess output |

#### `parallel`

Parallel automation settings with git worktree isolation (ll-parallel):

| Key | Default | Description |
|-----|---------|-------------|
| `max_workers` | `2` | Number of parallel workers |
| `p0_sequential` | `true` | Process P0 issues sequentially |
| `worktree_base` | `.worktrees` | Git worktree directory |
| `state_file` | `.parallel-manage-state.json` | State persistence |
| `timeout_per_issue` | `3600` | Per-issue timeout in seconds |
| `max_merge_retries` | `2` | Rebase attempts before failing |
| `include_p0` | `false` | Include P0 in parallel processing |
| `stream_subprocess_output` | `false` | Stream Claude CLI output |
| `command_prefix` | `/ll:` | Prefix for slash commands |
| `ready_command` | `ready_issue {{issue_id}}` | Ready command template |
| `manage_command` | `manage_issue {{issue_type}} {{action}} {{issue_id}}` | Manage command template |

## Commands

### Code Quality

| Command | Description |
|---------|-------------|
| `/ll:check_code [mode]` | Run linting, formatting, type checks |
| `/ll:run_tests [scope]` | Run test suites |
| `/ll:find_dead_code` | Find unused code |

### Issue Management

| Command | Description |
|---------|-------------|
| `/ll:manage_issue <type> <action> [id]` | Full issue lifecycle |
| `/ll:ready_issue [id]` | Validate issue for implementation |
| `/ll:prioritize_issues` | Assign priorities to issues |
| `/ll:verify_issues` | Verify issues against codebase |
| `/ll:scan_codebase` | Find new issues |

### Documentation & Analysis

| Command | Description |
|---------|-------------|
| `/ll:audit_docs [scope]` | Audit documentation |
| `/ll:audit_architecture [focus]` | Analyze architecture |
| `/ll:describe_pr` | Generate PR description |

### Git & Workflow

| Command | Description |
|---------|-------------|
| `/ll:commit` | Create commits with approval |
| `/ll:iterate_plan [path]` | Update existing plans |

## Agents

| Agent | Description |
|-------|-------------|
| `codebase-analyzer` | Analyze implementation details |
| `codebase-locator` | Find files by feature/topic |
| `codebase-pattern-finder` | Find code patterns and examples |
| `web-search-researcher` | Research web information |

## CLI Tools

After installing the Python package:

```bash
pip install ./little-loops/scripts
```

### ll-auto

Sequential issue processing:

```bash
ll-auto                    # Process all issues
ll-auto --max-issues 5     # Limit to 5 issues
ll-auto --resume           # Resume from state
ll-auto --dry-run          # Preview only
ll-auto --category bugs    # Only process bugs
```

### ll-parallel

Parallel issue processing with git worktrees:

```bash
ll-parallel                 # Process with 2 workers
ll-parallel --workers 3     # Use 3 workers
ll-parallel --cleanup       # Clean up worktrees
```

## Command Override

Projects can override plugin commands by placing files in `.claude/commands/br/`.

Override priority:
1. Project `.claude/commands/br/*.md` (highest)
2. Plugin `commands/*.md`
3. Default behavior

### Example Override

To add project-specific verification to `manage_issue`:

```bash
# .claude/commands/br/manage_issue.md
# Copy from plugin and modify as needed
```

## Variable Substitution

Commands use `{{config.*}}` for configuration values:

```markdown
# In command templates
{{config.project.src_dir}}     # -> "src/"
{{config.project.test_cmd}}    # -> "pytest"
{{config.issues.base_dir}}     # -> ".issues"
```

## Project Examples

### Python Project

```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "pytest tests/ -v",
    "lint_cmd": "ruff check src/",
    "type_cmd": "mypy src/"
  }
}
```

### Node.js Project

```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "npm test",
    "lint_cmd": "eslint src/",
    "type_cmd": "tsc --noEmit"
  }
}
```

### Go Project

```json
{
  "project": {
    "src_dir": "./",
    "test_cmd": "go test ./...",
    "lint_cmd": "golangci-lint run",
    "type_cmd": null
  }
}
```

## Migration from Existing Setup

If you have existing `.claude/commands/br/` files:

1. Install little-loops
2. Create `.claude/ll-config.json` with your project settings
3. Keep project-specific commands as overrides
4. Generic commands will now come from the plugin

## Development

### Plugin Structure

```
little-loops/
├── plugin.json           # Plugin manifest
├── config-schema.json    # Configuration schema
├── README.md             # This file
├── commands/             # Slash command templates
├── agents/               # Agent definitions
├── hooks/                # Lifecycle hooks
└── scripts/              # Python CLI tools
    ├── pyproject.toml
    └── little_loops/
        ├── __init__.py
        ├── cli.py
        ├── config.py
        └── ...
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Run tests: `pytest little-loops/scripts/tests/`
5. Submit a pull request

## License

MIT License - See LICENSE file for details.
