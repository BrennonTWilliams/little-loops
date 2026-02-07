<p align="center">
  <img src="https://raw.githubusercontent.com/BrennonTWilliams/little-loops/main/assets/little-loops.jpeg" alt="Little Loops Logo" width="200">
</p>

<p align="center">
  <a href="https://github.com/BrennonTWilliams/little-loops/releases">
    <img src="https://img.shields.io/github/v/release/BrennonTWilliams/little-loops?display_name=tag&style=flat-square" alt="Version">
  </a>
  <a href="https://github.com/BrennonTWilliams/little-loops/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/BrennonTWilliams/little-loops?style=flat-square" alt="License">
  </a>
  <a href="https://python.org">
    <img src="https://img.shields.io/badge/python-3.11+-blue.svg?style=flat-square&logo=python" alt="Python Version">
  </a>
</p>

# little-loops

Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing.

## Overview

little-loops is a Claude Code plugin that provides a complete development workflow toolkit. It includes:

- **35 slash commands** for development workflows
- **8 specialized agents** for codebase analysis
- **6 skills** for specialized workflows (history analysis, issue size review, issue workflow reference, dependency mapping, product analysis, workflow automation)
- **Automation scripts** for autonomous issue processing
- **Configuration system** for project customization

## Installation

### From GitHub (recommended)

```bash
# Add the GitHub repository as a marketplace
/plugin marketplace add BrennonTWilliams/little-loops

# Install the plugin
/plugin install ll@little-loops
```

### From local path (development)

```bash
# Add the local directory as a marketplace
/plugin marketplace add /path/to/little-loops

# Install the plugin
/plugin install ll@little-loops
```

### Manual configuration

Add to your project's `.claude/settings.local.json`:

```json
{
  "extraKnownMarketplaces": {
    "local": {
      "source": {
        "source": "directory",
        "path": "/path/to/little-loops"
      }
    }
  },
  "enabledPlugins": {
    "ll@local": true
  }
}
```

## Quick Start

1. **Initialize configuration** (recommended):

```bash
# Auto-detect project type and generate config
/ll:init

# Or use interactive wizard for full customization
/ll:init --interactive

# Or accept all defaults without prompts
/ll:init --yes
```

