"""Shared CLI argument definitions for little-loops tools.

Provides reusable functions for adding common command-line arguments
to argparse parsers, ensuring consistency across ll-auto, ll-parallel,
and ll-sprint commands.
"""

from __future__ import annotations

import argparse
from pathlib import Path


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


def add_skip_analysis_arg(parser: argparse.ArgumentParser) -> None:
    """Add --skip-analysis argument to skip dependency discovery."""
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip dependency analysis (use when dependencies are known to be current)",
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


VALID_ISSUE_TYPES = {"BUG", "FEAT", "ENH"}


def add_type_arg(parser: argparse.ArgumentParser) -> None:
    """Add --type argument for filtering issues by type prefix."""
    parser.add_argument(
        "--type",
        type=str,
        default=None,
        help="Comma-separated issue types to process (e.g., BUG, FEAT, ENH)",
    )


def parse_issue_types(value: str | None) -> set[str] | None:
    """Parse comma-separated issue types into a validated set.

    Args:
        value: Comma-separated string like "BUG,ENH" or None

    Returns:
        Set of uppercase type prefixes, or None if value is None

    Raises:
        SystemExit: If invalid issue types are provided (via argparse error)

    Example:
        >>> parse_issue_types("bug,enh")
        {'BUG', 'ENH'}
        >>> parse_issue_types(None)
        None
    """
    if value is None:
        return None
    types = {t.strip().upper() for t in value.split(",")}
    invalid = types - VALID_ISSUE_TYPES
    if invalid:
        import sys

        print(
            f"error: invalid issue type(s): {', '.join(sorted(invalid))}. "
            f"Valid types: {', '.join(sorted(VALID_ISSUE_TYPES))}",
            file=sys.stderr,
        )
        sys.exit(2)
    return types


def add_common_auto_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to ll-auto command.

    Adds: --resume, --dry-run, --max-issues, --quiet, --only, --skip, --type, --config
    """
    add_resume_arg(parser)
    add_dry_run_arg(parser)
    add_max_issues_arg(parser)
    add_quiet_arg(parser)
    add_only_arg(parser)
    add_skip_arg(parser)
    add_type_arg(parser)
    add_config_arg(parser)


def add_common_parallel_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to parallel execution tools.

    Adds: --dry-run, --resume, --max-workers, --timeout, --quiet, --only, --skip, --type, --config
    """
    add_dry_run_arg(parser)
    add_resume_arg(parser)
    add_max_workers_arg(parser)
    add_timeout_arg(parser)
    add_quiet_arg(parser)
    add_only_arg(parser)
    add_skip_arg(parser)
    add_type_arg(parser)
    add_config_arg(parser)


__all__ = [
    "add_dry_run_arg",
    "add_resume_arg",
    "add_config_arg",
    "add_only_arg",
    "add_skip_arg",
    "add_type_arg",
    "add_max_workers_arg",
    "add_timeout_arg",
    "add_quiet_arg",
    "add_skip_analysis_arg",
    "add_max_issues_arg",
    "parse_issue_ids",
    "parse_issue_types",
    "VALID_ISSUE_TYPES",
    "add_common_auto_args",
    "add_common_parallel_args",
]
