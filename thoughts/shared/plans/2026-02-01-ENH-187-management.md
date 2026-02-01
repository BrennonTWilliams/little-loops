# ENH-187: Create shared CLI argument module - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-187-create-shared-cli-argument-module.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Research Findings

### Key Discoveries
- Common arguments are duplicated across `main_auto()` (lines 45-132), `main_parallel()` (lines 135-331), and `main_sprint()` (lines 1333-1454) in `scripts/little_loops/cli.py`
- Test file exists at `scripts/tests/test_cli.py` with tests for argument parsing
- Entry points configured in `scripts/pyproject.toml` at lines 47-54

### Current State
- Each CLI tool defines its own argparse arguments with identical or similar definitions
- Arguments like `--dry-run/-n`, `--resume/-r`, `--config`, `--only`, `--skip`, `--max-workers/-w`, `--timeout/-t` are repeated
- Help text varies slightly between tools for the same argument
- Comma-separated parsing for `--only`/`--skip` is duplicated: `{i.strip().upper() for i in args.only.split(",")}`

### Patterns to Follow
- `scripts/little_loops/logger.py` - Simple utility module with class and standalone functions
- `scripts/little_loops/subprocess_utils.py` - Shared utilities with type aliases and clear docstrings
- Test pattern from `scripts/tests/test_cli.py` - Tests organized by class per command

### Potential Concerns
- Need to preserve exact argument behavior (no functional changes)
- Some tools have tool-specific arguments that should not be shared
- Help text differences may need to be standardized or parameterized

## Desired End State

A new module `scripts/little_loops/cli_args.py` containing:
1. Helper functions to add common argument groups to argparse parsers
2. Helper functions to parse comma-separated issue ID lists
3. Consistent help text and defaults across tools
4. Type hints and comprehensive docstrings

Each CLI entry point (`main_auto`, `main_parallel`, `main_sprint`) will import and use these shared functions.

### How to Verify
- All existing tests pass without modification
- CLI help output remains the same
- Argument parsing behavior is identical
- Code duplication in cli.py is reduced

## What We're NOT Doing

- Not changing any argument names, flags, or defaults
- Not changing functional behavior of any CLI tool
- Not adding new arguments
- Not refactoring `main_loop` or `main_messages` (different argument patterns)
- Not modifying the workflow_sequence_analyzer (separate entry point)

## Problem Analysis

The CLI tools `ll-auto`, `ll-parallel`, and `ll-sprint` define nearly identical arguments for:
- Dry-run mode (`--dry-run/-n`)
- Resume capability (`--resume/-r`)
- Config path (`--config`)
- Issue filtering (`--only`, `--skip`)
- Parallel execution (`--max-workers/-w`, `--timeout/-t`)

This duplication causes:
- Maintenance burden when updating arguments
- Inconsistent help text across tools
- Potential for subtle behavioral differences

## Solution Approach

Create a shared module with functions that:
1. Add argument groups to ArgumentParser instances
2. Parse common argument patterns (comma-separated issue IDs)
3. Provide consistent defaults and help text

## Implementation Phases

### Phase 1: Create cli_args.py module

#### Overview
Create the new shared module with all helper functions for adding CLI arguments.

#### Changes Required

**File**: `scripts/little_loops/cli_args.py` (NEW)

