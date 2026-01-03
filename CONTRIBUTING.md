# Contributing to little-loops

Thank you for your interest in contributing to little-loops! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git
- Claude Code CLI (for testing commands)

### Installation

1. Clone the repository:

```bash
git clone https://github.com/little-loops/little-loops.git
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

# Run with coverage
pytest scripts/tests/ --cov=little_loops --cov-report=html

# Run specific test file
pytest scripts/tests/test_config.py

# Run with verbose output
pytest scripts/tests/ -v
```

### Code Quality

```bash
# Run linter
ruff check scripts/little_loops/

# Run type checker
mypy scripts/little_loops/

# Auto-format code
ruff format scripts/little_loops/
```

## Project Structure

```
little-loops/
├── plugin.json           # Plugin manifest
├── config-schema.json    # Configuration JSON Schema
├── commands/             # Slash command templates (*.md)
├── agents/               # Agent definitions (*.md)
├── hooks/                # Lifecycle hooks
├── templates/            # Project-type config templates
├── docs/                 # Documentation
│   ├── TROUBLESHOOTING.md  # Common issues and solutions
│   ├── ARCHITECTURE.md     # System design diagrams
│   └── API.md              # Python API reference
└── scripts/              # Python CLI tools
    ├── pyproject.toml    # Package configuration
    ├── tests/            # Test suite
    └── little_loops/     # Main package
        ├── cli.py        # CLI entry points
        ├── config.py     # Configuration management
        ├── state.py      # State persistence
        ├── issue_manager.py
        ├── issue_parser.py
        ├── issue_lifecycle.py
        ├── git_operations.py
        ├── work_verification.py
        ├── subprocess_utils.py
        ├── logger.py
        └── parallel/     # Parallel processing module
            ├── orchestrator.py
            ├── worker_pool.py
            ├── merge_coordinator.py
            ├── priority_queue.py
            ├── output_parsing.py
            └── types.py
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
4. Ensure code quality: `ruff check scripts/little_loops/ && mypy scripts/little_loops/`
5. Update documentation if needed
6. Submit a pull request

### PR Guidelines

- Keep PRs focused on a single concern
- Include tests for new functionality
- Update CHANGELOG.md for user-facing changes
- Ensure CI passes before requesting review

## Adding Commands

Commands are defined as Markdown files in `commands/`:

```markdown
---
description: "Brief description for /ll:help"
arguments:
  - name: "arg_name"
    description: "Argument description"
    required: true
---

# Command Title

[Command implementation instructions]
```

## Adding Agents

Agents are defined as Markdown files in `agents/`:

```markdown
# Agent Name

[System prompt and instructions for the agent]
```

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

- Check [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues
- Review [docs/API.md](docs/API.md) for Python module documentation
- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Use discussions for questions and ideas

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