This detects your project type (Python, Node.js, Go, Rust, Java, .NET) and creates `.claude/ll-config.json` with appropriate defaults.

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
# Install CLI tools (use the path to your little-loops installation)
pip install /path/to/little-loops/scripts

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
    "priorities": ["P0", "P1", "P2", "P3", "P4", "P5"],
    "templates_dir": null
  },

  "automation": {
    "timeout_seconds": 3600,
    "state_file": ".auto-manage-state.json",
    "worktree_base": ".worktrees",
    "max_workers": 2,
    "stream_output": true,
    "max_continuations": 3
  },

  "parallel": {
    "max_workers": 2,
    "p0_sequential": true,
    "worktree_base": ".worktrees",
    "state_file": ".parallel-manage-state.json",
    "timeout_per_issue": 7200,
    "max_merge_retries": 2,
    "stream_subprocess_output": false,
    "command_prefix": "/ll:",
    "ready_command": "ready_issue {{issue_id}}",
    "manage_command": "manage_issue {{issue_type}} {{action}} {{issue_id}}",
    "worktree_copy_files": [".claude/settings.local.json", ".env"]
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

  "context_monitor": {
    "enabled": true,
    "auto_handoff_threshold": 80,
    "context_limit_estimate": 150000
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
| `templates_dir` | `null` | Directory for issue templates |

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

#### `automation`

Sequential automation settings (ll-auto):

| Key | Default | Description |
|-----|---------|-------------|
| `timeout_seconds` | `3600` | Per-issue timeout |
| `state_file` | `.auto-manage-state.json` | State persistence |
| `worktree_base` | `.worktrees` | Git worktree directory |
| `max_workers` | `2` | Parallel workers |
| `stream_output` | `true` | Stream subprocess output |
| `max_continuations` | `3` | Max session restarts on context handoff |

#### `parallel`

Parallel automation settings with git worktree isolation (ll-parallel):

| Key | Default | Description |
|-----|---------|-------------|
| `max_workers` | `2` | Number of parallel workers |
| `p0_sequential` | `true` | Process P0 issues sequentially |
| `worktree_base` | `.worktrees` | Git worktree directory |
| `state_file` | `.parallel-manage-state.json` | State persistence |
| `timeout_per_issue` | `7200` | Per-issue timeout in seconds |
| `max_merge_retries` | `2` | Rebase attempts before failing |
| `stream_subprocess_output` | `false` | Stream Claude CLI output |
| `command_prefix` | `/ll:` | Prefix for slash commands |
| `ready_command` | `ready_issue {{issue_id}}` | Ready command template |
| `manage_command` | `manage_issue {{issue_type}} {{action}} {{issue_id}}` | Manage command template |
| `worktree_copy_files` | `[".claude/settings.local.json", ".env"]` | Files to copy to worktrees |

#### `product`

Product analysis configuration for `/ll:scan_product`:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable product-focused issue analysis |
| `goals_file` | `.claude/ll-goals.md` | Path to product goals/vision document |
| `analyze_user_impact` | `true` | Include user impact assessment in issues |
| `analyze_business_value` | `true` | Include business value scoring in issues |

To enable product scanning, set `product.enabled: true` and create a goals file with your product vision, personas, and strategic priorities.

#### `scan`

Codebase scanning configuration:

| Key | Default | Description |
|-----|---------|-------------|
| `focus_dirs` | `["src/"]` | Directories to scan |
| `exclude_patterns` | Standard patterns | Paths to exclude from scanning |

## Commands

### Setup & Help

| Command | Description |
|---------|-------------|
| `/ll:init [flags]` | Initialize config for a project (auto-detects type) |
| `/ll:help` | Show available commands and usage |
| `/ll:configure [area]` | Interactive configuration editor |

**Init flags:**
- `--interactive` - Full guided wizard with prompts for each option
- `--yes` - Accept all defaults without confirmation
- `--force` - Overwrite existing configuration

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
| `/ll:normalize_issues` | Fix invalid issue filenames |
| `/ll:scan_codebase` | Find new issues (technical) |
| `/ll:scan_product` | Find new issues (product-focused) |
| `/ll:capture_issue [input]` | Capture issues from conversation |
| `/ll:refine_issue [id]` | Refine issue files through interactive Q&A |
| `/ll:align_issues <category>` | Validate issues against key documents |
| `/ll:sync_issues [mode]` | Sync local issues with GitHub Issues |
| `/ll:create_sprint [name] [--issues]` | Create sprint (explicit or auto-suggested) |

### Documentation & Analysis

| Command | Description |
|---------|-------------|
| `/ll:audit_docs [scope]` | Audit documentation |
| `/ll:audit_architecture [focus]` | Analyze architecture |
| `/ll:describe_pr` | Generate PR description |
| `/ll:audit_claude_config [scope]` | Audit Claude Code plugin configuration |
| `/ll:analyze-workflows [file]` | Analyze user message patterns for automation |

### Git & Workflow

| Command | Description |
|---------|-------------|
| `/ll:commit` | Create commits with approval |
| `/ll:iterate_plan [path]` | Update existing plans |
| `/ll:cleanup_worktrees [mode]` | Clean orphaned git worktrees |
| `/ll:create_loop` | Interactive FSM loop creation |

### Session Management

| Command | Description |
|---------|-------------|
| `/ll:handoff [context]` | Generate continuation prompt for session handoff |
| `/ll:resume [prompt_file]` | Resume from previous session's continuation prompt |
| `/ll:toggle_autoprompt [setting]` | Toggle automatic prompt optimization |

**Automatic context monitoring**: Enable `context_monitor.enabled` to get warnings when context fills up (~80%). The system will remind you to run `/ll:handoff` before context exhaustion. See [Session Handoff Guide](docs/SESSION_HANDOFF.md) for details.

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
| `workflow-pattern-analyzer` | Analyze workflow patterns and dependencies |

## Skills

Specialized workflows invoked via the Skill tool:

| Skill | Description |
|-------|-------------|
| `analyze-history` | Analyze issue history for project health, trends, and progress |
| `issue-size-review` | Evaluate issue size/complexity and propose decomposition |
| `issue-workflow` | Quick reference for issue management workflow |
| `map-dependencies` | Analyze cross-issue dependencies based on file overlap |
| `product-analyzer` | Analyze codebase against product goals for feature gaps and business value |
| `workflow-automation-proposer` | Synthesize workflow patterns into automation proposals |

## CLI Tools

**Requires Python 3.11+**

After installing the Python package:

```bash
# Use the absolute path to your little-loops installation
pip install /path/to/little-loops/scripts

# Example with home directory
pip install ~/code/little-loops/scripts
```

### ll-auto

Sequential issue processing:

```bash
ll-auto                          # Process all issues
ll-auto --max-issues 5           # Limit to 5 issues
ll-auto --resume                 # Resume from state
ll-auto --dry-run                # Preview only
ll-auto --category bugs          # Only process bugs
ll-auto --only BUG-001,BUG-002   # Process specific issues only
ll-auto --skip BUG-003           # Skip specific issues
ll-auto --config /path/to/repo   # Specify project root
```

### ll-loop

FSM-based automation loop execution (create loops with `/ll:create_loop`):

```bash
ll-loop run <loop-name>          # Execute a loop by name
ll-loop run .loops/fix-types.yaml # Execute with full path
ll-loop test-analyze-fix         # Quick execution shortcut
ll-loop fix-types --max-iterations 5  # Set iteration limit
ll-loop lint-cycle --background   # Run in background
ll-loop run .loops/fix-types.yaml --dry-run  # Preview mode
ll-loop list                     # List all available loops
ll-loop list --running           # List only running loops
ll-loop status <loop-name>       # Check loop status
ll-loop stop <loop-name>         # Stop a running loop
ll-loop resume <loop-name>       # Resume a stopped loop
ll-loop history <loop-name>      # View loop execution history
```

For loop authoring paradigms and examples, see [FSM Loop Guide](docs/generalized-fsm-loop.md).

### ll-parallel

Parallel issue processing with git worktrees:

```bash
ll-parallel                          # Process with default workers
ll-parallel --workers 3              # Use 3 parallel workers
ll-parallel --dry-run                # Preview what would be processed
ll-parallel --resume                 # Resume from previous state
ll-parallel --priority P1,P2         # Only process P1 and P2 issues
ll-parallel --include-p0             # Include P0 in parallel processing
ll-parallel --max-issues 10          # Limit total issues to process
ll-parallel --timeout 7200           # Timeout per issue in seconds
ll-parallel --stream-output          # Stream Claude CLI output in real-time
ll-parallel --show-model             # Display model info on worktree setup
ll-parallel --cleanup                # Clean up worktrees and exit
ll-parallel --only BUG-001,BUG-002   # Process specific issues only
ll-parallel --skip BUG-003           # Skip specific issues
ll-parallel --quiet                  # Suppress progress output
ll-parallel --worktree-base /tmp/wt  # Custom worktree directory
ll-parallel --config /path/to/repo   # Specify project root
```

### ll-messages

Extract user messages from Claude Code session logs:

```bash
ll-messages                          # Last 100 messages to file
ll-messages -n 50                    # Last 50 messages
ll-messages --since 2026-01-01       # Messages since date
ll-messages -o output.jsonl          # Custom output path
ll-messages --stdout                 # Print to terminal instead
ll-messages --exclude-agents         # Exclude agent session files
ll-messages --cwd /path/to/project   # Specify project directory
ll-messages -v                       # Verbose progress output
```

Output is JSONL format with message content and metadata (timestamp, session ID, working directory, git branch).

### ll-history

View completed issue statistics and history:

```bash
ll-history summary                   # Display issue statistics
ll-history summary --json            # Output as JSON for scripting
ll-history summary -d /path/to/.issues  # Custom issues directory
```

Shows total completed issues, date range, velocity (issues/day), and breakdowns by type (BUG/ENH/FEAT) and priority (P0-P5).

### ll-sprint

Manage and execute sprint/sequence definitions:

```bash
ll-sprint create sprint-1 --issues BUG-001,FEAT-010 --description "Q1 fixes"
ll-sprint run sprint-1                # Execute a sprint
ll-sprint run sprint-1 --dry-run      # Preview execution
ll-sprint run sprint-1 --resume       # Resume interrupted sprint
ll-sprint list                        # List all sprints
ll-sprint show sprint-1               # Show sprint details
ll-sprint delete sprint-1             # Delete a sprint
```

### ll-sync

Sync local `.issues/` files with GitHub Issues:

```bash
ll-sync status                        # Show sync status
ll-sync push                          # Push all local issues to GitHub
ll-sync push BUG-123                  # Push specific issue
ll-sync pull                          # Pull GitHub Issues to local
ll-sync pull --labels bug             # Pull filtered by labels
ll-sync --dry-run status              # Preview without changes
```

Requires `sync.enabled: true` in `.claude/ll-config.json`.

### ll-workflows

Workflow sequence analysis (step 2 of the workflow analysis pipeline):

```bash
ll-workflows analyze --input messages.jsonl --patterns step1.yaml
ll-workflows analyze -i messages.jsonl -p patterns.yaml -o output.yaml
```

Identifies multi-step workflows and cross-session patterns using entity-based clustering, time-gap weighted boundaries, and semantic similarity scoring.

### ll-verify-docs

Verify that documented counts (commands, agents, skills) match actual file counts:

```bash
ll-verify-docs                        # Check and show results
ll-verify-docs --json                 # Output as JSON
ll-verify-docs --format markdown      # Markdown report
ll-verify-docs --fix                  # Auto-fix mismatches
```

### ll-check-links

Check markdown documentation for broken links:

```bash
ll-check-links                        # Check all markdown files
ll-check-links docs/                  # Check specific directory
ll-check-links --json                 # Output as JSON
ll-check-links --format markdown      # Markdown report
ll-check-links --ignore 'http://localhost.*'  # Ignore pattern
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

## Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| Config not loading | Run `/ll:init` or check `.claude/ll-config.json` exists |
| Command not found | Verify plugin is enabled in `.claude/settings.local.json` |
| `ll-auto`/`ll-parallel` not found | Run `pip install /path/to/little-loops/scripts` |
| Worktree errors | Run `ll-parallel --cleanup` then `git worktree prune` |
| Issues not discovered | Check `issues.base_dir` config matches your `.issues/` path |
| Resume not working | Delete state file (`.auto-manage-state.json` or `.parallel-manage-state.json`) |

For detailed solutions, see [Troubleshooting Guide](docs/TROUBLESHOOTING.md).

## Documentation

- [**Documentation Index**](docs/INDEX.md) - Complete reference for all documentation
- [Command Reference](docs/COMMANDS.md) - All slash commands with usage
- [FSM Loop Guide](docs/generalized-fsm-loop.md) - Automation loop system and authoring paradigms
- [Session Handoff Guide](docs/SESSION_HANDOFF.md) - Context management and session continuation
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Architecture Overview](docs/ARCHITECTURE.md) - System design and diagrams
- [API Reference](docs/API.md) - Python module documentation

## Development

### Plugin Structure

```
little-loops/
├── .claude-plugin/
│   └── plugin.json       # Plugin manifest
├── config-schema.json    # Configuration schema
├── README.md             # This file
├── commands/             # Slash command templates (35 commands)
├── agents/               # Agent definitions (8 agents)
├── skills/               # Skill definitions (6 skills)
├── hooks/                # Lifecycle hooks and validation scripts
├── loops/                # Built-in FSM loop definitions
│   ├── codebase-scan.yaml
│   ├── issue-readiness-cycle.yaml
│   ├── issue-verification.yaml
│   ├── pre-pr-checks.yaml
│   └── quality-gate.yaml
├── templates/            # Project type config templates
│   ├── python-generic.json
│   ├── javascript.json
│   ├── typescript.json
│   ├── go.json
│   ├── rust.json
│   ├── java-maven.json
│   ├── java-gradle.json
│   ├── dotnet.json
│   └── generic.json
└── scripts/              # Python CLI tools
    ├── pyproject.toml
    └── little_loops/
        ├── __init__.py
        ├── cli.py              # CLI entrypoints
        ├── cli_args.py         # Argument parsing
        ├── config.py           # Configuration loading
        ├── state.py            # State persistence
        ├── logger.py           # Logging utilities
        ├── logo.py             # CLI logo display
        ├── frontmatter.py      # YAML frontmatter parsing
        ├── doc_counts.py       # Documentation count utilities
        ├── link_checker.py     # Link validation
        ├── issue_manager.py    # Sequential automation
        ├── issue_parser.py     # Issue file parsing
        ├── issue_discovery.py  # Issue discovery and deduplication
        ├── issue_lifecycle.py  # Issue lifecycle operations
        ├── issue_history.py    # Issue history and statistics
        ├── git_operations.py   # Git utilities
        ├── work_verification.py # Verification helpers
        ├── subprocess_utils.py # Subprocess handling
        ├── sprint.py           # Sprint planning and execution
        ├── sync.py             # GitHub Issues sync
        ├── goals_parser.py     # Goals file parsing
        ├── dependency_graph.py  # Dependency graph construction
        ├── dependency_mapper.py # Cross-issue dependency discovery
        ├── user_messages.py     # User message extraction
        ├── workflow_sequence_analyzer.py  # Workflow analysis
        ├── fsm/                 # FSM loop execution engine
        │   ├── __init__.py
        │   ├── schema.py
        │   ├── fsm-loop-schema.json
        │   ├── compilers.py
        │   ├── concurrency.py
        │   ├── evaluators.py
        │   ├── executor.py
        │   ├── interpolation.py
        │   ├── validation.py
        │   ├── persistence.py
        │   ├── signal_detector.py
        │   └── handoff_handler.py
        └── parallel/           # Parallel processing
            ├── __init__.py
            ├── orchestrator.py
            ├── worker_pool.py
            ├── merge_coordinator.py
            ├── priority_queue.py
            ├── output_parsing.py
            ├── git_lock.py
            ├── file_hints.py
            ├── overlap_detector.py
            ├── types.py
            └── tasks/          # Task templates for Claude CLI
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Submit a pull request

## License

MIT License