```python
"""Shared CLI argument definitions for little-loops tools.

Provides reusable functions for adding common command-line arguments
to argparse parsers, ensuring consistency across ll-auto, ll-parallel,
and ll-sprint commands.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable


def add_dry_run_arg(parser: argparse.ArgumentParser) -> None:
    """Add --dry-run/-n argument to parser."""
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be done without making changes",
    )


def add_resume_arg(parser: argparse.ArgumentParser) -> None:
    """Add --resume/-r argument to parser."""
    parser.add_argument(
        "--resume",
        "-r",
        action="store_true",
        help="Resume from previous checkpoint",
    )


def add_config_arg(parser: argparse.ArgumentParser) -> None:
    """Add --config argument to parser."""
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to project root (default: current directory)",
    )


def add_only_arg(parser: argparse.ArgumentParser) -> None:
    """Add --only argument for filtering specific issues."""
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to process (e.g., BUG-001,FEAT-002)",
    )


def add_skip_arg(parser: argparse.ArgumentParser, help_text: str | None = None) -> None:
    """Add --skip argument for excluding specific issues.

    Args:
        parser: The argument parser to add the argument to
        help_text: Optional custom help text. If not provided, uses default.
    """
    if help_text is None:
        help_text = "Comma-separated list of issue IDs to skip (e.g., BUG-003,FEAT-004)"
    parser.add_argument(
        "--skip",
        type=str,
        default=None,
        help=help_text,
    )


def add_max_workers_arg(parser: argparse.ArgumentParser, default: int | None = None) -> None:
    """Add --max-workers/-w argument for parallel execution.

    Args:
        parser: The argument parser to add the argument to
        default: Default value. If None, no default is specified.
    """
    if default is not None:
        parser.add_argument(
            "--max-workers",
            "-w",
            type=int,
            default=default,
            help=f"Maximum parallel workers (default: {default})",
        )
    else:
        parser.add_argument(
            "--max-workers",
            "-w",
            type=int,
            default=None,
            help="Maximum parallel workers",
        )


def add_timeout_arg(parser: argparse.ArgumentParser, default: int | None = None) -> None:
    """Add --timeout/-t argument for per-issue timeout.

    Args:
        parser: The argument parser to add the argument to
        default: Default value in seconds. If None, no default is specified.
    """
    if default is not None:
        parser.add_argument(
            "--timeout",
            "-t",
            type=int,
            default=default,
            help=f"Timeout in seconds (default: {default})",
        )
    else:
        parser.add_argument(
            "--timeout",
            "-t",
            type=int,
            default=None,
            help="Timeout in seconds",
        )


def add_quiet_arg(parser: argparse.ArgumentParser) -> None:
    """Add --quiet/-q argument to suppress output."""
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress non-essential output",
    )


def add_max_issues_arg(parser: argparse.ArgumentParser) -> None:
    """Add --max-issues/-m argument for limiting issues processed."""
    parser.add_argument(
        "--max-issues",
        "-m",
        type=int,
        default=0,
        help="Limit number of issues to process (0 = unlimited)",
    )


def parse_issue_ids(value: str | None) -> set[str] | None:
    """Parse comma-separated issue IDs into a set.

    Args:
        value: Comma-separated string like "BUG-001,FEAT-002" or None

    Returns:
        Set of uppercase issue IDs, or None if value is None

    Example:
        >>> parse_issue_ids("BUG-001,feat-002")
        {'BUG-001', 'FEAT-002'}
        >>> parse_issue_ids(None)
        None
    """
    if value is None:
        return None
    return {i.strip().upper() for i in value.split(",")}


def add_common_auto_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to ll-auto command.

    Adds: --resume, --dry-run, --max-issues, --only, --skip, --config
    """
    add_resume_arg(parser)
    add_dry_run_arg(parser)
    add_max_issues_arg(parser)
    add_only_arg(parser)
    add_skip_arg(parser)
    add_config_arg(parser)


def add_common_parallel_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to parallel execution tools.

    Adds: --dry-run, --resume, --max-workers, --timeout, --quiet, --only, --skip, --config
    """
    add_dry_run_arg(parser)
    add_resume_arg(parser)
    add_max_workers_arg(parser)
    add_timeout_arg(parser)
    add_quiet_arg(parser)
    add_only_arg(parser)
    add_skip_arg(parser)
    add_config_arg(parser)


__all__ = [
    "add_dry_run_arg",
    "add_resume_arg",
    "add_config_arg",
    "add_only_arg",
    "add_skip_arg",
    "add_max_workers_arg",
    "add_timeout_arg",
    "add_quiet_arg",
    "add_max_issues_arg",
    "parse_issue_ids",
    "add_common_auto_args",
    "add_common_parallel_args",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] Module can be imported: `python -c "from little_loops import cli_args"`
- [ ] Type checking passes: `python -m mypy scripts/little_loops/cli_args.py`
- [ ] Linting passes: `ruff check scripts/little_loops/cli_args.py`

---

### Phase 2: Update main_auto() to use shared arguments

#### Overview
Refactor `main_auto()` to import and use shared argument functions.

#### Changes Required

**File**: `scripts/little_loops/cli.py`

**Import at top**:
```python
from little_loops.cli_args import add_common_auto_args, parse_issue_ids
```

**Replace lines 68-111** in `main_auto()`:
```python
# Before (lines 68-111):
parser.add_argument("--resume", "-r", ...)
parser.add_argument("--dry-run", "-n", ...)
# ... 6 more argument definitions ...

