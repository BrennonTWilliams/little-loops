<!-- Last updated: 2026-02-14 -->
# little-loops (ll) - Claude Code Plugin

Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing.

## Project Configuration

- **Plugin manifest**: `.claude-plugin/plugin.json`
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
skills/         # Skill definitions (15 skills)
hooks/          # Lifecycle hooks and prompts
scripts/        # Python package (little_loops)
templates/      # Project-type config templates
.issues/        # Issue tracking (bugs/, features/, enhancements/, completed/)
thoughts/       # Plans and research documents
docs/           # Architecture, API, troubleshooting
```

## Commands & Skills

Run `/ll:help` for full list. Both commands (`commands/*.md`) and skills (`skills/*/SKILL.md`) are invoked via `/ll:<name>`. Skills are marked with ^.

- **Issue Discovery**: `capture-issue`^, `scan-codebase`, `scan-product`, `audit-architecture`, `product-analyzer`^
- **Issue Refinement**: `normalize-issues`, `prioritize-issues`, `align-issues`, `format-issue`^, `refine-issue`, `verify-issues`, `tradeoff-review-issues`, `ready-issue`, `issue-workflow`^, `issue-size-review`^, `map-dependencies`^
- **Planning & Implementation**: `create-sprint`, `review-sprint`, `manage-issue`^, `iterate-plan`, `confidence-check`^
- **Code Quality**: `check-code`, `run-tests`, `audit-docs`^, `find-dead-code`
- **Git & Release**: `commit`, `open-pr`, `describe-pr`, `manage-release`, `sync-issues`, `cleanup-worktrees`
- **Automation & Loops**: `create-loop`^, `loop-suggester`, `workflow-automation-proposer`^
- **Meta-Analysis**: `audit-claude-config`^, `analyze-workflows`, `analyze-history`^
- **Session & Config**: `init`^, `configure`^, `help`, `handoff`, `resume`, `toggle-autoprompt`

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
- `docs/reference/API.md` - Python module reference
- `docs/development/TROUBLESHOOTING.md` - Common issues

## CLI Tools

The `scripts/` directory contains Python CLI tools:
- `ll-auto` - Automated sequential issue processing
- `ll-parallel` - Parallel issue processing with git worktrees
- `ll-messages` - Extract user messages from Claude Code logs
- `ll-loop` - FSM-based automation loop execution
- `ll-sprint` - Sprint-based issue processing
- `ll-workflows` - Workflow sequence analyzer
- `ll-history` - View completed issue statistics and history
- `ll-deps` - Cross-issue dependency analysis and validation
- `ll-sync` - Sync local issues with GitHub Issues
- `ll-verify-docs` - Verify documented counts match actual file counts
- `ll-check-links` - Check markdown documentation for broken links
- `ll-next-id` - Print next globally unique issue number

Install: `pip install -e "./scripts[dev]"`
