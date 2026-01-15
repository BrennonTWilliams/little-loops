# P3-FEAT-050: Sprint and Sequence Execution - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-050-sprint-and-sequence-execution.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The little-loops project provides automated issue management through two execution modes:
- `ll-auto` - Sequential issue processing via `AutoManager` (`issue_manager.py:193`)
- `ll-parallel` - Parallel issue processing via `ParallelOrchestrator` (`parallel/orchestrator.py:34`)

Both tools support filtering by priority, category, and ad-hoc issue lists, but lack the ability to define and execute **named groups of issues** (sprints/sequences).

### Key Discoveries
- The `/ll:create-sprint` slash command already exists (`.claude/commands/ll_create_sprint.md:1-127`)
- Sprint YAML format is already defined in the issue specification
- CLI entry points are registered in `pyproject.toml:47-51`
- The `ll-loop` command demonstrates the full subcommand pattern to follow (`cli.py:412-913`)
- YAML loading patterns exist in `fsm/validation.py:312` (`yaml.safe_load`)
- Dataclass patterns with `to_dict`/`from_dict` are used throughout (`config.py`, `state.py`, `parallel/types.py`)

### Existing Patterns to Follow

**CLI Structure** (from `ll-loop` at `cli.py:412-913`):
- Uses `argparse.ArgumentParser` with `add_subparsers()`
- Defines `known_subcommands` set for arg preprocessing
- Implements shorthand: `ll-loop fix-types` → `ll-loop run fix-types`
- Command functions return `int` exit codes
- Uses `RawDescriptionHelpFormatter` for custom help text

**YAML File Loading** (from `fsm/validation.py:294-345`):
- Uses `yaml.safe_load()` for secure parsing
- Validates file exists before loading
- Checks required fields before parsing
- Converts dict to dataclass via `from_dict()` class method
- Separates errors from warnings

**Dataclass Pattern** (from `config.py:30-101`):
- Uses `@dataclass` decorator with type hints
- Optional fields default to `None`
- `to_dict()` method for serialization (omits `None` values)
- `from_dict()` classmethod for deserialization

**Entry Point Registration** (from `pyproject.toml:47-51`):
- Format: `command-name = "module.path:function_name"`
- All entry points point to functions in `cli.py`
- Function signature: `def main_*() -> int`

## Desired End State

Users can define named sprints containing specific issue IDs and execute them as a unit using either sequential (`ll-auto`) or parallel (`ll-parallel`) mode.

### CLI Interface
```bash
# Create a sprint
$ ll-sprint create sprint-1 --issues BUG-001,FEAT-010 --description "Q1 fixes"

# Run sequentially
$ ll-sprint run sprint-1

# Run in parallel
$ ll-sprint run sprint-1 --parallel

# List sprints
$ ll-sprint list

# Show sprint details
$ ll-sprint show sprint-1

# Delete a sprint
$ ll-sprint delete sprint-1
```

### YAML Format (.sprints/<name>.yaml)
```yaml
name: sprint-1
description: "Q1 Performance and Security Improvements"
created: "2026-01-14T00:00:00Z"
issues:
  - BUG-001
  - BUG-002
  - FEAT-010
  - FEAT-015
options:
  mode: auto  # auto (sequential) or parallel
  max_iterations: 100
  timeout: 3600
  max_workers: 4
```

### How to Verify
- `ll-sprint create` creates valid YAML files in `.sprints/`
- `ll-sprint show` validates issue IDs exist before displaying
- `ll-sprint run` executes issues using existing `AutoManager` or `ParallelOrchestrator`
- `ll-sprint run --parallel` executes issues in parallel mode
- CLI tests verify argument parsing
- Integration test verifies end-to-end sprint execution

## What We're NOT Doing

- **Not modifying ll-auto or ll-parallel** - Reusing them as-is via subprocess or direct import
- **Not implementing dependency resolution** - Deferred to ENH-016/ENH-017
- **Not adding sprint scheduling/cron** - Out of scope, manual execution only
- **Not implementing sprint templates** - Simple YAML creation is sufficient
- **Not adding collaborative features** - No sharing, locking, or multi-user support
- **Not refactoring existing CLI structure** - Following established patterns as-is

## Problem Analysis

The current workflow requires users to remember and manually specify issue IDs each time:

```bash
# Current: Must remember and type issue IDs every time
ll-auto --only BUG-001,BUG-002,FEAT-010,FEAT-015

# Desired: Define once, execute by name
ll-sprint create sprint-1 --issues BUG-001,BUG-002,FEAT-010,FEAT-015
ll-sprint run sprint-1
```

This creates friction for:
1. **Sprint planning** - No way to pre-define a sprint backlog
2. **Replayability** - Can't easily re-run the same set of issues
3. **Team coordination** - Can't share sprint definitions via git

## Solution Approach

1. **Create SprintManager module** - Handle sprint YAML CRUD operations
2. **Add ll-sprint CLI** - New entry point with subcommands
3. **Reuse execution engines** - Call `AutoManager` or `ParallelOrchestrator` via Python API
4. **Validate issue IDs** - Check issues exist before sprint execution