# After:
add_common_auto_args(parser)

# Add --category and --max-issues (not in common)
parser.add_argument(
    "--category",
    "-c",
    type=str,
    default=None,
    help="Filter to specific category (bugs, features, enhancements)",
)
```

**Replace lines 119-120** (parsing logic):
```python
# Before:
only_ids = {i.strip().upper() for i in args.only.split(",")} if args.only else None
skip_ids = {i.strip().upper() for i in args.skip.split(",")} if args.skip else None

# After:
only_ids = parse_issue_ids(args.only)
skip_ids = parse_issue_ids(args.skip)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py::TestAutoArgumentParsing -v`
- [ ] Help output matches: `ll-auto --help` shows same arguments
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`

**Manual Verification**:
- [ ] Run `ll-auto --help` and verify all arguments present with correct help text
- [ ] Run `ll-auto --dry-run` and verify it still works

---

### Phase 3: Update main_parallel() to use shared arguments

#### Overview
Refactor `main_parallel()` to import and use shared argument functions.

#### Changes Required

**File**: `scripts/little_loops/cli.py`

**Update import**:
```python
from little_loops.cli_args import (
    add_common_auto_args,
    add_common_parallel_args,
    parse_issue_ids,
)
```

**Replace argument definitions at lines 159-270** in `main_parallel()`:
```python
# Common arguments:
add_common_parallel_args(parser)

# Parallel-specific arguments not in common:
parser.add_argument(
    "--workers",  # Note: using --workers not --max-workers for ll-parallel
    "-w",
    type=int,
    default=None,
    help="Number of parallel workers (default: from config or 2)",
)
parser.add_argument(
    "--priority",
    "-p",
    type=str,
    default=None,
    help="Comma-separated priorities to process (default: all)",
)
parser.add_argument(
    "--worktree-base",
    type=Path,
    default=None,
    help="Base directory for git worktrees",
)
parser.add_argument(
    "--cleanup",
    "-c",
    action="store_true",
    help="Clean up all worktrees and exit",
)
parser.add_argument(
    "--merge-pending",
    action="store_true",
    help="Attempt to merge pending work from previous interrupted runs",
)
parser.add_argument(
    "--clean-start",
    action="store_true",
    help="Remove all worktrees and start fresh (skip pending work check)",
)
parser.add_argument(
    "--ignore-pending",
    action="store_true",
    help="Report pending work but continue without merging",
)
parser.add_argument(
    "--stream-output",
    action="store_true",
    help="Stream Claude CLI subprocess output to console",
)
parser.add_argument(
    "--show-model",
    action="store_true",
    help="Make API call to verify and display model on worktree setup",
)
parser.add_argument(
    "--overlap-detection",
    action="store_true",
    help="Enable pre-flight overlap detection to reduce merge conflicts (ENH-143)",
)
parser.add_argument(
    "--warn-only",
    action="store_true",
    help="With --overlap-detection, warn about overlaps instead of serializing",
)
```

**Note**: `--workers/-w` in `main_parallel` is different from `--max-workers/-w` - we need to preserve this naming. The shared function adds `--max-workers`, but `main_parallel` uses `--workers`. We should keep `--workers` for backward compatibility and just not use the shared function for this specific argument.

