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

little-loops turns Claude Code into a full development workflow engine. It adds issue tracking, automated code fixes, sprint planning, and parallel processing — so Claude can manage entire backlogs, not just one-off prompts. Install the plugin, point it at your codebase, and let it discover, plan, implement, and verify changes autonomously.

## Quick Start

### Install

```bash
# Add the GitHub repository as a marketplace
/plugin marketplace add BrennonTWilliams/little-loops

# Install the plugin
/plugin install ll@little-loops
```

<details>
<summary>Alternative install methods</summary>

**From local path (development):**

```bash
/plugin marketplace add /path/to/little-loops
/plugin install ll@little-loops
```

**Manual configuration** — add to `.claude/settings.local.json`:

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

</details>

### First Commands

```bash
# Auto-detect project type and generate config
/ll:init

# Check code quality
/ll:check_code all

# Run tests
/ll:run_tests unit

# Scan for issues
/ll:scan_codebase

# Manage an issue end-to-end (plan, implement, verify, complete)
/ll:manage_issue bug fix BUG-001
```

## What's Included

- **34 slash commands** covering issue discovery, refinement, planning, code quality, git operations, and automation
- **8 specialized agents** for codebase analysis, pattern finding, and web research
- **7 skills** for history analysis, dependency mapping, product analysis, confidence checks, and more
- **11 CLI tools** (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, etc.) for autonomous and parallel issue processing
- **Configuration system** with project-type templates for Python, Node.js, Go, Rust, Java, and .NET

## Commands

Commands are organized by workflow capability. Run `/ll:help` for the full reference.

### Issue Discovery

| Command | Description |
|---------|-------------|
| `/ll:capture_issue [input]` | Capture issues from conversation or description |
| `/ll:scan_codebase` | Find new issues (technical) |
| `/ll:scan_product` | Find new issues (product-focused) |
| `/ll:audit_architecture [focus]` | Analyze architecture for patterns and improvements |

### Issue Refinement

| Command | Description |
|---------|-------------|
| `/ll:normalize_issues` | Fix invalid issue filenames |
| `/ll:prioritize_issues` | Assign priorities (P0-P5) to issues |
| `/ll:align_issues <category>` | Validate issues against key documents |
| `/ll:refine_issue [id]` | Refine issue files through interactive Q&A |
| `/ll:verify_issues` | Verify issues against codebase |
| `/ll:tradeoff_review_issues` | Evaluate issues for utility vs complexity |
| `/ll:ready_issue [id]` | Validate issue for implementation |

### Planning & Implementation

| Command | Description |
|---------|-------------|
| `/ll:create_sprint [name] [--issues]` | Create sprint (explicit or auto-suggested) |
| `/ll:manage_issue <type> <action> [id]` | Full issue lifecycle (plan, implement, verify, complete) |
| `/ll:iterate_plan [path]` | Update existing implementation plans |

### Code Quality

| Command | Description |
|---------|-------------|
| `/ll:check_code [mode]` | Run linting, formatting, type checks |
| `/ll:run_tests [scope]` | Run test suites |
| `/ll:audit_docs [scope]` | Audit documentation for accuracy and completeness |
| `/ll:find_dead_code` | Find unused code |

### Git & Release

| Command | Description |
|---------|-------------|
| `/ll:commit` | Create commits with approval |
| `/ll:open_pr [target_branch]` | Open pull request for current branch |
| `/ll:describe_pr` | Generate PR description |
| `/ll:manage_release [action] [version]` | Manage releases, tags, and changelogs |
| `/ll:sync_issues [mode]` | Sync local issues with GitHub Issues |
| `/ll:cleanup_worktrees [mode]` | Clean orphaned git worktrees |

### Automation & Loops

| Command | Description |
|---------|-------------|
| `/ll:create_loop` | Interactive FSM loop creation |
| `/ll:loop-suggester [file]` | Suggest FSM loops from message history |

### Meta-Analysis

| Command | Description |
|---------|-------------|
| `/ll:audit_claude_config [scope]` | Audit Claude Code plugin configuration |
| `/ll:analyze-workflows [file]` | Analyze user message patterns for automation |

### Session & Config

| Command | Description |
|---------|-------------|
| `/ll:init [flags]` | Initialize config for a project (auto-detects type) |
| `/ll:configure [area]` | Interactive configuration editor |
| `/ll:help` | Show available commands and usage |
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

| Skill | Capability Group | Description |
|-------|-----------------|-------------|
| `issue-workflow` | Issue Discovery / Refinement | Quick reference for issue management workflow |
| `issue-size-review` | Issue Discovery / Refinement | Evaluate issue size/complexity and propose decomposition |
| `map-dependencies` | Issue Discovery / Refinement | Analyze cross-issue dependencies based on file overlap |
| `product-analyzer` | Scanning & Analysis | Analyze codebase against product goals for feature gaps |
| `workflow-automation-proposer` | Automation & Loops | Synthesize workflow patterns into automation proposals |
| `analyze-history` | Meta-Analysis | Analyze issue history for project health, trends, and progress |
| `confidence-check` | Planning & Implementation | Pre-implementation confidence check for readiness validation |