The implementation integrates with existing components rather than modifying them:
- Sprint YAML files stored in `.sprints/` directory
- Execution delegated to `AutoManager` (sequential) or `ParallelOrchestrator` (parallel)
- Configuration read from existing `BRConfig`

## Implementation Phases

### Phase 1: Create Sprint Data Module

**Overview**: Define the `Sprint` dataclass and `SprintManager` class for sprint CRUD operations.

**Changes Required**

**File**: `scripts/little_loops/sprint.py` (new)
**Changes**: Create new module with Sprint dataclass and SprintManager

```python
"""Sprint and sequence management for issue execution."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import yaml

from little_loops.config import BRConfig


@dataclass
class SprintOptions:
    """Execution options for sprint runs."""

    mode: str = "auto"  # "auto" for sequential, "parallel" for concurrent
    max_iterations: int = 100
    timeout: int = 3600
    max_workers: int = 4

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        return {
            "mode": self.mode,
            "max_iterations": self.max_iterations,
            "timeout": self.timeout,
            "max_workers": self.max_workers,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "SprintOptions":
        """Create from dictionary."""
        if data is None:
            return cls()
        return cls(
            mode=data.get("mode", "auto"),
            max_iterations=data.get("max_iterations", 100),
            timeout=data.get("timeout", 3600),
            max_workers=data.get("max_workers", 4),
        )


@dataclass
class Sprint:
    """A sprint is a named group of issues to execute together.

    Attributes:
        name: Sprint identifier (used as filename)
        description: Human-readable purpose
        issues: List of issue IDs (e.g., BUG-001, FEAT-010)
        created: ISO 8601 timestamp
        options: Execution options (mode, timeout, etc.)
    """

    name: str
    description: str
    issues: list[str]
    created: str
    options: SprintOptions | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        data = {
            "name": self.name,
            "description": self.description,
            "created": self.created,
            "issues": self.issues,
        }
        if self.options:
            data["options"] = self.options.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Sprint":
        """Create from dictionary (YAML deserialization)."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            issues=data.get("issues", []),
            created=data.get("created", datetime.now(timezone.utc).isoformat()),
            options=SprintOptions.from_dict(data.get("options")),
        )

    def save(self, sprints_dir: Path) -> Path:
        """Save sprint to YAML file.

        Args:
            sprints_dir: Directory containing sprint definitions

        Returns:
            Path to saved file
        """
        sprints_dir.mkdir(parents=True, exist_ok=True)
        sprint_path = sprints_dir / f"{self.name}.yaml"
        with open(sprint_path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)
        return sprint_path

    @classmethod
    def load(cls, sprints_dir: Path, name: str) -> "Sprint | None":
        """Load sprint from YAML file.

        Args:
            sprints_dir: Directory containing sprint definitions
            name: Sprint name (without .yaml extension)

        Returns:
            Sprint instance or None if not found
        """
        sprint_path = sprints_dir / f"{name}.yaml"
        if not sprint_path.exists():
            return None
        with open(sprint_path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)


class SprintManager:
    """Manager for sprint CRUD operations.

    Provides methods to create, load, list, and delete sprint definitions.
    Also validates that issue IDs exist before executing sprints.
    """

    def __init__(self, sprints_dir: Path | None = None, config: BRConfig | None = None):
        """Initialize SprintManager.

        Args:
            sprints_dir: Directory for sprint definitions (default: .sprints/)
            config: Project configuration for issue validation
        """
        self.sprints_dir = sprints_dir or Path(".sprints")
        self.config = config
        self.sprints_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        name: str,
        issues: list[str],
        description: str = "",
        options: SprintOptions | None = None,
    ) -> Sprint:
        """Create a new sprint.

        Args:
            name: Sprint identifier
            issues: List of issue IDs
            description: Human-readable description
            options: Optional execution options

        Returns:
            Created Sprint instance
        """
        sprint = Sprint(
            name=name,
            description=description,
            issues=[i.strip().upper() for i in issues],
            created=datetime.now(timezone.utc).isoformat(),
            options=options,
        )
        sprint.save(self.sprints_dir)
        return sprint

    def load(self, name: str) -> Sprint | None:
        """Load a sprint by name.

        Args:
            name: Sprint name

        Returns:
            Sprint instance or None if not found
        """
        return Sprint.load(self.sprints_dir, name)

    def list(self) -> list[Sprint]:
        """List all sprints.

        Returns:
            List of Sprint instances, sorted by name
        """
        sprints = []
        for path in sorted(self.sprints_dir.glob("*.yaml")):
            sprint = Sprint.load(self.sprints_dir, path.stem)
            if sprint:
                sprints.append(sprint)
        return sprints

    def delete(self, name: str) -> bool:
        """Delete a sprint.

        Args:
            name: Sprint name

        Returns:
            True if deleted, False if not found
        """
        sprint_path = self.sprints_dir / f"{name}.yaml"
        if not sprint_path.exists():
            return False
        sprint_path.unlink()
        return True

    def validate_issues(self, issues: list[str]) -> dict[str, Path]:
        """Validate that issue IDs exist.

        Args:
            issues: List of issue IDs to validate

        Returns:
            Dictionary mapping valid issue IDs to their file paths
        """
        if not self.config:
            # No config provided, skip validation
            return {}

        valid = {}
        for issue_id in issues:
            for category in ["bugs", "features", "enhancements"]:
                issue_dir = self.config.get_issue_dir(category)
                for path in issue_dir.glob(f"*-{issue_id}-*.md"):
                    valid[issue_id] = path
                    break
                if issue_id in valid:
                    break
        return valid
```

