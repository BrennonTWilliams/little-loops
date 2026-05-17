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
├── agents/               # 9 agent definitions (*.md)
│   ├── codebase-analyzer.md
│   ├── codebase-locator.md
│   ├── codebase-pattern-finder.md
│   ├── consistency-checker.md
│   ├── loop-specialist.md
│   ├── plugin-config-auditor.md
│   ├── prompt-optimizer.md
│   ├── web-search-researcher.md
│   └── workflow-pattern-analyzer.md
├── hooks/                # Lifecycle hooks
├── loops/                # Built-in FSM loop definitions (44 YAML files)
├── skills/               # 30 skill definitions (user-invocable workflows)
│   ├── analyze-history/              # Analyze issue history and trends
│   ├── debug-loop-run/               # Analyze loop execution history
│   ├── audit-loop-run/               # Audit loop goal achievement
│   ├── audit-claude-config/          # Audit plugin configuration
│   ├── audit-docs/                   # Audit documentation accuracy
│   ├── audit-issue-conflicts/        # Detect conflicts across open issues
│   ├── capture-issue/                # Capture issues from conversation
│   ├── cleanup-loops/                # Find and clean stuck loop processes
│   ├── confidence-check/             # Pre-implementation confidence check
│   ├── decide-issue/                 # Resolve competing implementation options
│   ├── explore-api/                  # Guided 4-phase external-API exploration with LearnTestRecord output
│   ├── go-no-go/                     # Adversarial GO/NO-GO issue assessment
│   ├── configure/                    # Configure ll-config.json
│   ├── create-eval-from-issues/      # Generate eval harness YAML from issue IDs
│   ├── create-loop/                  # Create FSM loop configurations
│   ├── format-issue/                 # Format issues to template v2.0
│   ├── improve-claude-md/            # Rewrite CLAUDE.md with <important if> blocks
│   ├── init/                         # Initialize project configuration
│   ├── issue-size-review/            # Evaluate issue complexity
│   ├── issue-workflow/               # Issue lifecycle quick reference
│   ├── manage-issue/                 # Manage issue lifecycle
│   ├── map-dependencies/             # Discover and map issue dependencies
│   ├── product-analyzer/             # Analyze codebase against product goals
│   ├── review-loop/                  # Review and improve FSM loop configurations
│   ├── update/                       # Update little-loops components
│   ├── update-docs/                  # Identify stale or missing documentation
│   ├── verify-issue-loop/            # Generate FSM verification loop from issue acceptance criteria
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
│   │   ├── LOOPS_GUIDE.md               # Loop creation guide
│   │   ├── SESSION_HANDOFF.md           # Context management guide
│   │   ├── SPRINT_GUIDE.md             # Sprint planning and execution
│   │   └── WORKFLOW_ANALYSIS_GUIDE.md  # Workflow analysis guide
│   ├── development/                     # Developer documentation
│   │   ├── E2E_TESTING.md              # End-to-end testing guide
│   │   ├── MERGE-COORDINATOR.md        # Merge coordinator docs
│   │   ├── TESTING.md                   # Testing patterns and conventions
│   │   └── TROUBLESHOOTING.md          # Common issues and solutions
│   ├── research/                        # Research documents
│   │   ├── CLI-TOOLS-AUDIT.md           # CLI tools audit
│   │   ├── claude-cli-integration-mechanics.md
│   │   ├── LCM-Integration-Brainstorm.md  # LCM integration roadmap
│   │   └── LCM-Lossless-Context-Management.md  # LCM research
│   ├── claude-code/                     # Claude Code documentation
│   ├── codex/                           # Codex CLI documentation
│   └── demo/                            # Demo materials
└── scripts/              # Python CLI tools
    ├── pyproject.toml    # Package configuration
    ├── tests/            # Test suite
    └── little_loops/     # Main package
        ├── cli/                 # CLI entry points
        │   ├── __init__.py
        │   ├── action.py        # ll-action one-shot skill invocation CLI
        │   ├── generate_skill_descriptions.py  # ll-generate-skill-descriptions release utility
        │   ├── auto.py
        │   ├── create_extension.py  # ll-create-extension scaffold CLI
        │   ├── doctor.py
        │   ├── docs.py
        │   ├── deps.py
        │   ├── history.py
        │   ├── logs.py
        │   ├── messages.py
        │   ├── parallel.py
        │   ├── sync.py
        │   ├── output.py        # Shared CLI output utilities (colors, terminal width)
        │   ├── loop/            # ll-loop subcommands
        │   ├── sprint/          # ll-sprint subcommands
        │   └── issues/          # ll-issues subcommands
        ├── issues/              # Issue utility sub-package (ENH-1300)
        │   ├── __init__.py
        │   ├── anchors.py       # resolve_anchor(): language-agnostic backwards scan
        │   └── anchor_sweep.py  # sweep_issues(): two-phase scan-and-rewrite
        ├── cli_args.py          # Argument parsing
        ├── config.py            # Configuration management
        ├── state.py             # State persistence
        ├── frontmatter.py       # YAML frontmatter parsing
        ├── learning_tests.py    # Learning test registry (CRUD for .ll/learning-tests/)
        ├── doc_counts.py        # Documentation count utilities
        ├── link_checker.py      # Link validation
        ├── issue_manager.py
        ├── issue_parser.py
        ├── issue_discovery/     # Issue discovery and deduplication (package)
        ├── issue_lifecycle.py
        ├── issue_history/       # Issue history and statistics (package)
        ├── git_operations.py
        ├── work_verification.py
        ├── sprint.py            # Sprint planning and execution
        ├── sync.py              # GitHub Issues sync
        ├── goals_parser.py      # Goals file parsing
        ├── subprocess_utils.py
        ├── host_runner.py       # Host CLI abstraction (HostRunner Protocol + ClaudeCodeRunner + CodexRunner + OpenCodeRunner + PiRunner)
        ├── text_utils.py        # Text processing utilities
        ├── logger.py
        ├── logo.py              # CLI logo display
        ├── dependency_graph.py  # Dependency graph construction
        ├── dependency_mapper/   # Cross-issue dependency discovery (sub-package)
        │   ├── __init__.py      #   Re-exports for backwards compatibility
        │   ├── models.py        #   Data models
        │   ├── analysis.py      #   Conflict scoring and analysis
        │   ├── formatting.py    #   Report and graph formatting
        │   └── operations.py    #   File mutation operations
        ├── session_log.py       # Session log linking for issues
        ├── file_utils.py        # Shared file I/O utilities (atomic writes)
        ├── user_messages.py     # User message extraction
        ├── workflow_sequence/   # Workflow analysis (ll-workflows, sub-package)
        │   ├── __init__.py      #   Re-exports: analyze_workflows, models
        │   ├── analysis.py      #   Core analysis: boundaries, entity clustering
        │   ├── models.py        #   Data models (Workflow, SessionLink, etc.)
        │   └── io.py            #   YAML/JSON input-output helpers
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
        │   ├── handoff_handler.py
        │   └── rate_limit_circuit.py
        ├── extension.py         # Extension protocol, loader, and reference implementation
        ├── testing.py           # Offline LLTestBus test harness for extension development
        ├── extensions/          # Bundled reference extensions (sub-package)
        │   ├── __init__.py      #   Re-exports ReferenceInterceptorExtension
        │   └── reference_interceptor.py  #   Passthrough interceptor template
        ├── output_parsing.py  # Shared output parsing
        └── parallel/     # Parallel processing module
            ├── __init__.py
            ├── orchestrator.py
            ├── worker_pool.py
            ├── merge_coordinator.py
            ├── priority_queue.py
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

