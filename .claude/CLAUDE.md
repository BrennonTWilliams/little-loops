<!-- Last updated: 2026-02-06 -->
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
skills/         # Skill definitions
hooks/          # Lifecycle hooks and prompts
scripts/        # Python package (little_loops)
templates/      # Project-type config templates
.issues/        # Issue tracking (bugs/, features/, enhancements/, completed/)
thoughts/       # Plans and research documents
docs/           # Architecture, API, troubleshooting
```

## Commands

Run `/ll:help` for full list. Key commands by capability:

- **Issue Discovery**: `capture_issue`, `scan_codebase`, `scan_product`, `audit_architecture`
- **Issue Refinement**: `normalize_issues`, `prioritize_issues`, `align_issues`, `format_issue`, `refine_issue`, `verify_issues`, `tradeoff_review_issues`, `ready_issue`
- **Planning & Implementation**: `create_sprint`, `review_sprint`, `manage_issue`, `iterate_plan`
- **Code Quality**: `check_code`, `run_tests`, `audit_docs`, `find_dead_code`
- **Git & Release**: `commit`, `open_pr`, `describe_pr`, `manage_release`, `sync_issues`, `cleanup_worktrees`
- **Automation & Loops**: `create_loop`, `loop-suggester`
- **Meta-Analysis**: `audit_claude_config`, `analyze-workflows`
- **Session & Config**: `init`, `configure`, `help`, `handoff`, `resume`, `toggle_autoprompt`

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
- `ll-deps` - Cross-issue dependency analysis and validation
- `ll-sync` - Sync local issues with GitHub Issues
- `ll-verify-docs` - Verify documented counts match actual file counts
- `ll-check-links` - Check markdown documentation for broken links

Install: `pip install -e "./scripts[dev]"`