## CLI Tools

**Requires Python 3.11+**. Install with:

```bash
pip install -e /path/to/little-loops/scripts
```

### ll-auto

Sequential issue processing:

```bash
ll-auto                          # Process all issues
ll-auto --max-issues 5           # Limit to 5 issues
ll-auto --resume                 # Resume from state
ll-auto --dry-run                # Preview only
```

Run `ll-auto --help` for all options.

### ll-parallel

Parallel issue processing with git worktree isolation:

```bash
ll-parallel                      # Process with default workers
ll-parallel --workers 3          # Use 3 parallel workers
ll-parallel --dry-run            # Preview what would be processed
ll-parallel --resume             # Resume from previous state
```

Run `ll-parallel --help` for all options.

### ll-loop

FSM-based automation loop execution (create loops with `/ll:create_loop`):

```bash
ll-loop run <loop-name>          # Execute a loop by name
ll-loop list                     # List all available loops
ll-loop stop <loop-name>         # Stop a running loop
```

Run `ll-loop --help` for all options. See [FSM Loop Guide](docs/generalized-fsm-loop.md) for loop authoring.

### ll-sprint

Sprint-based issue processing:

```bash
ll-sprint create sprint-1 --issues BUG-001,FEAT-010
ll-sprint run sprint-1           # Execute a sprint
ll-sprint list                   # List all sprints
```

Run `ll-sprint --help` for all options.

### ll-messages

Extract user messages from Claude Code session logs:

```bash
ll-messages                      # Last 100 messages to file
ll-messages -n 50                # Last 50 messages
ll-messages --since 2026-01-01   # Messages since date
```

Run `ll-messages --help` for all options.

### ll-sync

Sync local `.issues/` files with GitHub Issues:

```bash
ll-sync status                   # Show sync status
ll-sync push                     # Push all local issues to GitHub
ll-sync pull                     # Pull GitHub Issues to local
```

Requires `sync.enabled: true` in config. Run `ll-sync --help` for all options.

### ll-history

View completed issue statistics:

```bash
ll-history summary               # Display issue statistics
ll-history summary --json        # Output as JSON
```

### ll-workflows

Workflow sequence analysis (step 2 of the workflow analysis pipeline):

```bash
ll-workflows analyze --input messages.jsonl --patterns step1.yaml
```

### ll-deps

Cross-issue dependency discovery and validation:

```bash
ll-deps analyze                  # Full analysis with markdown output
ll-deps analyze --graph          # Include ASCII dependency graph
ll-deps validate                 # Validate existing dependency references
```

### ll-verify-docs / ll-check-links

Documentation verification utilities:

```bash
ll-verify-docs                   # Check documented counts match actual
ll-check-links                   # Check markdown for broken links
ll-check-links docs/             # Check specific directory
```

## Configuration

little-loops uses `.claude/ll-config.json` for project-specific settings. Run `/ll:init` to auto-detect your project type and generate a config, or `/ll:configure` for interactive editing. All settings have sensible defaults.

For the full configuration reference — all sections, options, variable substitution, and command overrides — see [Configuration Reference](docs/CONFIGURATION.md).

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

## Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| Config not loading | Run `/ll:init` or check `.claude/ll-config.json` exists |
| Command not found | Verify plugin is enabled in `.claude/settings.local.json` |
| `ll-auto`/`ll-parallel` not found | Run `pip install -e /path/to/little-loops/scripts` |
| Worktree errors | Run `ll-parallel --cleanup` then `git worktree prune` |
| Issues not discovered | Check `issues.base_dir` config matches your `.issues/` path |
| Resume not working | Delete state file (`.auto-manage-state.json` or `.parallel-manage-state.json`) |

For detailed solutions, see [Troubleshooting Guide](docs/TROUBLESHOOTING.md).

## Documentation

- [**Documentation Index**](docs/INDEX.md) - Complete reference for all documentation
- [Configuration Reference](docs/CONFIGURATION.md) - Full config options and examples
- [Command Reference](docs/COMMANDS.md) - All slash commands with usage
- [FSM Loop Guide](docs/generalized-fsm-loop.md) - Automation loop system and authoring paradigms
- [Session Handoff Guide](docs/SESSION_HANDOFF.md) - Context management and session continuation
- [Merge Coordinator Guide](docs/MERGE-COORDINATOR.md) - Sophisticated merge coordination for parallel processing
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Architecture Overview](docs/ARCHITECTURE.md) - System design and diagrams
- [API Reference](docs/API.md) - Python module documentation

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and guidelines.

## License

MIT License