### Documentation wiring for new CLI tools

`README.md` is the hero page — positioning claims and quick demos, not a CLI catalog. When you add a new `ll-` CLI tool, do **not** add a `### ll-<toolname>` section to `README.md`.

Instead, update these files:

| File | What to update |
|------|---------------|
| `docs/reference/CLI.md` | Full `### ll-<toolname>` section with flags and examples |
| `commands/help.md` | One-line entry in the CLI TOOLS block |
| `.claude/CLAUDE.md` | One-line entry in the CLI Tools list |
| `skills/configure/areas.md` | Add tool name; increment "Authorize all N" count |
| `README.md` | Increment `"N CLI tools"` count only — no new section |

Add a presence test in `scripts/tests/test_create_extension_wiring.py` that checks `CLI_REFERENCE`, `HELP_MD`, and `CLAUDE_MD` — not `README`. The structural guard in `test_readme_structure.py` will fail CI if a `### ll-` section lands in the README.

## Creating Issues

Issues are tracked in `.issues/` with structured Markdown files following the v2.0 template.

### Issue Template (v2.0)

The issue template has been optimized for AI implementation with **20 sections** across BUG, FEAT, ENH, and EPIC types.

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
- **EPIC**: Lists `children:` (constituent BUG/FEAT/ENH IDs), articulates coordination/business goal — not directly implementable

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

