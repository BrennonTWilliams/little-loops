---
discovered_commit: 51dcccd702a7f8947c624a914f353b8ec65cf55f
discovered_branch: main
discovered_date: 2026-02-10
discovered_by: audit_architecture
focus_area: patterns
---

# FEAT-411: Add abstract base classes for CLI commands

## Summary

Architectural improvement found by `/ll:audit_architecture`. Add abstract base classes to enable plugin architecture and improve extensibility for CLI commands.

## Location

- **New files**: `scripts/little_loops/cli/base.py`
- **Affected files**: All CLI command modules after ENH-309 is completed
- **Module**: `little_loops.cli`

## Motivation

### Current State

CLI commands are implemented as standalone functions (main_auto, main_parallel, etc.) with no common interface or contract. This makes it difficult to:
- Add new CLI commands via plugins
- Share common functionality across commands
- Test commands with mock implementations
- Validate command implementations

### Proposed State

Define abstract base classes that CLI commands can inherit from, establishing a clear contract and enabling extensibility.

## Proposed Solution

### 1. Create Base Command ABC

```python
# scripts/little_loops/cli/base.py
"""Base classes for CLI commands."""

from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from typing import Any

from little_loops.config import BRConfig
from little_loops.logger import Logger


class CLICommand(ABC):
    """Abstract base class for CLI commands.

    Provides common infrastructure for argument parsing,
    configuration loading, and logging.
    """

    def __init__(self) -> None:
        self.config: BRConfig | None = None
        self.logger: Logger | None = None

    @abstractmethod
    def get_name(self) -> str:
        """Return the command name (e.g., 'auto', 'parallel')."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Return the command description for help text."""
        pass

    @abstractmethod
    def configure_parser(self, parser: ArgumentParser) -> None:
        """Configure the argument parser with command-specific arguments."""
        pass

    @abstractmethod
    def execute(self, args: Namespace) -> int:
        """Execute the command with parsed arguments.

        Returns:
            Exit code (0 = success, non-zero = error)
        """
        pass

    def run(self, argv: list[str] | None = None) -> int:
        """Main entry point that handles parsing and execution.

        Args:
            argv: Command-line arguments (None = sys.argv)

        Returns:
            Exit code (0 = success)
        """
        parser = ArgumentParser(
            description=self.get_description(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        self.configure_parser(parser)
        args = parser.parse_args(argv)

        # Load config if not set
        if self.config is None:
            self.config = BRConfig.load(args.config if hasattr(args, 'config') else None)

        # Initialize logger if not set
        if self.logger is None:
            quiet = args.quiet if hasattr(args, 'quiet') else False
            self.logger = Logger(quiet=quiet)

        return self.execute(args)


class IssueProcessingCommand(CLICommand):
    """Base class for commands that process issues.

    Provides common functionality for issue-based workflows
    like ll-auto, ll-parallel, and ll-sprint.
    """

    @abstractmethod
    def get_issues(self, args: Namespace) -> list[Any]:
        """Get the list of issues to process."""
        pass

    @abstractmethod
    def process_issue(self, issue: Any, args: Namespace) -> bool:
        """Process a single issue.

        Returns:
            True if successful, False otherwise
        """
        pass
```

### 2. Refactor Existing Commands

After ENH-309 is complete, refactor commands to inherit from base classes:

```python
# scripts/little_loops/cli/auto.py
from little_loops.cli.base import IssueProcessingCommand

class AutoCommand(IssueProcessingCommand):
    def get_name(self) -> str:
        return "auto"

    def get_description(self) -> str:
        return "Automated sequential issue management with Claude CLI"

    def configure_parser(self, parser: ArgumentParser) -> None:
        add_common_auto_args(parser)
        parser.add_argument("--category", "-c", ...)

    def execute(self, args: Namespace) -> int:
        # Implementation from current main_auto
        ...

def main_auto() -> int:
    """Entry point for ll-auto command."""
    return AutoCommand().run()
```

### 3. Enable Plugin Discovery

```python
# scripts/little_loops/cli/registry.py
"""CLI command registry for plugin discovery."""

from typing import Type

from little_loops.cli.base import CLICommand

_REGISTRY: dict[str, Type[CLICommand]] = {}

def register_command(command_class: Type[CLICommand]) -> None:
    """Register a CLI command class."""
    cmd = command_class()
    _REGISTRY[cmd.get_name()] = command_class

def get_command(name: str) -> Type[CLICommand] | None:
    """Get a registered command class by name."""
    return _REGISTRY.get(name)

def list_commands() -> list[str]:
    """List all registered command names."""
    return sorted(_REGISTRY.keys())
```

## Implementation Steps

1. **Create base.py with ABCs** (depends on ENH-309)
2. **Refactor one command as proof of concept** (e.g., auto.py)
3. **Test refactored command** to ensure behavior unchanged
4. **Refactor remaining commands** incrementally
5. **Add plugin registry** for future extensibility
6. **Update documentation** with plugin development guide

## Impact Assessment

- **Severity**: Medium - Improves extensibility, no immediate functional change
- **Effort**: Small - Create ABCs, refactor commands to inherit
- **Risk**: Low - Additive change, can maintain backward compatibility
- **Breaking Change**: No - Existing entry points preserved

## Benefits

1. **Plugin architecture** - Third parties can add new commands
2. **Consistent interface** - All commands follow same pattern
3. **Shared functionality** - Common logic in base classes
4. **Better testability** - Mock implementations via ABCs
5. **Type safety** - Protocol enforcement via abstract methods

## Dependencies

- **Blocks**: None
- **Blocked by**: ENH-309 (should split cli.py first for cleaner implementation)

## Labels

`feature`, `architecture`, `extensibility`, `auto-generated`, `design-pattern`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P3

---

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID
- scripts/little_loops/cli/base.py does not exist — no ABCs implemented
- scripts/little_loops/cli/ package does not exist — still single cli.py file
- CLI commands remain as standalone functions (main_auto, main_parallel, etc.)
- Dependency ENH-309 not yet completed — implementation blocked

---

## Tradeoff Review Note

**Reviewed**: 2026-02-10 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | LOW |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | MEDIUM |
| Maintenance overhead | LOW |

### Recommendation
User selected "Update instead" of closure. This issue represents speculative architecture work with no immediate user benefit. The project already has working CLI commands; adding ABCs for "plugin architecture" that doesn't yet exist is premature abstraction. Consider reopening only after:
1. ENH-309 is completed (cli.py split)
2. There's actual demand for third-party CLI command plugins

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: 2026-02-11
- **Reason**: Low utility relative to implementation complexity

### Tradeoff Review Scores
- Utility: LOW
- Implementation Effort: MEDIUM
- Complexity Added: MEDIUM
- Technical Debt Risk: MEDIUM
- Maintenance Overhead: LOW

### Rationale
Premature abstraction. No current demand for third-party CLI command plugins. The project has working CLI commands; adding ABCs for a plugin architecture that doesn't exist is speculative. Reopen only after ENH-309 is completed AND there's actual demand for CLI plugins.
