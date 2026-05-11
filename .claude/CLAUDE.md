<!-- Last updated: 2026-03-15 -->
# little-loops (ll) - Claude Code Plugin

Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing.

## Project Configuration

- **Plugin manifest**: `.claude-plugin/plugin.json`
- **Config schema**: `config-schema.json`
- **Project config**: `.ll/ll-config.json` (read this for project-specific settings)
- **Local overrides**: `.ll/ll.local.md` (user-specific, gitignored)
- **Hooks**: `hooks/hooks.json`

### Local Settings Override

Create `.ll/ll.local.md` to override settings for your local environment without modifying shared config:

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
skills/         # Skill definitions (29 skills)
hooks/          # Lifecycle hooks and prompts
scripts/        # Python package (little_loops)
templates/      # Project-type config templates
.issues/        # Issue tracking (bugs/, features/, enhancements/, epics/)
thoughts/       # Plans and research documents
docs/           # Architecture, API, troubleshooting
```

## Commands & Skills

Run `/ll:help` for full list. Both commands (`commands/*.md`) and skills (`skills/*/SKILL.md`) are invoked via `/ll:<name>`. Skills are marked with ^.

- **Issue Discovery**: `capture-issue`^, `scan-codebase`, `scan-product`, `audit-architecture`, `product-analyzer`^
- **Issue Refinement**: `normalize-issues`, `prioritize-issues`, `align-issues`, `format-issue`^ (template structure), `refine-issue` (codebase research), `wire-issue`^ (integration wiring), `verify-issues`, `tradeoff-review-issues`, `ready-issue`, `issue-workflow`^, `issue-size-review`^, `map-dependencies`^, `audit-issue-conflicts`^
- **Planning & Implementation**: `create-sprint`, `review-sprint`, `manage-issue`^, `iterate-plan`, `confidence-check`^, `go-no-go`^, `create-eval-from-issues`^
- **Code Quality**: `check-code`, `run-tests`, `audit-docs`^, `update-docs`^, `find-dead-code`
- **Git & Release**: `commit`, `open-pr`, `describe-pr`, `manage-release`, `sync-issues`, `cleanup-worktrees`
- **Automation & Loops**: `create-loop`^, `loop-suggester`, `review-loop`^, `debug-loop-run`^, `audit-loop-run`^, `rename-loop`^, `cleanup-loops`^, `workflow-automation-proposer`^, `verify-issue-loop`^
- **Meta-Analysis**: `audit-claude-config`^, `analyze-workflows`, `analyze-history`^, `improve-claude-md`^
- **Session & Config**: `init`^, `configure`^, `update`^, `help`, `handoff`, `resume`, `toggle-autoprompt`

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
- Types: `BUG`, `FEAT`, `ENH`, `EPIC`
- Priorities: P0 (critical) to P5 (low)

## Important Files

- `CONTRIBUTING.md` - Development setup and guidelines
- `docs/ARCHITECTURE.md` - System design
- `docs/reference/API.md` - Python module reference
- `docs/development/TROUBLESHOOTING.md` - Common issues

## CLI Tools

The `scripts/` directory contains Python CLI tools:
- `ll-auto` - Process all backlog issues sequentially in priority order
- `ll-parallel` - Process issues concurrently using isolated git worktrees
- `ll-sprint` - Define and execute curated issue sets with dependency-aware ordering
- `ll-action` - Invoke any ll skill as a one-shot command with JSON-structured output
- `ll-loop` - Execute FSM-based automation loops
- `ll-workflows` - Identify multi-step workflow patterns from user message history
- `ll-logs` - Discover, extract, and tail Claude Code session logs (`discover` / `extract` / `tail` subcommands; writes `logs/index.md`)
- `ll-messages` - Extract user messages from Claude Code logs
- `ll-history` - View completed issue statistics, analysis, and export topic-filtered excerpts from history
- `ll-deps` - Cross-issue dependency analysis and validation
- `ll-sync` - Sync local issues with GitHub Issues
- `ll-verify-docs` - Verify documented counts match actual file counts
- `ll-verify-skill-budget` - Check skill description token footprint against listing budget (exit 1 if over)
- `ll-check-links` - Check markdown documentation for broken links
- `ll-issues` - Issue management and visualization (next-id, list, show, sequence, impact-effort, refine-status, anchor-sweep)
- `ll-learning-tests` - Query and manage the learning test registry (check/list/mark-stale); record creation is owned by `/ll:explore-api`
- `ll-gitignore` - Suggest and apply `.gitignore` patterns based on untracked files
- `ll-migrate` - One-time migration of completed/deferred issues to type-based directories (ENH-1390)
- `ll-migrate-relationships` - One-time migration that renames `parent_issue:` → `parent:` and `related:` → `relates_to:` across all issue files (ENH-1434)
- `ll-migrate-labels` - One-time migration that moves freeform `## Labels` body sections to `labels:` frontmatter across all issue files (ENH-1392)
- `ll-create-extension` - Scaffold a new extension repo with entry-point, skeleton handler, and LLTestBus example
- `ll-generate-schemas` - Regenerate JSON Schema files for all `LLEvent` types into `docs/reference/schemas/` (maintainer tool)
- `ll-generate-skill-descriptions` - Auto-generate ≤100-char skill descriptions via Claude CLI; skips `disable-model-invocation: true` skills (release utility)

Install: `pip install -e "./scripts[dev]"`

## Automation: Scratch Pad

When running in automation contexts (ll-auto, ll-parallel, ll-sprint), use scratch pad files to keep large tool outputs out of conversation context:

- **Before reading a file**, check its size: `wc -l <path>`. If > 200 lines, use `Bash "mkdir -p .loops/tmp/scratch/ && cat <path> > .loops/tmp/scratch/<descriptive-name>.txt && echo 'Saved N lines to .loops/tmp/scratch/<descriptive-name>.txt'"` instead of the Read tool.
- **For test/lint runs**, pipe output to scratch and tail the summary: `Bash "python -m pytest ... > .loops/tmp/scratch/test-results.txt 2>&1; tail -20 .loops/tmp/scratch/test-results.txt"`.
- **Reference scratch paths** when reasoning about file contents. Use `Read` on the scratch file only when you need specific content later.
- Small outputs (< 200 lines) should still be inlined normally.
