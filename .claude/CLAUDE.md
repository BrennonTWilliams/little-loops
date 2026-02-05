<!-- Last updated: 2026-01-06 -->
# little-loops (ll) - Claude Code Plugin

Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing.

## Project Configuration

- **Plugin manifest**: `plugin.json`
- **Config schema**: `config-schema.json`
- **Project config**: `.claude/ll-config.json` (read this for project-specific settings)
- **Local overrides**: `.claude/ll.local.md` (user-specific, gitignored)
- **Hooks**: `hooks/hooks.json`

### Local Settings Override

Create `.claude/ll.local.md` to override settings for your local environment without modifying shared config:

```markdown
---
project:
  test_cmd: "python -m pytest scripts/tests/ -v --tb=short"
scan:
  focus_dirs: ["scripts/", "my-experimental-dir/"]
---

# Local Settings Notes

Personal development preferences.
```

**Merge behavior**: Nested objects are deep merged, arrays replace (not append), explicit `null` removes a setting.

## Key Directories

```
commands/       # Slash commands (/ll:*)
agents/         # Subagent definitions
skills/         # Skill definitions
hooks/          # Lifecycle hooks and prompts
scripts/        # Python package (little_loops)
templates/      # Project-type config templates
.issues/        # Issue tracking (bugs/, features/, enhancements/, completed/)
thoughts/       # Plans and research documents
docs/           # Architecture, API, troubleshooting
```

## Commands

Run `/ll:help` for full list. Key commands:
- `/ll:manage_issue` - Process issues through full lifecycle
- `/ll:scan_codebase` - Find bugs/enhancements, create issues
- `/ll:sync_issues` - Sync issues with GitHub Issues (requires `sync.enabled`)
- `/ll:check_code` - Run lint/format/type checks
- `/ll:run_tests` - Execute test suite
- `/ll:commit` - Create commits with user approval

## Development

```bash
# Tests
python -m pytest scripts/tests/

# Type checking
python -m mypy scripts/little_loops/

# Linting
ruff check scripts/

# Format
ruff format scripts/
```

## Code Style

- Python 3.11+, type hints required
- PEP 8 with 100 char line limit
- Use dataclasses for data structures
- Docstrings for classes and public methods
- Conventional commits: `type(scope): description`

## Development Preferences

- **Prefer Skills over Agents**: When adding new functionality, create a Skill instead of a new Agent. Skills are simpler, more composable, and can be invoked directly by users or other components. Reserve Agents for complex, autonomous multi-step tasks that require specialized capabilities.

## Issue File Format

Files in `.issues/` follow: `P[0-5]-[TYPE]-[NNN]-description.md`
- Types: `BUG`, `FEAT`, `ENH`
- Priorities: P0 (critical) to P5 (low)

## Important Files

- `CONTRIBUTING.md` - Development setup and guidelines
- `docs/ARCHITECTURE.md` - System design
- `docs/API.md` - Python module reference
- `docs/TROUBLESHOOTING.md` - Common issues

## CLI Tools

The `scripts/` directory contains Python CLI tools:
- `ll-auto` - Automated sequential issue processing
- `ll-parallel` - Parallel issue processing with git worktrees
- `ll-messages` - Extract user messages from Claude Code logs
- `ll-loop` - FSM-based automation loop execution
- `ll-sprint` - Sprint-based issue processing
- `ll-workflows` - Workflow sequence analyzer
- `ll-history` - View completed issue statistics and history

Install: `pip install -e "./scripts[dev]"`