**Replace lines 294-295** (parsing logic):
```python
# Before:
only_ids = {i.strip().upper() for i in args.only.split(",")} if args.only else None
skip_ids = {i.strip().upper() for i in args.skip.split(",")} if args.skip else None

# After:
only_ids = parse_issue_ids(args.only)
skip_ids = parse_issue_ids(args.skip)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py::TestParallelArgumentParsing -v`
- [ ] Help output matches: `ll-parallel --help` shows same arguments
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`

**Manual Verification**:
- [ ] Run `ll-parallel --help` and verify all arguments present
- [ ] Verify `--workers` (not `--max-workers`) is present

---

### Phase 4: Update main_sprint() to use shared arguments

#### Overview
Refactor `main_sprint()` subcommands to use shared argument functions.

#### Changes Required

**File**: `scripts/little_loops/cli.py`

**Update import** to include `add_dry_run_arg`, `add_resume_arg`, etc.

**For `create` subcommand (lines 1359-1386)**:
```python
# Use shared functions for common args:
add_max_workers_arg(create_parser, default=2)
add_timeout_arg(create_parser, default=3600)
add_skip_arg(create_parser, help_text="Comma-separated list of issue IDs to exclude from sprint (e.g., BUG-003,FEAT-004)")
```

**For `run` subcommand (lines 1388-1413)**:
```python
# Use shared functions:
add_dry_run_arg(run_parser)
add_resume_arg(run_parser)
add_max_workers_arg(run_parser)
add_timeout_arg(run_parser)
add_config_arg(run_parser)
add_skip_arg(run_parser, help_text="Comma-separated list of issue IDs to skip during execution (e.g., BUG-003,FEAT-004)")
```

**Update parsing in `_cmd_sprint_create` (lines 1460-1471)**:
```python
# Before:
skip_ids = {s.strip().upper() for s in args.skip.split(",")}

# After:
from little_loops.cli_args import parse_issue_ids
skip_ids = parse_issue_ids(args.skip) or set()
```

**Update parsing in `_cmd_sprint_run` (lines 1787-1793)**:
Same pattern - use `parse_issue_ids()`.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py scripts/tests/test_sprint_integration.py -v`
- [ ] Help output matches: `ll-sprint --help`, `ll-sprint run --help`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`

**Manual Verification**:
- [ ] Run `ll-sprint create --help` and verify all arguments
- [ ] Run `ll-sprint run --help` and verify all arguments
- [ ] Create a test sprint to verify it still works

---

### Phase 5: Create tests for cli_args module

#### Overview
Add comprehensive tests for the new cli_args module.

#### Changes Required

**File**: `scripts/tests/test_cli_args.py` (NEW)

```python
"""Tests for little_loops.cli_args module.

Tests cover:
- Argument addition functions
- parse_issue_ids() utility function
- Help text generation
"""
import argparse
from typing import Any

import pytest

from little_loops.cli_args import (
    add_common_auto_args,
    add_common_parallel_args,
    add_config_arg,
    add_dry_run_arg,
    add_max_issues_arg,
    add_max_workers_arg,
    add_only_arg,
    add_quiet_arg,
    add_resume_arg,
    add_skip_arg,
    add_timeout_arg,
    parse_issue_ids,
)


class TestParseIssueIds:
    """Tests for parse_issue_ids() function."""

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        result = parse_issue_ids(None)
        assert result is None

    def test_single_issue(self) -> None:
        """Single issue ID is uppercased."""
        result = parse_issue_ids("bug-001")
        assert result == {"BUG-001"}

    def test_multiple_issues(self) -> None:
        """Multiple comma-separated issues are uppercased and split."""
        result = parse_issue_ids("BUG-001,feat-002,ENH-003")
        assert result == {"BUG-001", "FEAT-002", "ENH-003"}

    def test_whitespace_handling(self) -> None:
        """Whitespace around IDs is stripped."""
        result = parse_issue_ids(" BUG-001 , feat-002 , ENH-003 ")
        assert result == {"BUG-001", "FEAT-002", "ENH-003"}

    def test_empty_string(self) -> None:
        """Empty string returns empty set."""
        result = parse_issue_ids("")
        assert result == set()