**Success Criteria**

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/sprint.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/sprint.py`

---

### Phase 2: Add CLI Entry Point

**Overview**: Add `main_sprint()` function to `cli.py` with create, run, list, show, delete subcommands.

**Changes Required**

**File**: `scripts/little_loops/cli.py`
**Changes**: Add `main_sprint()` function after `main_loop()` (around line 914)

```python
def main_sprint() -> int:
    """Entry point for ll-sprint command.

    Manage and execute sprint/sequence definitions.

    Returns:
        Exit code (0 = success)
    """
    from little_loops.config import BRConfig
    from little_loops.issue_manager import AutoManager
    from little_loops.logger import Logger
    from little_loops.parallel.orchestrator import ParallelOrchestrator
    from little_loops.parallel.types import ParallelConfig
    from little_loops.sprint import SprintManager, SprintOptions
    from little_loops.logo import print_logo

    parser = argparse.ArgumentParser(
        prog="ll-sprint",
        description="Manage and execute sprint/sequence definitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s create sprint-1 --issues BUG-001,FEAT-010 --description "Q1 fixes"
  %(prog)s run sprint-1
  %(prog)s run sprint-1 --parallel
  %(prog)s run sprint-1 --dry-run
  %(prog)s list
  %(prog)s show sprint-1
  %(prog)s delete sprint-1
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create subcommand
    create_parser = subparsers.add_parser("create", help="Create a new sprint")
    create_parser.add_argument("name", help="Sprint name (used as filename)")
    create_parser.add_argument(
        "--issues",
        required=True,
        help="Comma-separated issue IDs (e.g., BUG-001,FEAT-010)",
    )
    create_parser.add_argument(
        "--description", "-d", default="", help="Sprint description"
    )
    create_parser.add_argument(
        "--mode",
        choices=["auto", "parallel"],
        default="auto",
        help="Default execution mode (default: auto)",
    )
    create_parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Default max workers for parallel mode (default: 4)",
    )
    create_parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Default timeout in seconds (default: 3600)",
    )

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Execute a sprint")
    run_parser.add_argument("sprint", help="Sprint name to execute")
    run_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Execute in parallel mode (overrides sprint default)",
    )
    run_parser.add_argument(
        "--dry-run", "-n", action="store_true", help="Show execution plan without running"
    )
    run_parser.add_argument(
        "--max-workers",
        type=int,
        help="Override max workers for parallel mode",
    )
    run_parser.add_argument(
        "--timeout", type=int, help="Override timeout in seconds"
    )
    run_parser.add_argument(
        "--config", type=Path, default=None, help="Path to project root"
    )

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List all sprints")
    list_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed information"
    )

    # show subcommand
    show_parser = subparsers.add_parser("show", help="Show sprint details")
    show_parser.add_argument("sprint", help="Sprint name to show")
    show_parser.add_argument(
        "--config", type=Path, default=None, help="Path to project root"
    )

    # delete subcommand
    delete_parser = subparsers.add_parser("delete", help="Delete a sprint")
    delete_parser.add_argument("sprint", help="Sprint name to delete")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Commands that don't need project root
    if args.command == "list":
        return cmd_sprint_list(args, SprintManager())
    if args.command == "delete":
        return cmd_sprint_delete(args, SprintManager())

    # Commands that need project root
    project_root = args.config if hasattr(args, "config") and args.config else Path.cwd()
    config = BRConfig(project_root)
    manager = SprintManager(config=config)

    if args.command == "create":
        return cmd_sprint_create(args, manager)
    if args.command == "show":
        return cmd_sprint_show(args, manager)
    if args.command == "run":
        return cmd_sprint_run(args, manager, config)

    return 1


def cmd_sprint_create(args: argparse.Namespace, manager: SprintManager) -> int:
    """Create a new sprint."""
    from little_loops.logger import logger

    issues = [i.strip().upper() for i in args.issues.split(",")]

    # Validate issues exist
    valid = manager.validate_issues(issues)
    invalid = set(issues) - set(valid.keys())

    if invalid:
        logger.warning(f"Issue IDs not found: {', '.join(sorted(invalid))}")

    options = SprintOptions(
        mode=args.mode,
        max_workers=args.max_workers,
        timeout=args.timeout,
    )

    sprint = manager.create(
        name=args.name,
        issues=issues,
        description=args.description,
        options=options,
    )

    logger.success(f"Created sprint: {sprint.name}")
    logger.info(f"  Description: {sprint.description or '(none)'}")
    logger.info(f"  Issues: {', '.join(sprint.issues)}")
    logger.info(f"  Mode: {sprint.options.mode if sprint.options else 'auto'}")
    logger.info(f"  File: .sprints/{sprint.name}.yaml")

    if invalid:
        logger.warning(f"  Invalid issues: {', '.join(sorted(invalid))}")

    return 0


