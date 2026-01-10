# little-loops

Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing.

## Overview

little-loops is a Claude Code plugin that provides a complete development workflow toolkit. It includes:

- **20 slash commands** for development workflows
- **7 specialized agents** for codebase analysis
- **Automation scripts** for autonomous issue processing
- **Configuration system** for project customization

## Installation

```bash
# Add the marketplace and install
/plugin marketplace add github:BrennonTWilliams/little-loops
/plugin install ll@little-loops
```

## Quick Start

1. **Create a configuration file** (optional):

```bash
mkdir -p .claude
cat > .claude/ll-config.json << 'EOF'
{
  "$schema": "./config-schema.json",
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
  "$schema": "./config-schema.json",

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

Sequential automation settings (`ll-auto`):

| Key | Default | Description |
|-----|---------|-------------|
| `timeout_seconds` | `3600` | Per-issue timeout |
| `state_file` | `.auto-manage-state.json` | State persistence |
| `max_workers` | `2` | Parallel workers |
| `stream_output` | `true` | Stream subprocess output |

#### `parallel`

Parallel automation settings with git worktree isolation (`ll-parallel`):

| Key | Default | Description |
|-----|---------|-------------|
| `max_workers` | `2` | Number of parallel workers (1-8) |
| `p0_sequential` | `true` | Process P0 issues sequentially first |
| `worktree_base` | `.worktrees` | Base directory for git worktrees |
| `state_file` | `.parallel-manage-state.json` | State persistence file |
| `timeout_per_issue` | `3600` | Per-issue timeout in seconds |
| `max_merge_retries` | `2` | Maximum rebase attempts on conflicts |
| `stream_subprocess_output` | `false` | Stream Claude CLI output |
| `command_prefix` | `/ll:` | Prefix for slash commands |
| `ready_command` | `ready_issue {{issue_id}}` | Command template for validation |
| `manage_command` | See below | Command template for processing |

The `manage_command` default is: `manage_issue {{issue_type}} {{action}} {{issue_id}}`

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
| `consistency-checker` | Cross-component consistency validation |
| `plugin-config-auditor` | Plugin configuration auditing |
| `prompt-optimizer` | Codebase context for prompt enhancement |
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

Parallel issue processing with git worktree isolation. Each worker operates in its own worktree, enabling true parallel processing of multiple issues. Changes are merged back to main with automatic conflict resolution.

**How it works:**

1. Discovers issues from `.issues/` directory
2. Groups by priority (P0-P5)
3. Optionally processes P0 issues sequentially first (for critical fixes)
4. Spawns parallel workers, each in its own git worktree
5. Each worker runs `ready_issue` then `manage_issue` commands
6. Merges completed work back to main with rebase strategy
7. Cleans up worktrees when done

**Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview issues without processing |
| `--workers N` | Number of parallel workers (default: 2) |
| `--max-issues N` | Limit total issues to process |
| `--category TYPE` | Filter by category (bugs, features, enhancements) |
| `--include-p0` | Include P0 issues in parallel queue |
| `--stream` | Stream subprocess output to console |
| `--cleanup` | Clean up all worktrees and exit |
| `--resume` | Resume from previous state file |
| `--config PATH` | Use custom config file |

**Examples:**

```bash
ll-parallel                       # Process all issues with 2 workers
ll-parallel --dry-run             # Preview what would be processed
ll-parallel --workers 4           # Use 4 parallel workers
ll-parallel --max-issues 10       # Process at most 10 issues
ll-parallel --category bugs       # Only process bugs
ll-parallel --include-p0          # Include critical P0 issues
ll-parallel --stream              # See Claude CLI output in real-time
ll-parallel --cleanup             # Remove all worktrees
ll-parallel --resume              # Continue from saved state
```

**Priority handling:**

- **P0 issues** are processed sequentially by default (critical fixes shouldn't be parallelized)
- Use `--include-p0` to include them in the parallel queue if needed
- Issues within each priority level are processed in parallel up to worker limit

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

If you have existing `.claude/commands/ll/` files:

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
        ├── cli.py                # CLI entry points (ll-auto, ll-parallel)
        ├── config.py             # Configuration loading
        ├── git_operations.py     # Git operations utilities
        ├── issue_lifecycle.py    # Issue lifecycle management
        ├── issue_manager.py      # Issue management
        ├── issue_parser.py       # Issue discovery and parsing
        ├── issue_discovery.py    # Issue discovery and deduplication
        ├── logger.py             # Logging utilities
        ├── state.py              # State management
        ├── subprocess_utils.py   # Subprocess execution utilities
        ├── work_verification.py  # Work verification utilities
        └── parallel/             # Parallel processing module
            ├── __init__.py
            ├── types.py              # Data types and enums
            ├── priority_queue.py     # Priority-based issue queue
            ├── worker_pool.py        # Worker pool management
            ├── merge_coordinator.py  # Git merge coordination
            ├── orchestrator.py       # Main orchestrator
            ├── git_lock.py           # Thread-safe git operations
            └── output_parsing.py     # Claude output parsing
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Run tests: `pytest scripts/tests/`
5. Submit a pull request

## License

MIT License - See LICENSE file for details.