### Relationship Fields

Issues use six frontmatter fields to express relationships between issues. Use the canonical names — deprecated names (`parent_issue`, `related`) are no longer accepted.

| Field | Type | When to use |
|-------|------|-------------|
| `parent` | string | This issue was decomposed from a parent (e.g., `parent: ENH-179`) |
| `blocked_by` | list | Hard dependency — this issue **cannot start** until listed issues are done; wave-gated in sprints |
| `depends_on` | list | Soft ordering — this issue *should* come after listed issues, but sprint execution is not blocked |
| `relates_to` | list | Thematically related issues with no ordering constraint; for cross-reference only |
| `duplicate_of` | string | This issue duplicates another; set when closing as duplicate |
| `blocks` | list | Computed inverse of `blocked_by`; written automatically by `ll-deps fix` — do not set manually |

**`blocked_by` vs `depends_on`**: Use `blocked_by` only when ISSUE-B **must** complete before ISSUE-A can start (hard stop, sprint wave-gated). Use `depends_on` for preferred ordering that does not gate execution.

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

### After Creating a New Command

Run `ll-adapt-skills-for-codex --apply` to bridge the new command into `skills/ll-<command-name>/` so Codex CLI users can discover it via the Skills API. Skipping this step will fail CI (`test_every_command_has_bridged_skill`). Commands tagged `disable-model-invocation: true` are exempt. This mirrors the New Skill Checklist step below — the same tool now handles both surfaces.

## Adding Agents

Agents are defined as Markdown files in `agents/`:

```markdown
# Agent Name

[System prompt and instructions for the agent]
```

After creating a new agent, run `ll-adapt-agents-for-codex --apply` to generate a `.codex/agents/<name>.toml` file so Codex CLI users can select the agent via `--agent <name>`.

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
name: my-skill
description: |
  Use when the user asks to [trigger conditions], [more conditions], or asks "[example phrase]."
  [Optional brief context about what the skill does].

  Trigger keywords: "keyword1", "keyword2", "keyword3"
metadata:
  short-description: Use when the user asks to [trigger conditions]. (≤80 chars, Codex TUI)
---

# Skill Name

[Skill instructions and usage documentation]
```

**Description convention**: The `description` field is a **trigger document** — Claude uses it to decide when to auto-activate the skill. Lead with trigger conditions ("Use when..."), not a capability summary. Include 5-10 quoted trigger keywords matching natural user phrasing. This reduces missed activations and false positives.

### New Skill Checklist

Before adding a new skill, answer:

1. **Will users always type this command explicitly?**
   If yes → add `disable-model-invocation: true` to frontmatter. Examples: `update`, `cleanup-worktrees`, `audit-loop-run`, `analyze-history`.

2. **Should the LLM route to this skill from natural language?**
   If yes → keep default (no flag). Keep the `description` field ≤ 100 characters. No bullet lists in descriptions.

3. **After creating a new skill:** run `ll-adapt-skills-for-codex --apply` to generate `agents/openai.yaml` alongside the `SKILL.md`. Skipping this step will fail CI (`test_all_real_skills_have_openai_yaml`). Skills tagged `disable-model-invocation: true` are exempt.

4. **Before release:** run `ll-verify-skill-budget` to check the total description token footprint. Exits 1 if over the 2000-token budget — shorten descriptions or tag more skills with `disable-model-invocation: true`. Then run `/doctor` and verify "0 skill descriptions dropped".

> **Optional utility:** `ll-generate-skill-descriptions` auto-generates minimal (≤100 char) descriptions from SKILL.md content using Claude (dry-run by default; use `--apply` to write back). Useful before a release to batch-refresh descriptions for LLM-discoverable skills.

Skills are user-invocable workflows that activate based on trigger keywords or explicit invocation. Prefer creating skills over agents for new functionality (see development preferences in CLAUDE.md).

## Authoring Extensions

little-loops supports custom extensions that receive structured events from core subsystems. Extensions implement the `LLExtension` protocol and are wired to the `EventBus` at CLI startup.

### Create → Develop → Test → Publish workflow

**1. Scaffold**

Use `ll-create-extension` to generate a new extension repo with boilerplate entry point and test:

```bash
ll-create-extension my-ext           # Scaffold into ./my-ext/
ll-create-extension my-ext --dry-run # Preview without writing files
```

This produces a `pyproject.toml` with the `little_loops.extensions` entry-point group registered, a skeleton `on_event` handler in `my_ext/extension.py`, and an example test in `tests/test_my_ext.py` using `LLTestBus`.

**2. Develop**

Implement the `on_event` method in your extension class. Optionally set `event_filter` to a glob string (e.g. `"issue.*"`) to receive only matching event types:

```python
from little_loops.events import LLEvent

