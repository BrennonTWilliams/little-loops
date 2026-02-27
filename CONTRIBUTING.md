# Contributing to little-loops

Thank you for your interest in contributing to little-loops! This document provides guidelines and instructions for contributing.

> **Related Documentation:**
> - [Issue Template Guide](docs/reference/ISSUE_TEMPLATE.md) - v2.0 issue template with examples and best practices
> - [Testing Guide](docs/development/TESTING.md) - Comprehensive testing patterns and conventions
> - [Architecture Overview](docs/ARCHITECTURE.md) - System design and component relationships
> - [API Reference](docs/reference/API.md) - Python module documentation
> - [Troubleshooting](docs/development/TROUBLESHOOTING.md) - Common issues and solutions

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git
- Claude Code CLI (for testing commands)

### Installation

1. Clone the repository:

```bash
git clone https://github.com/BrennonTWilliams/little-loops.git
cd little-loops
```

2. Install the Python package in development mode:

```bash
pip install -e "./scripts[dev]"

# For full development with LLM features (e.g., ll-sync):
pip install -e "./scripts[dev,llm]"
```

3. Verify installation:

```bash
ll-auto --help
ll-parallel --help
```

### Running Tests

```bash
# Run all tests
pytest scripts/tests/

# Run only unit tests (fast, excludes integration tests)
pytest -m "not integration" scripts/tests/

# Run only integration tests
pytest -m integration scripts/tests/

# Run with coverage
pytest scripts/tests/ --cov=little_loops --cov-report=html

# Run specific test file
pytest scripts/tests/test_config.py

# Run with verbose output
pytest scripts/tests/ -v
```

### Mutation Testing

Mutation testing verifies test assertion quality by introducing artificial bugs (mutants) into source code and checking that tests fail. A surviving mutant means the test suite didn't catch the mutation.

```bash
# Run mutation testing (slow - can take hours for full codebase)
cd scripts
mutmut run

# View results summary
mutmut results

# Show specific surviving mutant details
mutmut show 42

# Apply a mutation to see what it looks like
mutmut apply 42
```

Mutation testing is slow and not included in regular test runs. Use it to:
- Identify tests with weak assertions
- Verify critical code has quality tests
- Find untested code paths

Configuration is in `scripts/pyproject.toml` under `[tool.mutmut]`.

### Code Quality

```bash
# Run linter
ruff check scripts/

# Run type checker
mypy scripts/little_loops/

# Auto-format code
ruff format scripts/
```

## Project Structure