def cmd_sprint_show(args: argparse.Namespace, manager: SprintManager) -> int:
    """Show sprint details."""
    from little_loops.logger import logger

    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Validate issues
    valid = manager.validate_issues(sprint.issues)
    invalid = set(sprint.issues) - set(valid.keys())

    print(f"Sprint: {sprint.name}")
    print(f"Description: {sprint.description or '(none)'}")
    print(f"Created: {sprint.created}")
    print(f"Issues ({len(sprint.issues)}):")

    for issue_id in sprint.issues:
        status = "valid" if issue_id in valid else "NOT FOUND"
        print(f"  - {issue_id} ({status})")

    if sprint.options:
        print(f"Options:")
        print(f"  Mode: {sprint.options.mode}")
        print(f"  Max iterations: {sprint.options.max_iterations}")
        print(f"  Timeout: {sprint.options.timeout}s")
        print(f"  Max workers: {sprint.options.max_workers}")

    if invalid:
        print(f"\nWarning: {len(invalid)} issue(s) not found")

    return 0


def cmd_sprint_list(args: argparse.Namespace, manager: SprintManager) -> int:
    """List all sprints."""
    sprints = manager.list()

    if not sprints:
        print("No sprints defined")
        return 0

    print(f"Available sprints ({len(sprints)}):")

    for sprint in sprints:
        if args.verbose:
            print(f"\n{sprint.name}:")
            print(f"  Description: {sprint.description or '(none)'}")
            print(f"  Issues: {', '.join(sprint.issues)}")
            print(f"  Created: {sprint.created}")
        else:
            desc = f" - {sprint.description}" if sprint.description else ""
            print(f"  {sprint.name}{desc}")

    return 0


def cmd_sprint_delete(args: argparse.Namespace, manager: SprintManager) -> int:
    """Delete a sprint."""
    from little_loops.logger import logger

    if not manager.delete(args.sprint):
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    logger.success(f"Deleted sprint: {args.sprint}")
    return 0


def cmd_sprint_run(
    args: argparse.Namespace,
    manager: SprintManager,
    config: BRConfig,
) -> int:
    """Execute a sprint."""
    from little_loops.logger import logger
    from little_loops.logo import print_logo

    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Validate issues exist
    valid = manager.validate_issues(sprint.issues)
    invalid = set(sprint.issues) - set(valid.keys())

    if invalid:
        logger.error(f"Issue IDs not found: {', '.join(sorted(invalid))}")
        logger.info("Cannot execute sprint with missing issues")
        return 1

    # Determine execution mode
    parallel = args.parallel or (sprint.options and sprint.options.mode == "parallel")

    print_logo()

    logger.info(f"Running sprint: {sprint.name}")
    logger.info(f"  Mode: {'parallel' if parallel else 'sequential'}")
    logger.info(f"  Issues: {', '.join(sprint.issues)}")

    if args.dry_run:
        logger.info("\nDry run mode - no changes will be made")
        return 0

    # Build only_ids set for filtering
    only_ids = set(sprint.issues)

    if parallel:
        # Execute via ParallelOrchestrator
        max_workers = args.max_workers or (sprint.options.max_workers if sprint.options else 4)
        timeout = args.timeout or (sprint.options.timeout if sprint.options else 3600)

        parallel_config = config.create_parallel_config(
            max_workers=max_workers,
            timeout=timeout,
            only_ids=only_ids,
            dry_run=args.dry_run,
        )

        orchestrator = ParallelOrchestrator(config=parallel_config, repo_path=Path.cwd())
        return orchestrator.run()
    else:
        # Execute via AutoManager
        manager = AutoManager(
            config=config,
            dry_run=args.dry_run,
            only_ids=only_ids,
        )
        return manager.run()
```

**Success Criteria**

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -k sprint -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`

**Manual Verification**:
- [ ] `ll-sprint --help` displays help message
- [ ] `ll-sprint create --help` shows create subcommand options
- [ ] `ll-sprint list` works without project config
- [ ] Invalid arguments produce helpful error messages

---

### Phase 3: Register Entry Point

**Overview**: Add `ll-sprint` entry point to `pyproject.toml`.

**Changes Required**

**File**: `scripts/pyproject.toml`
**Changes**: Add `ll-sprint` entry point after `ll-loop` (line 51)

```toml
[project.scripts]
ll-auto = "little_loops.cli:main_auto"
ll-parallel = "little_loops.cli:main_parallel"
ll-messages = "little_loops.cli:main_messages"
ll-loop = "little_loops.cli:main_loop"
ll-sprint = "little_loops.cli:main_sprint"
```