class MyExtension:
    event_filter = "issue.*"

    def on_event(self, event: LLEvent) -> None:
        print(f"{event.type} — {event.payload}")
```

In addition to the base `LLExtension` shape, an extension class may implement any of the optional mixin Protocols exposed from `little_loops`: `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`, and `LLHookIntentExtension`. Each is detected via `hasattr()` at wire time, so you opt in simply by implementing the corresponding method. `LLHookIntentExtension.provided_hook_intents()` returns a mapping of hook-intent name to a `Callable[[LLHookEvent], LLHookResult]` handler; returned handlers are merged into the global hook-intent registry consumed by `little_loops.hooks`.

**3. Test offline with LLTestBus**

`LLTestBus` lets you replay recorded events against your extension without running a live loop:

```python
from little_loops.testing import LLTestBus
from my_ext.extension import MyExtension

def test_my_ext():
    bus = LLTestBus.from_jsonl("fixtures/events.jsonl")
    ext = MyExtension()
    bus.register(ext)
    bus.replay()
    assert any(e.type == "issue.completed" for e in bus.delivered_events)
```

See [API Reference → LLTestBus](docs/reference/API.md#lltestbus) for full class documentation.

**4. Publish**

Install your extension package into the same Python environment as little-loops. The `little_loops.extensions` entry-point group is discovered automatically on every `ll` run — no changes to `ll-config.json` required.

To load extensions not published as packages, list them in `ll-config.json`:

```json
{ "extensions": ["my_ext.extension:MyExtension"] }
```

See [Configuration Reference → Extensions](docs/reference/CONFIGURATION.md#extensions) for full wiring details.

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

## Event Schema Maintenance

When adding a new `LLEvent` type or changing payload fields:

1. Update `docs/reference/EVENT-SCHEMA.md` with the new type and its payload fields.
2. Add or update the entry in `SCHEMA_DEFINITIONS` in `scripts/little_loops/generate_schemas.py`.
3. Regenerate the JSON Schema files:

   ```bash
   python scripts/little_loops/generate_schemas.py docs/reference/schemas
   # or via the installed CLI:
   ll-generate-schemas
   ```

4. Commit the updated `.json` files in `docs/reference/schemas/` alongside the source change.

**Note on `LLHookEvent` / `LLHookResult`:** these are a sibling request/response wire format used by `LLHookIntentExtension` handlers — not pub/sub events on the `EventBus`. They do **not** participate in the JSON Schema regeneration flow above. See [`docs/reference/EVENT-SCHEMA.md`](docs/reference/EVENT-SCHEMA.md) and `scripts/little_loops/hooks/types.py` for the type definitions.

## MCP Debugging

`mcp-call` is a developer utility for calling MCP tools directly from the shell without a full Claude Code session. Useful when debugging or testing MCP server integrations.

```bash
mcp-call server/tool-name '{"param": "value"}'
```

It reads `.mcp.json` from the current directory, spawns the MCP server subprocess, performs a JSON-RPC handshake, and prints the result. Full reference: [`docs/reference/CLI.md`](docs/reference/CLI.md) (search for `mcp-call`).

## Questions?

- Check [docs/development/TROUBLESHOOTING.md](docs/development/TROUBLESHOOTING.md) for common issues
- Review [docs/reference/API.md](docs/reference/API.md) for Python module documentation
- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Use discussions for questions and ideas

## License

By contributing, you agree that your contributions will be licensed under the MIT License.