class TestAddDryRunArg:
    """Tests for add_dry_run_arg() function."""

    def test_adds_dry_run_flag(self) -> None:
        """Adds --dry-run and -n flags as store_true."""
        parser = argparse.ArgumentParser()
        add_dry_run_arg(parser)
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_short_flag(self) -> None:
        """Short -n flag works."""
        parser = argparse.ArgumentParser()
        add_dry_run_arg(parser)
        args = parser.parse_args(["-n"])
        assert args.dry_run is True

    def test_default_is_false(self) -> None:
        """Default value is False."""
        parser = argparse.ArgumentParser()
        add_dry_run_arg(parser)
        args = parser.parse_args([])
        assert args.dry_run is False


class TestAddResumeArg:
    """Tests for add_resume_arg() function."""

    def test_adds_resume_flag(self) -> None:
        """Adds --resume and -r flags as store_true."""
        parser = argparse.ArgumentParser()
        add_resume_arg(parser)
        args = parser.parse_args(["--resume"])
        assert args.resume is True

    def test_short_flag(self) -> None:
        """Short -r flag works."""
        parser = argparse.ArgumentParser()
        add_resume_arg(parser)
        args = parser.parse_args(["-r"])
        assert args.resume is True


class TestAddConfigArg:
    """Tests for add_config_arg() function."""

    def test_adds_config_path(self) -> None:
        """Adds --config argument that parses as Path."""
        from pathlib import Path

        parser = argparse.ArgumentParser()
        add_config_arg(parser)
        args = parser.parse_args(["--config", "/some/path"])
        assert args.config == Path("/some/path")

    def test_default_is_none(self) -> None:
        """Default value is None."""
        parser = argparse.ArgumentParser()
        add_config_arg(parser)
        args = parser.parse_args([])
        assert args.config is None


class TestAddMaxWorkersArg:
    """Tests for add_max_workers_arg() function."""

    def test_with_default(self) -> None:
        """Adds argument with specified default."""
        parser = argparse.ArgumentParser()
        add_max_workers_arg(parser, default=4)
        args = parser.parse_args([])
        assert args.max_workers == 4

    def test_without_default(self) -> None:
        """Adds argument with None default."""
        parser = argparse.ArgumentParser()
        add_max_workers_arg(parser)
        args = parser.parse_args([])
        assert args.max_workers is None

    def test_accepts_integer(self) -> None:
        """Accepts integer value."""
        parser = argparse.ArgumentParser()
        add_max_workers_arg(parser)
        args = parser.parse_args(["--max-workers", "8"])
        assert args.max_workers == 8

    def test_short_flag(self) -> None:
        """Short -w flag works."""
        parser = argparse.ArgumentParser()
        add_max_workers_arg(parser)
        args = parser.parse_args(["-w", "3"])
        assert args.max_workers == 3


class TestAddTimeoutArg:
    """Tests for add_timeout_arg() function."""

    def test_with_default(self) -> None:
        """Adds argument with specified default."""
        parser = argparse.ArgumentParser()
        add_timeout_arg(parser, default=3600)
        args = parser.parse_args([])
        assert args.timeout == 3600

    def test_without_default(self) -> None:
        """Adds argument with None default."""
        parser = argparse.ArgumentParser()
        add_timeout_arg(parser)
        args = parser.parse_args([])
        assert args.timeout is None

    def test_accepts_integer(self) -> None:
        """Accepts integer value."""
        parser = argparse.ArgumentParser()
        add_timeout_arg(parser)
        args = parser.parse_args(["--timeout", "1800"])
        assert args.timeout == 1800