**Success Criteria**

**Automated Verification**:
- [ ] Installation succeeds: `pip install -e scripts/`
- [ ] Command available: `ll-sprint --help` runs from any directory
- [ ] All entry points work: `ll-auto --help`, `ll-parallel --help`, etc.

---

### Phase 4: Add Tests

**Overview**: Create tests for sprint module and CLI commands.

**Changes Required**

**File**: `scripts/tests/test_sprint.py` (new)
**Changes**: Create comprehensive test suite

```python
"""Tests for sprint module."""

import json
from pathlib import Path
from datetime import datetime, timezone
import pytest

from little_loops.sprint import Sprint, SprintManager, SprintOptions
from little_loops.config import BRConfig


class TestSprintOptions:
    """Tests for SprintOptions dataclass."""

    def test_default_values(self) -> None:
        """Default values are correct."""
        options = SprintOptions()
        assert options.mode == "auto"
        assert options.max_iterations == 100
        assert options.timeout == 3600
        assert options.max_workers == 4

    def test_custom_values(self) -> None:
        """Custom values are set correctly."""
        options = SprintOptions(
            mode="parallel",
            max_iterations=200,
            timeout=7200,
            max_workers=8,
        )
        assert options.mode == "parallel"
        assert options.max_iterations == 200
        assert options.timeout == 7200
        assert options.max_workers == 8

    def test_to_dict(self) -> None:
        """Serialization to dict works."""
        options = SprintOptions(mode="parallel", max_workers=8)
        data = options.to_dict()
        assert data == {
            "mode": "parallel",
            "max_iterations": 100,
            "timeout": 3600,
            "max_workers": 8,
        }

    def test_from_dict(self) -> None:
        """Deserialization from dict works."""
        data = {
            "mode": "parallel",
            "max_iterations": 200,
            "timeout": 7200,
            "max_workers": 8,
        }
        options = SprintOptions.from_dict(data)
        assert options.mode == "parallel"
        assert options.max_iterations == 200
        assert options.timeout == 7200
        assert options.max_workers == 8

    def test_from_dict_none(self) -> None:
        """None input returns defaults."""
        options = SprintOptions.from_dict(None)
        assert options.mode == "auto"
        assert options.max_workers == 4


class TestSprint:
    """Tests for Sprint dataclass."""

    def test_creation(self) -> None:
        """Sprint can be created with required fields."""
        sprint = Sprint(
            name="test-sprint",
            description="Test sprint",
            issues=["BUG-001", "FEAT-010"],
            created="2026-01-14T00:00:00Z",
        )
        assert sprint.name == "test-sprint"
        assert sprint.description == "Test sprint"
        assert sprint.issues == ["BUG-001", "FEAT-010"]
        assert sprint.options is None

    def test_with_options(self) -> None:
        """Sprint can include options."""
        options = SprintOptions(mode="parallel")
        sprint = Sprint(
            name="test-sprint",
            description="Test sprint",
            issues=["BUG-001"],
            created="2026-01-14T00:00:00Z",
            options=options,
        )
        assert sprint.options is not None
        assert sprint.options.mode == "parallel"

    def test_to_dict(self) -> None:
        """Serialization includes all fields."""
        options = SprintOptions(mode="parallel", max_workers=8)
        sprint = Sprint(
            name="test-sprint",
            description="Test",
            issues=["BUG-001"],
            created="2026-01-14T00:00:00Z",
            options=options,
        )
        data = sprint.to_dict()
        assert data["name"] == "test-sprint"
        assert data["description"] == "Test"
        assert data["issues"] == ["BUG-001"]
        assert data["options"]["mode"] == "parallel"
        assert data["options"]["max_workers"] == 8

    def test_to_dict_no_options(self) -> None:
        """Serialization without options omits options key."""
        sprint = Sprint(
            name="test-sprint",
            description="Test",
            issues=["BUG-001"],
            created="2026-01-14T00:00:00Z",
        )
        data = sprint.to_dict()
        assert "options" not in data

    def test_from_dict(self) -> None:
        """Deserialization from dict works."""
        data = {
            "name": "test-sprint",
            "description": "Test sprint",
            "issues": ["BUG-001", "FEAT-010"],
            "created": "2026-01-14T00:00:00Z",
            "options": {
                "mode": "parallel",
                "max_workers": 8,
            },
        }
        sprint = Sprint.from_dict(data)
        assert sprint.name == "test-sprint"
        assert sprint.issues == ["BUG-001", "FEAT-010"]
        assert sprint.options is not None
        assert sprint.options.mode == "parallel"
        assert sprint.options.max_workers == 8

    def test_from_dict_defaults(self) -> None:
        """Deserialization fills in missing fields."""
        data = {
            "name": "test-sprint",
            "issues": ["BUG-001"],
        }
        sprint = Sprint.from_dict(data)
        assert sprint.name == "test-sprint"
        assert sprint.description == ""
        assert sprint.issues == ["BUG-001"]
        assert sprint.options is None

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Save and load round-trip works."""
        sprint = Sprint(
            name="test-sprint",
            description="Test sprint",
            issues=["BUG-001", "FEAT-010"],
            created="2026-01-14T00:00:00Z",
            options=SprintOptions(mode="parallel"),
        )

        # Save
        saved_path = sprint.save(tmp_path)
        assert saved_path.exists()
        assert saved_path.name == "test-sprint.yaml"

        # Load
        loaded = Sprint.load(tmp_path, "test-sprint")
        assert loaded is not None
        assert loaded.name == "test-sprint"
        assert loaded.issues == ["BUG-001", "FEAT-010"]
        assert loaded.options is not None
        assert loaded.options.mode == "parallel"

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        """Loading non-existent sprint returns None."""
        loaded = Sprint.load(tmp_path, "nonexistent")
        assert loaded is None


class TestSprintManager:
    """Tests for SprintManager."""

    def test_init_default_dir(self, tmp_path: Path) -> None:
        """Default initialization creates .sprints directory."""
        manager = SprintManager(sprints_dir=tmp_path / ".sprints")
        assert manager.sprints_dir.exists()
        assert manager.sprints_dir.is_dir()

    def test_create_sprint(self, tmp_path: Path) -> None:
        """Creating a sprint writes YAML file."""
        manager = SprintManager(sprints_dir=tmp_path)
        sprint = manager.create(
            name="test-sprint",
            issues=["BUG-001", "FEAT-010"],
            description="Test sprint",
        )

        assert sprint.name == "test-sprint"
        assert sprint.issues == ["BUG-001", "FEAT-010"]

        # Verify file exists
        sprint_path = tmp_path / "test-sprint.yaml"
        assert sprint_path.exists()

    def test_load_sprint(self, tmp_path: Path) -> None:
        """Loading a sprint reads YAML file."""
        manager = SprintManager(sprints_dir=tmp_path)

        # Create first
        manager.create(
            name="test-sprint",
            issues=["BUG-001"],
            description="Test",
        )

        # Then load
        loaded = manager.load("test-sprint")
        assert loaded is not None
        assert loaded.name == "test-sprint"
        assert loaded.issues == ["BUG-001"]

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        """Loading non-existent sprint returns None."""
        manager = SprintManager(sprints_dir=tmp_path)
        loaded = manager.load("nonexistent")
        assert loaded is None

    def test_list_empty(self, tmp_path: Path) -> None:
        """Listing empty directory returns empty list."""
        manager = SprintManager(sprints_dir=tmp_path)
        sprints = manager.list()
        assert sprints == []

    def test_list_multiple(self, tmp_path: Path) -> None:
        """Listing returns all sprints sorted by name."""
        manager = SprintManager(sprints_dir=tmp_path)

        manager.create(name="zebra", issues=["BUG-003"])
        manager.create(name="alpha", issues=["BUG-001"])
        manager.create(name="beta", issues=["BUG-002"])

        sprints = manager.list()
        assert [s.name for s in sprints] == ["alpha", "beta", "zebra"]

    def test_delete_sprint(self, tmp_path: Path) -> None:
        """Deleting a sprint removes the file."""
        manager = SprintManager(sprints_dir=tmp_path)

        manager.create(name="test-sprint", issues=["BUG-001"])
        assert (tmp_path / "test-sprint.yaml").exists()

        result = manager.delete("test-sprint")
        assert result is True
        assert not (tmp_path / "test-sprint.yaml").exists()

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        """Deleting non-existent sprint returns False."""
        manager = SprintManager(sprints_dir=tmp_path)
        result = manager.delete("nonexistent")
        assert result is False

    def test_create_normalizes_issue_ids(self, tmp_path: Path) -> None:
        """Issue IDs are normalized to uppercase."""
        manager = SprintManager(sprints_dir=tmp_path)
        sprint = manager.create(
            name="test",
            issues=["bug-001", "FeAt-010"],  # Mixed case
        )
        assert sprint.issues == ["BUG-001", "FEAT-010"]

    def test_validate_issues_without_config(self, tmp_path: Path) -> None:
        """Validation without config returns empty dict."""
        manager = SprintManager(sprints_dir=tmp_path, config=None)
        valid = manager.validate_issues(["BUG-001", "FEAT-010"])
        assert valid == {}

    def test_validate_issues_with_config(
        self, tmp_path: Path, sample_issues: dict[str, Path]
    ) -> None:
        """Validation with config finds existing issues."""
        # Setup: Create config and issues
        config = self._create_config_with_issues(tmp_path, sample_issues)
        manager = SprintManager(sprints_dir=tmp_path, config=config)

        valid = manager.validate_issues(["BUG-001", "FEAT-010", "NONEXISTENT"])

        assert "BUG-001" in valid
        assert "FEAT-010" in valid
        assert "NONEXISTENT" not in valid

    def _create_config_with_issues(self, tmp_path: Path, issues: dict[str, Path]) -> BRConfig:
        """Helper to create config with sample issues."""
        # Create issues directory structure
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        for category in ["bugs", "features", "enhancements"]:
            cat_dir = issues_dir / category
            cat_dir.mkdir()

        # Create config file
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_file = config_dir / "ll-config.json"
        config_data = {
            "project": {"name": "test", "src_dir": "src/"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
                },
                "completed_dir": "completed",
            },
        }

        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create sample issue files
        for issue_id, _ in issues.items():
            if issue_id.startswith("BUG"):
                cat_dir = issues_dir / "bugs"
            elif issue_id.startswith("FEAT"):
                cat_dir = issues_dir / "features"
            else:
                cat_dir = issues_dir / "enhancements"

            issue_file = cat_dir / f"P1-{issue_id}-test.md"
            issue_file.write_text(f"# {issue_id}\n\nTest issue")

        return BRConfig(tmp_path)
```

