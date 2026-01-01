# brentech-toolkit

Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing.

## Overview

brentech-toolkit is a Claude Code plugin that provides a complete development workflow toolkit. It includes:

- **30+ slash commands** for development workflows
- **4 specialized agents** for codebase analysis
- **Automation scripts** for autonomous issue processing
- **Configuration system** for project customization

## Installation

```bash
# From plugin marketplace (when available)
claude plugin install brentech-toolkit

# From git repository
claude plugin install https://github.com/brentech/brentech-toolkit
```

## Quick Start

1. **Create a configuration file** (optional):

```bash
mkdir -p .claude
cat > .claude/br-config.json << 'EOF'
{
  "$schema": "brentech-toolkit://config-schema.json",
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
/br:check_code all

# Run tests
/br:run_tests unit

# Manage issues
/br:manage_issue bug fix BUG-001
```

3. **Run automation** (requires Python package):

```bash
# Install CLI tools
pip install ./brentech-toolkit/scripts

# Process issues automatically
br-auto --max-issues 5
```

## Configuration

brentech-toolkit uses `.claude/br-config.json` for project-specific settings. All settings have sensible defaults.

### Full Configuration Example

```json
{
  "$schema": "brentech-toolkit://config-schema.json",

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

Automation script settings:

| Key | Default | Description |
|-----|---------|-------------|
| `timeout_seconds` | `3600` | Per-issue timeout |
| `state_file` | `.auto-manage-state.json` | State persistence |
| `max_workers` | `2` | Parallel workers |
| `stream_output` | `true` | Stream subprocess output |

## Commands

### Code Quality

| Command | Description |
|---------|-------------|
| `/br:check_code [mode]` | Run linting, formatting, type checks |
| `/br:run_tests [scope]` | Run test suites |
| `/br:find_dead_code` | Find unused code |

### Issue Management

| Command | Description |
|---------|-------------|
| `/br:manage_issue <type> <action> [id]` | Full issue lifecycle |
| `/br:ready_issue [id]` | Validate issue for implementation |
| `/br:prioritize_issues` | Assign priorities to issues |
| `/br:verify_issues` | Verify issues against codebase |
| `/br:scan_codebase` | Find new issues |

### Documentation & Analysis

| Command | Description |
|---------|-------------|
| `/br:audit_docs [scope]` | Audit documentation |
| `/br:audit_architecture [focus]` | Analyze architecture |
| `/br:describe_pr` | Generate PR description |

### Git & Workflow

| Command | Description |
|---------|-------------|
| `/br:commit` | Create commits with approval |
| `/br:iterate_plan [path]` | Update existing plans |

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
pip install ./brentech-toolkit/scripts
```

### br-auto

Sequential issue processing:

```bash
br-auto                    # Process all issues
br-auto --max-issues 5     # Limit to 5 issues
br-auto --resume           # Resume from state
br-auto --dry-run          # Preview only
br-auto --category bugs    # Only process bugs
```

### br-parallel

Parallel issue processing with git worktrees:

```bash
br-parallel                 # Process with 2 workers
br-parallel --workers 3     # Use 3 workers
br-parallel --cleanup       # Clean up worktrees
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

1. Install brentech-toolkit
2. Create `.claude/br-config.json` with your project settings
3. Keep project-specific commands as overrides
4. Generic commands will now come from the plugin

## Development

### Plugin Structure

```
brentech-toolkit/
├── plugin.json           # Plugin manifest
├── config-schema.json    # Configuration schema
├── README.md             # This file
├── commands/             # Slash command templates
├── agents/               # Agent definitions
├── hooks/                # Lifecycle hooks
└── scripts/              # Python CLI tools
    ├── pyproject.toml
    └── brentech_toolkit/
        ├── __init__.py
        ├── cli.py
        ├── config.py
        └── ...
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Run tests: `pytest brentech-toolkit/scripts/tests/`
5. Submit a pull request

## License

MIT License - See LICENSE file for details.