```
little-loops/
├── .claude-plugin/
│   └── plugin.json       # Plugin manifest
├── config-schema.json    # Configuration JSON Schema
├── commands/             # Slash command templates (*.md)
├── agents/               # 8 agent definitions (*.md)
│   ├── codebase-analyzer.md
│   ├── codebase-locator.md
│   ├── codebase-pattern-finder.md
│   ├── consistency-checker.md
│   ├── plugin-config-auditor.md
│   ├── prompt-optimizer.md
│   ├── web-search-researcher.md
│   └── workflow-pattern-analyzer.md
├── hooks/                # Lifecycle hooks
├── loops/                # Built-in FSM loop definitions
│   ├── codebase-scan.yaml
│   ├── history-reporting.yaml
│   ├── issue-readiness-cycle.yaml
│   ├── issue-verification.yaml
│   ├── pre-pr-checks.yaml
│   ├── quality-gate.yaml
│   ├── sprint-execution.yaml
│   └── workflow-analysis.yaml
├── skills/               # 15 skill definitions (user-invocable workflows)
│   ├── analyze-history/              # Analyze issue history and trends
│   ├── audit-claude-config/          # Audit plugin configuration
│   ├── audit-docs/                   # Audit documentation accuracy
│   ├── capture-issue/                # Capture issues from conversation
│   ├── confidence-check/             # Pre-implementation confidence check
│   ├── configure/                    # Configure ll-config.json
│   ├── create-loop/                  # Create FSM loop configurations
│   ├── format-issue/                 # Format issues to template v2.0
│   ├── init/                         # Initialize project configuration
│   ├── issue-size-review/            # Evaluate issue complexity
│   ├── issue-workflow/               # Issue lifecycle quick reference
│   ├── manage-issue/                 # Manage issue lifecycle
│   ├── map-dependencies/             # Discover and map issue dependencies
│   ├── product-analyzer/             # Analyze codebase against product goals
│   └── workflow-automation-proposer/ # Propose automations from patterns
├── templates/            # Project-type config templates
├── docs/                 # Documentation
│   ├── ARCHITECTURE.md                  # System design diagrams
│   ├── INDEX.md                         # Documentation index
│   ├── generalized-fsm-loop.md         # FSM loop system
│   ├── reference/                       # Reference documentation
│   │   ├── API.md                       # Python API reference
│   │   ├── COMMANDS.md                  # Command reference
│   │   ├── CONFIGURATION.md             # Configuration reference
│   │   └── ISSUE_TEMPLATE.md            # Issue template guide
│   ├── guides/                          # User guides
│   │   ├── GETTING_STARTED.md           # Getting started guide
│   │   ├── ISSUE_MANAGEMENT_GUIDE.md    # Issue management workflow
│   │   ├── LOOPS_GUIDE.md               # Loop creation and paradigms
│   │   ├── SESSION_HANDOFF.md           # Context management guide
│   │   └── SPRINT_GUIDE.md             # Sprint planning and execution
│   ├── development/                     # Developer documentation
│   │   ├── E2E_TESTING.md              # End-to-end testing guide
│   │   ├── MERGE-COORDINATOR.md        # Merge coordinator docs
│   │   ├── TESTING.md                   # Testing patterns and conventions
│   │   └── TROUBLESHOOTING.md          # Common issues and solutions
│   ├── research/                        # Research documents
│   │   ├── CLI-TOOLS-AUDIT.md           # CLI tools audit
│   │   └── claude-cli-integration-mechanics.md
│   ├── claude-code/                     # Claude Code documentation
│   └── demo/                            # Demo materials
└── scripts/              # Python CLI tools
    ├── pyproject.toml    # Package configuration
    ├── tests/            # Test suite
    └── little_loops/     # Main package
        ├── cli/                 # CLI entry points
        │   ├── __init__.py
        │   ├── auto.py
        │   ├── docs.py
        │   ├── history.py
        │   ├── messages.py
        │   ├── next_id.py
        │   ├── parallel.py
        │   ├── sync.py
        │   ├── loop/            # ll-loop subcommands
        │   ├── sprint/          # ll-sprint subcommands
        │   └── issues/          # ll-issues subcommands
        ├── cli_args.py          # Argument parsing
        ├── config.py            # Configuration management
        ├── state.py             # State persistence
        ├── frontmatter.py       # YAML frontmatter parsing
        ├── doc_counts.py        # Documentation count utilities
        ├── link_checker.py      # Link validation
        ├── issue_manager.py
        ├── issue_parser.py
        ├── issue_discovery/     # Issue discovery and deduplication (package)
        ├── issue_lifecycle.py
        ├── issue_history.py     # Issue history and statistics
        ├── git_operations.py
        ├── work_verification.py
        ├── sprint.py            # Sprint planning and execution
        ├── sync.py              # GitHub Issues sync
        ├── goals_parser.py      # Goals file parsing
        ├── subprocess_utils.py
        ├── logger.py
        ├── logo.py              # CLI logo display
        ├── dependency_graph.py  # Dependency graph construction
        ├── dependency_mapper.py # Cross-issue dependency discovery
        ├── user_messages.py     # User message extraction
        ├── workflow_sequence_analyzer.py  # Workflow analysis (ll-workflows)
        ├── fsm/                  # FSM loop system
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
        └── parallel/     # Parallel processing module
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
            └── tasks/    # Task templates for Claude CLI
```

For architecture details and system design, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Making Changes

### Branching Strategy

- `main` - Stable release branch
- `feature/*` - New features
- `fix/*` - Bug fixes
- `docs/*` - Documentation updates

### Commit Messages

Follow conventional commits format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `test` - Tests
- `refactor` - Code refactoring
- `chore` - Maintenance

Examples:
```
feat(parallel): add worker timeout configuration
fix(parser): handle empty issue files gracefully
docs(readme): update installation instructions
test(config): add tests for configuration merging
```

### Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Ensure tests pass: `pytest scripts/tests/`
4. Ensure code quality: `ruff check scripts/ && mypy scripts/little_loops/`
5. Update documentation if needed
6. Submit a pull request

### PR Guidelines

- Keep PRs focused on a single concern
- Include tests for new functionality
- Update CHANGELOG.md for user-facing changes
- Ensure CI passes before requesting review

## Creating Issues

Issues are tracked in `.issues/` with structured Markdown files following the v2.0 template.

### Issue Template (v2.0)

The issue template has been optimized for AI implementation with **19 sections** across BUG, FEAT, and ENH types.

**Key Features**:
- Anchor-based code references (function/class names, not line numbers)
- High-level Implementation Steps (agent expands into detailed plan)
- Enhanced Motivation and Impact sections with justifications
- New Root Cause (BUG), API/Interface (FEAT/ENH) sections