**File**: `scripts/tests/test_cli.py` (append)
**Changes**: Add sprint CLI tests

```python
class TestSprintArgumentParsing:
    """Tests for ll-sprint argument parsing."""

    def _parse_sprint_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_sprint."""
        parser = argparse.ArgumentParser(prog="ll-sprint")
        subparsers = parser.add_subparsers(dest="command")

        # create
        create = subparsers.add_parser("create")
        create.add_argument("name")
        create.add_argument("--issues", required=True)
        create.add_argument("--description", "-d", default="")
        create.add_argument("--mode", choices=["auto", "parallel"], default="auto")
        create.add_argument("--max-workers", type=int, default=4)
        create.add_argument("--timeout", type=int, default=3600)

        # run
        run = subparsers.add_parser("run")
        run.add_argument("sprint")
        run.add_argument("--parallel", action="store_true")
        run.add_argument("--dry-run", "-n", action="store_true")
        run.add_argument("--max-workers", type=int)
        run.add_argument("--timeout", type=int)
        run.add_argument("--config", type=Path)

        # list
        list_parser = subparsers.add_parser("list")
        list_parser.add_argument("--verbose", "-v", action="store_true")

        # show
        show = subparsers.add_parser("show")
        show.add_argument("sprint")
        show.add_argument("--config", type=Path)

        # delete
        delete = subparsers.add_parser("delete")
        delete.add_argument("sprint")

        return parser.parse_args(args)

    def test_create_command(self) -> None:
        """create subcommand parses correctly."""
        args = self._parse_sprint_args(
            [
                "create",
                "sprint-1",
                "--issues",
                "BUG-001,FEAT-010",
                "--description",
                "Q1 fixes",
                "--mode",
                "parallel",
                "--max-workers",
                "8",
            ]
        )
        assert args.command == "create"
        assert args.name == "sprint-1"
        assert args.issues == "BUG-001,FEAT-010"
        assert args.description == "Q1 fixes"
        assert args.mode == "parallel"
        assert args.max_workers == 8

    def test_run_command(self) -> None:
        """run subcommand parses correctly."""
        args = self._parse_sprint_args(
            ["run", "sprint-1", "--parallel", "--dry-run", "--max-workers", "8"]
        )
        assert args.command == "run"
        assert args.sprint == "sprint-1"
        assert args.parallel is True
        assert args.dry_run is True
        assert args.max_workers == 8

    def test_run_sequential(self) -> None:
        """run without --parallel flag."""
        args = self._parse_sprint_args(["run", "sprint-1"])
        assert args.command == "run"
        assert args.sprint == "sprint-1"
        assert args.parallel is False

    def test_list_command(self) -> None:
        """list subcommand."""
        args = self._parse_sprint_args(["list", "--verbose"])
        assert args.command == "list"
        assert args.verbose is True

    def test_show_command(self) -> None:
        """show subcommand."""
        args = self._parse_sprint_args(
            ["show", "sprint-1", "--config", "/my/project"]
        )
        assert args.command == "show"
        assert args.sprint == "sprint-1"
        assert args.config == Path("/my/project")

    def test_delete_command(self) -> None:
        """delete subcommand."""
        args = self._parse_sprint_args(["delete", "sprint-1"])
        assert args.command == "delete"
        assert args.sprint == "sprint-1"

    def test_no_command(self) -> None:
        """No command shows help."""
        args = self._parse_sprint_args([])
        assert args.command is None
```

