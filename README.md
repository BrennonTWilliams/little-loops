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
  <a href="https://pypi.org/project/little-loops/">
    <img src="https://img.shields.io/pypi/v/little-loops?style=flat-square&label=PyPI" alt="PyPI Version">
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
/ll:check-code all

# Run tests
/ll:run-tests unit

# Scan for issues
/ll:scan-codebase

# Manage an issue end-to-end (plan, implement, verify, complete)
/ll:manage-issue bug fix BUG-001
```

## What's Included

- **28 commands** covering issue discovery, refinement, planning, code quality, git operations, and automation
- **8 specialized agents** for codebase analysis, pattern finding, and web research
- **19 skills** for history analysis, dependency mapping, product analysis, confidence checks, and more
- **13 CLI tools** (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, etc.) for autonomous and parallel issue processing
- **23 FSM loops** for recurring automation workflows (backlog triage, sprint building, quality checks, and more)
- **Configuration system** with project-type templates for Python, JavaScript, TypeScript, Go, Rust, Java (Maven/Gradle), .NET, and a generic fallback

## Commands

Commands are organized by workflow capability. Skills (marked with `^` in `/ll:help`) are also invoked as `/ll:` commands and are included in the tables below. Run `/ll:help` for the full reference.

### Issue Discovery

| Command | Description |
|---------|-------------|
| `/ll:capture-issue [input]` | Capture issues from conversation or description |
| `/ll:scan-codebase` | Find new issues (technical) |
| `/ll:scan-product` | Find new issues (product-focused) |
| `/ll:audit-architecture [focus]` | Analyze architecture for patterns and improvements |
| `/ll:product-analyzer` | Analyze codebase against product goals for feature gaps |

### Issue Refinement

| Command | Description |
|---------|-------------|
| `/ll:normalize-issues` | Fix invalid issue filenames |
| `/ll:prioritize-issues` | Assign priorities (P0-P5) to issues |
| `/ll:align-issues <category>` | Validate issues against key documents |
| `/ll:format-issue [id]` | Format issue files to align with template v2.0 structure |
| `/ll:refine-issue [id]` | Refine issue with codebase-driven research |
| `/ll:verify-issues` | Verify issues against codebase |
| `/ll:tradeoff-review-issues` | Evaluate issues for utility vs complexity |
| `/ll:ready-issue [id]` | Validate issue for implementation |
| `/ll:issue-workflow` | Quick reference for issue management workflow |
| `/ll:issue-size-review` | Evaluate issue size/complexity and propose decomposition |
| `/ll:map-dependencies` | Analyze cross-issue dependencies based on file overlap |

### Planning & Implementation

| Command | Description |
|---------|-------------|
| `/ll:create-sprint [name] [--issues]` | Create sprint (explicit or auto-suggested) |
| `/ll:review-sprint [name]` | Review sprint health and suggest improvements |
| `/ll:manage-issue <type> <action> [id]` | Full issue lifecycle (plan, implement, verify, complete) |
| `/ll:iterate-plan [path]` | Update existing implementation plans |
| `/ll:confidence-check [id]` | Pre-implementation confidence check for readiness |
| `/ll:go-no-go [id|sprint] [--check]` | Adversarial GO/NO-GO verdict via pro/con debate agents |

### Code Quality

| Command | Description |
|---------|-------------|
| `/ll:check-code [mode]` | Run linting, formatting, type checks |
| `/ll:run-tests [scope]` | Run test suites |
| `/ll:audit-docs [scope] [--fix]` | Audit documentation for accuracy and completeness |
| `/ll:update-docs [--since <date\|ref>] [--fix]` | Identify stale or missing docs from recent commits and completed issues |
| `/ll:find-dead-code` | Find unused code |

### Git & Release

| Command | Description |
|---------|-------------|
| `/ll:commit` | Create commits with approval |
| `/ll:open-pr [target_branch]` | Open pull request for current branch |
| `/ll:describe-pr` | Generate PR description |
| `/ll:manage-release [action] [version]` | Manage releases, tags, and changelogs |
| `/ll:sync-issues [mode]` | Sync local issues with GitHub Issues |
| `/ll:cleanup-worktrees [mode]` | Clean orphaned git worktrees |

### Automation & Loops

| Command | Description |
|---------|-------------|
| `/ll:create-loop` | Interactive FSM loop creation |
| `/ll:review-loop` | Review and improve existing FSM loop configurations |
| `/ll:analyze-loop` | Analyze loop execution history for actionable issues |
| `/ll:loop-suggester [file|--from-commands]` | Suggest FSM loops from message history or command catalog |
| `/ll:workflow-automation-proposer` | Synthesize workflow patterns into automation proposals |

### Meta-Analysis

| Command | Description |
|---------|-------------|
| `/ll:audit-claude-config [scope]` | Audit Claude Code plugin configuration |
| `/ll:analyze-workflows [file]` | Analyze user message patterns for automation |
| `/ll:analyze-history` | Analyze issue history for project health and trends |

### Session & Config

| Command | Description |
|---------|-------------|
| `/ll:init [flags]` | Initialize config for a project (auto-detects type) |
| `/ll:configure [area]` | Interactive configuration editor |
| `/ll:help` | Show available commands and usage |
| `/ll:handoff [context]` | Generate continuation prompt for session handoff |
| `/ll:resume [prompt_file]` | Resume from previous session's continuation prompt |
| `/ll:toggle-autoprompt [setting]` | Toggle automatic prompt optimization |

**Automatic context monitoring**: Enable `context_monitor.enabled` to get warnings when context fills up (~80%). The system will remind you to run `/ll:handoff` before context exhaustion. See [Session Handoff Guide](docs/guides/SESSION_HANDOFF.md) for details.

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

| Skill `^` | Capability Group | Description |
|-----------|-----------------|-------------|
| `capture-issue`^ | Issue Discovery | Capture issues from conversation or description |
| `issue-workflow`^ | Issue Discovery / Refinement | Quick reference for issue management workflow |
| `issue-size-review`^ | Issue Discovery / Refinement | Evaluate issue size/complexity and propose decomposition |
| `format-issue`^ | Issue Refinement | Format issue files to align with template v2.0 structure |
| `map-dependencies`^ | Issue Discovery / Refinement | Analyze cross-issue dependencies based on file overlap |
| `product-analyzer`^ | Scanning & Analysis | Analyze codebase against product goals for feature gaps |
| `confidence-check`^ | Planning & Implementation | Pre-implementation confidence check for readiness validation |
| `manage-issue`^ | Planning & Implementation | Autonomously manage issues — plan, implement, verify, and complete |
| `audit-docs`^ | Code Quality | Audit documentation for accuracy and completeness |
| `update-docs`^ | Code Quality | Identify stale or missing docs from recent commits and completed issues |
| `create-loop`^ | Automation & Loops | Create new FSM loop configuration interactively |
| `review-loop`^ | Automation & Loops | Review and improve existing FSM loop configurations |
| `analyze-loop`^ | Automation & Loops | Analyze loop execution history to synthesize actionable issues from failures |
| `workflow-automation-proposer`^ | Automation & Loops | Synthesize workflow patterns into automation proposals |
| `audit-claude-config`^ | Meta-Analysis | Comprehensive audit of Claude Code plugin configuration |
| `analyze-history`^ | Meta-Analysis | Analyze issue history for project health, trends, and progress |
| `init`^ | Session & Config | Initialize little-loops configuration for a project |
| `configure`^ | Session & Config | Interactively configure specific areas in ll-config.json |
| `go-no-go`^ | Planning & Implementation | Adversarial GO/NO-GO verdict via pro/con debate agents |

## CLI Tools

**Requires Python 3.11+**. Install from PyPI:

```bash
pip install little-loops
```

<details>
<summary>Developer install (editable, with test dependencies)</summary>

```bash
pip install -e "./scripts[dev]"
```

</details>

### ll-auto

Process all backlog issues sequentially in priority order:

```bash
ll-auto                          # Process all issues
ll-auto --max-issues 5           # Limit to 5 issues
ll-auto --resume                 # Resume from state
ll-auto --dry-run                # Preview only
```

Run `ll-auto --help` for all options.

### ll-parallel

Process issues concurrently using isolated git worktrees:

```bash
ll-parallel                      # Process with default workers
ll-parallel --workers 3          # Use 3 parallel workers
ll-parallel --dry-run            # Preview what would be processed
ll-parallel --resume             # Resume from previous state
ll-parallel --cleanup            # Clean up orphaned worktrees and exit
```

Run `ll-parallel --help` for all options.

### ll-loop

FSM-based automation loop execution (create loops with `/ll:create-loop`):

```bash
ll-loop run <loop-name>                   # Execute a loop by name
ll-loop run <loop-name> -b               # Run as background daemon
ll-loop run <loop-name> --show-diagrams  # Show FSM diagram after each step
ll-loop run <loop-name> --clear --show-diagrams  # Live in-place FSM diagram dashboard
ll-loop run <loop-name> --delay 2    # Pause 2s between iterations
ll-loop list                     # List all available loops
ll-loop list --json              # JSON array of available loops
ll-loop stop <loop-name>         # Stop a running loop
ll-loop status <loop-name>       # Show loop status
ll-loop status <loop-name> --json  # Show loop status as JSON
ll-loop resume <loop-name>       # Resume an interrupted loop
ll-loop validate <loop-name>     # Validate loop definition
ll-loop history <loop-name>      # Show loop execution history (lists archived runs)
ll-loop history <loop-name> <run_id>  # Inspect a specific archived run
ll-loop test <loop-name>         # Run a single test iteration
ll-loop simulate <loop-name>     # Trace execution interactively
ll-loop install <loop-name>      # Copy built-in loop to .loops/
ll-loop show <loop-name>         # Show loop details and structure
ll-loop show <loop-name> --json  # Show loop details as JSON
```

Run `ll-loop --help` for all options. See [Loops Guide](docs/guides/LOOPS_GUIDE.md) for loop authoring.

### ll-sprint

Define and execute curated issue sets with dependency-aware ordering:

```bash
ll-sprint create sprint-1 --issues BUG-001,FEAT-010
ll-sprint run sprint-1           # Execute a sprint
ll-sprint list                   # List all sprints
ll-sprint list --json            # JSON array of all sprints
ll-sprint show sprint-1          # Show sprint details
ll-sprint edit sprint-1 --add BUG-045  # Edit sprint issue list
ll-sprint delete sprint-1        # Delete a sprint
ll-sprint analyze sprint-1       # Analyze for file conflicts
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
ll-sync diff [issue_id]          # Show diff between local and GitHub issues
ll-sync close [issue_ids...]     # Close GitHub issues for completed local issues
ll-sync reopen [issue_ids...]    # Reopen GitHub issues for locally-active issues
```

Requires `sync.enabled: true` in config. Run `ll-sync --help` for all options.

### ll-history

View completed issue statistics and generate documentation:

```bash
ll-history summary               # Display issue statistics
ll-history summary --json        # Output as JSON
ll-history analyze               # Full analysis with trends and debt metrics
ll-history export "topic" # Export topic-filtered issue excerpts
ll-history export "sprint" --output docs/arch/sprint.md
```

### ll-workflows

Identify multi-step workflow patterns from user message history:

```bash
ll-workflows analyze --input messages.jsonl --patterns step1.yaml
```

### ll-deps

Cross-issue dependency discovery and validation:

```bash
ll-deps analyze                  # Full analysis with markdown output
ll-deps analyze --graph          # Include ASCII dependency graph
ll-deps validate                 # Validate existing dependency references
ll-deps fix                      # Auto-fix broken refs, stale refs, backlinks
```

### ll-issues

Issue management and visualization utilities:

```bash
ll-issues next-id                             # Next available issue number
ll-issues list                                # List all active issues
ll-issues list --type FEAT --priority P2      # Filter by type and priority
ll-issues list --flat                         # Flat output for scripting
ll-issues list --json                         # JSON output for scripting
ll-issues count                               # Total active issue count
ll-issues count --type BUG                    # Count bugs only
ll-issues count --json                        # JSON with breakdowns
ll-issues search "caching"                    # Search by keyword
ll-issues search --type BUG --priority P0-P2  # Filter bugs by priority range
ll-issues show FEAT-001                       # Show summary card for an issue
ll-issues show FEAT-001 --json                # Show issue as JSON
ll-issues sequence                            # Dependency-ordered implementation sequence
ll-issues sequence --limit 5                  # Show top 5 issues to work on
ll-issues sequence --json                     # JSON output for scripting
ll-issues impact-effort                       # ASCII impact vs effort matrix
ll-issues impact-effort --type FEAT           # Filter matrix to a specific issue type
ll-issues refine-status                       # Refinement depth table sorted by commands touched
ll-issues refine-status --type BUG            # Filter to bugs only
ll-issues refine-status --format json         # JSONL output for scripting
ll-issues append-log <issue_path> <command>   # Append a session log entry to an issue file
```

### ll-gitignore

Suggest and apply `.gitignore` patterns based on untracked files:

```bash
ll-gitignore                  # Show suggestions and apply approved patterns
ll-gitignore --dry-run        # Preview suggestions without modifying .gitignore
```

Run `ll-gitignore --help` for all options.

### ll-verify-docs / ll-check-links

Documentation verification utilities:

```bash
ll-verify-docs                   # Check documented counts match actual
ll-check-links                   # Check markdown for broken links
ll-check-links docs/             # Check specific directory
```

## Configuration

little-loops uses `.claude/ll-config.json` for project-specific settings. Run `/ll:init` to auto-detect your project type and generate a config, or `/ll:configure` for interactive editing. All settings have sensible defaults.

For the full configuration reference — all sections, options, variable substitution, and command overrides — see [Configuration Reference](docs/reference/CONFIGURATION.md).

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
| `ll-auto`/`ll-parallel` not found | Run `pip install little-loops` |
| Worktree errors | Run `ll-parallel --cleanup` then `git worktree prune` |
| Issues not discovered | Check `issues.base_dir` config matches your `.issues/` path |
| Resume not working | Delete state file (`.auto-manage-state.json` or `.parallel-manage-state.json`) |

For detailed solutions, see [Troubleshooting Guide](docs/development/TROUBLESHOOTING.md).

## Documentation

- [**docs.little-loops.ai**](https://docs.little-loops.ai) - Hosted documentation site (searchable, dark mode, mobile-friendly)
- [**Documentation Index**](docs/INDEX.md) - Complete reference for all documentation
- [Configuration Reference](docs/reference/CONFIGURATION.md) - Full config options and examples
- [Command Reference](docs/reference/COMMANDS.md) - All slash commands with usage
- [CLI Reference](docs/reference/CLI.md) - All `ll-` CLI tools with flags and examples
- [Loops Guide](docs/guides/LOOPS_GUIDE.md) - Loop creation, FSM YAML, and practical examples
- [Session Handoff Guide](docs/guides/SESSION_HANDOFF.md) - Context management and session continuation
- [Merge Coordinator Guide](docs/development/MERGE-COORDINATOR.md) - Sophisticated merge coordination for parallel processing
- [Troubleshooting Guide](docs/development/TROUBLESHOOTING.md) - Common issues and solutions
- [Architecture Overview](docs/ARCHITECTURE.md) - System design and diagrams
- [API Reference](docs/reference/API.md) - Python module documentation

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and guidelines.

## License

MIT License