**See**: [docs/reference/ISSUE_TEMPLATE.md](docs/reference/ISSUE_TEMPLATE.md) for complete guide with examples

### Quick Start

**Create an issue**:
```bash
/ll:capture-issue "Description of the issue"
```

**Format an issue**:
```bash
/ll:format-issue .issues/bugs/P2-BUG-123-description.md
```

**Validate an issue**:
```bash
/ll:ready-issue .issues/bugs/P2-BUG-123-description.md
```

### Issue Quality Checklist

All issues should pass these checks:

- [ ] **Summary**: One sentence combining WHAT and WHY
- [ ] **Impact**: Includes justifications for priority, effort, and risk
- [ ] **Proposed Solution**: Uses anchor-based references (function/class names) not line numbers
- [ ] **Integration Map**: Lists all affected files (callers, tests, docs, config)
- [ ] **Implementation Steps**: High-level outline (3-8 phases), not detailed substeps

**Type-specific**:
- **BUG**: Numbered steps to reproduce, Root Cause with file + function anchor
- **FEAT**: Concrete Use Case scenario, API/Interface for public contracts
- **ENH**: Motivation with quantified impact, Success Metrics with targets

### Best Practices

**For AI Implementation**:
- Use function/class anchors: `in function foo()` not `at line 42`
- Include code examples in Proposed Solution
- Reference existing patterns to reuse
- Use Integration Map to enumerate ALL affected files (prevents isolated changes)
- Keep Implementation Steps high-level (let agent create detailed plan)

**For Human Reviewers**:
- Quantify impact: "affects 100 users" not "affects users"
- Show concrete scenarios, not generic templates
- Justify priority/effort/risk decisions
- Link relevant documentation

## Adding Commands

Commands are defined as Markdown files in `commands/`:

```markdown
---
description: "Brief description for /ll:help"
argument-hint: "[arg_name] [flags]"
arguments:
  - name: "arg_name"
    description: "Argument description"
    required: true
  - name: flags
    description: "Optional flags: --quick (faster), --deep (thorough)"
    required: false
---

# Command Title

[Command implementation instructions]
```

### Flag Conventions

When adding flag support to commands or skills, follow these conventions:

1. **Declare flags** in the YAML frontmatter `arguments` array as a `flags` entry
2. **Parse flags** using bash substring matching:
   ```bash
   FLAGS="${flags:-}"
   QUICK_MODE=false
   if [[ "$FLAGS" == *"--quick"* ]]; then QUICK_MODE=true; fi
   ```
3. **Document flags** in the Arguments section with descriptions
4. **Show flag usage** in the Examples section

**Standard flags** — reuse these names when the behavior matches:

| Flag | When to use |
|------|-------------|
| `--quick` | Reduce analysis depth for faster results |
| `--deep` | Increase thoroughness, spawn sub-agents |
| `--focus [area]` | Narrow scope to a specific concern area |
| `--dry-run` | Preview changes without applying them |
| `--auto` | Non-interactive mode, no user prompts |
| `--verbose` | Include detailed output |
| `--all` | Process all items instead of a single item |

Only add flags that meaningfully change command behavior. Flags are optional — commands must work unchanged without them.

## Adding Agents

Agents are defined as Markdown files in `agents/`:

```markdown
# Agent Name

[System prompt and instructions for the agent]
```

## Adding Skills

Skills are defined as directories in `skills/`, each containing a `SKILL.md` file:

```
skills/
└── my-skill/
    └── SKILL.md
```

The `SKILL.md` file uses YAML frontmatter for metadata, followed by the skill instructions:

```markdown
---
description: |
  Brief description of what the skill does.

  Trigger keywords: "keyword1", "keyword2", "keyword3"
---

# Skill Name

[Skill instructions and usage documentation]
```

Skills are user-invocable workflows that activate based on trigger keywords or explicit invocation. Prefer creating skills over agents for new functionality (see development preferences in CLAUDE.md).

## Code Style

- Use type hints for all public functions and methods
- Add docstrings to classes and public methods
- Follow PEP 8 with 100 character line limit
- Use dataclasses for data structures
- Prefer explicit over implicit

## Testing Guidelines

- Write unit tests for all new functionality
- Use pytest fixtures for common setup
- Mock external dependencies (subprocess, file I/O)
- Test both success and error paths
- Aim for meaningful coverage, not just line coverage

## Questions?

- Check [docs/development/TROUBLESHOOTING.md](docs/development/TROUBLESHOOTING.md) for common issues
- Review [docs/reference/API.md](docs/reference/API.md) for Python module documentation
- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Use discussions for questions and ideas

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