**Success Criteria**

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -k sprint -v`
- [ ] Coverage: `python -m pytest scripts/tests/test_sprint.py --cov=little_loops.sprint`

---

### Phase 5: Add Integration Test

**Overview**: Create end-to-end test verifying sprint execution workflow.

**Changes Required**

**File**: `scripts/tests/test_sprint_integration.py` (new)
**Changes**: Create integration test suite

```python
"""Integration tests for sprint execution."""

import json
from pathlib import Path
import pytest

from little_loops.sprint import SprintManager
from little_loops.config import BRConfig


@pytest.fixture
def sprint_project(tmp_path: Path) -> BRConfig:
    """Create a test project with issues and config."""
    # Create directory structure
    issues_dir = tmp_path / ".issues"
    issues_dir.mkdir()

    for category in ["bugs", "features", "enhancements", "completed"]:
        (issues_dir / category).mkdir()

    # Create config
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()

    config_file = config_dir / "ll-config.json"
    config_data = {
        "project": {
            "name": "test-project",
            "src_dir": "src/",
            "test_cmd": "pytest",
            "lint_cmd": "ruff check",
        },
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
            },
            "completed_dir": "completed",
        },
    }

    with open(config_file, "w") as f:
        json.dump(config_data, f)

    # Create sample issues
    (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
        "# BUG-001: Test Bug\n\nFix this bug."
    )
    (issues_dir / "features" / "P2-FEAT-010-test-feature.md").write_text(
        "# FEAT-010: Test Feature\n\nImplement this feature."
    )

    return BRConfig(tmp_path)