class TestAddSkipArg:
    """Tests for add_skip_arg() function."""

    def test_default_help_text(self) -> None:
        """Uses default help text when not specified."""
        parser = argparse.ArgumentParser()
        add_skip_arg(parser)
        # Help text should contain expected content
        help_text = parser.format_help()
        assert "Comma-separated list of issue IDs to skip" in help_text

    def test_custom_help_text(self) -> None:
        """Uses custom help text when provided."""
        parser = argparse.ArgumentParser()
        add_skip_arg(parser, help_text="Custom help message")
        help_text = parser.format_help()
        assert "Custom help message" in help_text


class TestAddCommonAutoArgs:
    """Tests for add_common_auto_args() function."""

    def test_adds_all_expected_arguments(self) -> None:
        """Adds resume, dry-run, max-issues, only, skip, config."""
        parser = argparse.ArgumentParser()
        add_common_auto_args(parser)
        args = parser.parse_args([
            "--resume",
            "--dry-run",
            "--max-issues", "5",
            "--only", "BUG-001",
            "--skip", "BUG-002",
            "--config", "/path",
        ])
        assert args.resume is True
        assert args.dry_run is True
        assert args.max_issues == 5
        assert args.only == "BUG-001"
        assert args.skip == "BUG-002"
        assert args.config is not None


class TestAddCommonParallelArgs:
    """Tests for add_common_parallel_args() function."""

    def test_adds_all_expected_arguments(self) -> None:
        """Adds dry-run, resume, max-workers, timeout, quiet, only, skip, config."""
        parser = argparse.ArgumentParser()
        add_common_parallel_args(parser)
        args = parser.parse_args([
            "--dry-run",
            "--resume",
            "--max-workers", "3",
            "--timeout", "1800",
            "--quiet",
            "--only", "BUG-001",
            "--skip", "BUG-002",
            "--config", "/path",
        ])
        assert args.dry_run is True
        assert args.resume is True
        assert args.max_workers == 3
        assert args.timeout == 1800
        assert args.quiet is True
        assert args.only == "BUG-001"
        assert args.skip == "BUG-002"
        assert args.config is not None
```

#### Success Criteria

**Automated Verification**:
- [ ] All new tests pass: `python -m pytest scripts/tests/test_cli_args.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_cli_args.py`
- [ ] Type check passes: `python -m mypy scripts/tests/test_cli_args.py`

---

### Phase 6: Final verification and cleanup

#### Overview
Run full test suite and verify CLI tools work correctly.

#### Success Criteria

**Automated Verification**:
- [ ] All CLI tests pass: `python -m pytest scripts/tests/test_cli.py -v`
- [ ] All sprint tests pass: `python -m pytest scripts/tests/test_sprint.py scripts/tests/test_sprint_integration.py -v`
- [ ] New cli_args tests pass: `python -m pytest scripts/tests/test_cli_args.py -v`
- [ ] Full test suite passes: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Format passes: `ruff format scripts/`
- [ ] Type check passes: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] `ll-auto --help` shows correct arguments
- [ ] `ll-parallel --help` shows correct arguments
- [ ] `ll-sprint create --help` shows correct arguments
- [ ] `ll-sprint run --help` shows correct arguments
- [ ] Run `ll-auto --dry-run` in test project
- [ ] Run `ll-parallel --dry-run --cleanup` in test project

## Testing Strategy

### Unit Tests
- Test each argument addition function
- Test `parse_issue_ids()` edge cases (None, empty string, whitespace)
- Test default values for all arguments

### Integration Tests
- Verify existing CLI tests still pass
- Test help text output matches before/after
- Test argument parsing with various combinations

## References

- Original issue: `.issues/enhancements/P4-ENH-187-create-shared-cli-argument-module.md`
- CLI file: `scripts/little_loops/cli.py`
- Test file: `scripts/tests/test_cli.py`
- Related audit: `docs/CLI-TOOLS-AUDIT.md`
- Similar modules: `scripts/little_loops/logger.py`, `scripts/little_loops/subprocess_utils.py`