def test_sprint_lifecycle(sprint_project: BRConfig, tmp_path: Path) -> None:
    """Test full sprint lifecycle: create, list, show, delete."""
    manager = SprintManager(sprints_dir=tmp_path, config=sprint_project)

    # Create sprint
    sprint = manager.create(
        name="test-sprint",
        issues=["BUG-001", "FEAT-010"],
        description="Test sprint",
    )

    assert sprint.name == "test-sprint"
    assert len(sprint.issues) == 2

    # List sprints
    sprints = manager.list()
    assert len(sprints) == 1
    assert sprints[0].name == "test-sprint"

    # Show sprint
    loaded = manager.load("test-sprint")
    assert loaded is not None
    assert loaded.issues == ["BUG-001", "FEAT-010"]

    # Validate issues
    valid = manager.validate_issues(loaded.issues)
    assert "BUG-001" in valid
    assert "FEAT-010" in valid

    # Delete sprint
    result = manager.delete("test-sprint")
    assert result is True

    # Verify deleted
    sprints = manager.list()
    assert len(sprints) == 0


def test_sprint_validation_invalid_issues(sprint_project: BRConfig, tmp_path: Path) -> None:
    """Test sprint validation with invalid issue IDs."""
    manager = SprintManager(sprints_dir=tmp_path, config=sprint_project)

    # Create sprint with mix of valid and invalid issues
    sprint = manager.create(
        name="test-sprint",
        issues=["BUG-001", "NONEXISTENT", "FEAT-010"],
    )

    # Validate
    valid = manager.validate_issues(sprint.issues)

    # Only BUG-001 and FEAT-010 should be valid
    assert "BUG-001" in valid
    assert "FEAT-010" in valid
    assert "NONEXISTENT" not in valid


def test_sprint_yaml_format(sprint_project: BRConfig, tmp_path: Path) -> None:
    """Test sprint YAML file format matches specification."""
    manager = SprintManager(sprints_dir=tmp_path, config=sprint_project)

    sprint = manager.create(
        name="test-sprint",
        issues=["BUG-001"],
        description="Test sprint",
    )

    # Read YAML file
    yaml_path = tmp_path / "test-sprint.yaml"
    content = yaml_path.read_text()

    # Verify structure
    assert "name: test-sprint" in content
    assert "description: Test sprint" in content
    assert "issues:" in content
    assert "- BUG-001" in content
    assert "created:" in content
```

**Success Criteria**

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint_integration.py -v`
- [ ] Full test suite passes: `python -m pytest scripts/tests/`

---

### Phase 6: Add .gitignore Entry

**Overview**: Add `.sprints/` directory to project .gitignore (if desired by user).

**Changes Required**

**File**: `.gitignore` (or `scripts/.gitignore` if package-specific)
**Changes**: Add entry for `.sprints/` directory

```
# Sprint definitions (optional - remove if tracking sprints in git)
.sprints/
```

**Success Criteria**

**Automated Verification**:
- [ ] Git status shows `.sprints/` as ignored after creating a sprint
- [ ] `git check-ignore .sprints/` confirms the pattern

---

## Testing Strategy

### Unit Tests
- `SprintOptions` dataclass serialization/deserialization
- `Sprint` dataclass serialization/deserialization
- `SprintManager` CRUD operations
- CLI argument parsing for all subcommands

### Integration Tests
- Full sprint lifecycle (create, list, show, delete)
- Issue validation with real project structure
- YAML file format verification
- Sprint execution (mocked, not actual ll-auto/ll-parallel runs)

### Manual Testing
- Create sprint via CLI
- List sprints
- Show sprint details
- Run sprint (dry-run mode)
- Delete sprint

## References

- Original issue: `.issues/features/P3-FEAT-050-sprint-and-sequence-execution.md`
- Slash command: `.claude/commands/ll_create_sprint.md`
- CLI pattern: `scripts/little_loops/cli.py:412-913` (ll-loop)
- YAML pattern: `scripts/little_loops/fsm/validation.py:294-345`
- Dataclass pattern: `scripts/little_loops/config.py:30-101`
- Entry points: `scripts/pyproject.toml:47-51`
- Sequential execution: `scripts/little_loops/issue_manager.py:193` (AutoManager)
- Parallel execution: `scripts/little_loops/parallel/orchestrator.py:34` (ParallelOrchestrator)
