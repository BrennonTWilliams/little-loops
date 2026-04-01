"""Shared CLI argument definitions for little-loops tools.

Provides reusable functions for adding common command-line arguments
to argparse parsers, ensuring consistency across ll-auto, ll-parallel,
and ll-sprint commands.
"""

from __future__ import annotations

import argparse
import re
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
    """Add --config/-C argument to parser."""
    parser.add_argument(
        "--config",
        "-C",
        type=Path,
        default=None,
        help="Path to project root (default: current directory)",
    )


def add_only_arg(parser: argparse.ArgumentParser) -> None:
    """Add --only/-o argument for filtering specific issues."""
    parser.add_argument(
        "--only",
        "-o",
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
        "-s",
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


def add_idle_timeout_arg(parser: argparse.ArgumentParser) -> None:
    """Add --idle-timeout argument for idle process termination.

    Args:
        parser: The argument parser to add the argument to
    """
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=None,
        help="Kill worker if no output for N seconds (0 to disable, default: from config)",
    )


def add_handoff_threshold_arg(parser: argparse.ArgumentParser) -> None:
    """Add --handoff-threshold argument for per-run context handoff override.

    Args:
        parser: The argument parser to add the argument to
    """
    parser.add_argument(
        "--handoff-threshold",
        type=int,
        default=None,
        help="Override auto-handoff context threshold (1-100, default: from config)",
    )


def add_context_limit_arg(parser: argparse.ArgumentParser) -> None:
    """Add --context-limit argument for per-run context window size override.

    Args:
        parser: The argument parser to add the argument to
    """
    parser.add_argument(
        "--context-limit",
        type=int,
        default=None,
        help="Override context window token estimate (default: from config or 1000000 for Sonnet/Opus, 200000 for Haiku 4.5)",
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


def parse_issue_ids_ordered(value: str | None) -> list[str] | None:
    """Parse comma-separated issue IDs into an ordered list.

    Like parse_issue_ids but preserves input order, enabling callers to
    honor the sequence in which IDs were specified.

    Args:
        value: Comma-separated string like "BUG-001,FEAT-002" or None

    Returns:
        List of uppercase issue IDs in input order, or None if value is None

    Example:
        >>> parse_issue_ids_ordered("BUG-010,FEAT-005,ENH-020")
        ['BUG-010', 'FEAT-005', 'ENH-020']
        >>> parse_issue_ids_ordered(None)
        None
    """
    if value is None:
        return None
    return [i.strip().upper() for i in value.split(",")]


_NUMERIC_RE = re.compile(r"^\d+$")


def _id_matches(candidate: str, pattern: str) -> bool:
    """Return True if candidate matches pattern, supporting numeric-only patterns.

    Args:
        candidate: Full issue ID like 'ENH-732'
        pattern: Full ID like 'ENH-732' or numeric suffix like '732'

    Returns:
        True if candidate matches the pattern

    Example:
        >>> _id_matches("ENH-732", "732")
        True
        >>> _id_matches("ENH-732", "ENH-732")
        True
        >>> _id_matches("ENH-732", "BUG-732")
        False
    """
    if _NUMERIC_RE.match(pattern):
        return candidate.split("-")[-1] == pattern
    return candidate == pattern


VALID_ISSUE_TYPES = {"BUG", "FEAT", "ENH"}

VALID_PRIORITIES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3", "P4", "P5"})


def parse_priorities(value: str | None) -> set[str] | None:
    """Parse comma-separated priority levels into a validated set.

    Args:
        value: Comma-separated string like "P1,P2" or None

    Returns:
        Set of uppercase priority strings, or None if value is None

    Raises:
        SystemExit: If invalid priority levels are provided (exit code 2)

    Example:
        >>> parse_priorities("p1,P2")
        {'P1', 'P2'}
        >>> parse_priorities(None)
        None
    """
    if value is None:
        return None
    priorities = {p.strip().upper() for p in value.split(",")}
    invalid = priorities - VALID_PRIORITIES
    if invalid:
        import sys

        print(
            f"error: invalid priority level(s): {', '.join(sorted(invalid))}. "
            f"Valid priorities: {', '.join(sorted(VALID_PRIORITIES))}",
            file=sys.stderr,
        )
        sys.exit(2)
    return priorities


def add_priority_arg(parser: argparse.ArgumentParser) -> None:
    """Add --priority/-p argument for filtering issues by priority level."""
    parser.add_argument(
        "--priority",
        "-p",
        type=str,
        default=None,
        help="Comma-separated priority levels to process (e.g., P0, P1,P2)",
    )


def add_type_arg(parser: argparse.ArgumentParser) -> None:
    """Add --type/-T argument for filtering issues by type prefix."""
    parser.add_argument(
        "--type",
        "-T",
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

    Adds: --resume, --dry-run, --max-issues, --quiet, --only, --skip, --type, --priority,
          --config, --idle-timeout, --handoff-threshold, --context-limit
    """
    add_resume_arg(parser)
    add_dry_run_arg(parser)
    add_max_issues_arg(parser)
    add_quiet_arg(parser)
    add_only_arg(parser)
    add_skip_arg(parser)
    add_type_arg(parser)
    add_priority_arg(parser)
    add_config_arg(parser)
    add_idle_timeout_arg(parser)
    add_handoff_threshold_arg(parser)
    add_context_limit_arg(parser)


def add_common_parallel_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to parallel execution tools.

    Adds: --dry-run, --resume, --max-workers, --timeout, --idle-timeout, --quiet, --only, --skip, --type, --config,
          --context-limit
    """
    add_dry_run_arg(parser)
    add_resume_arg(parser)
    add_max_workers_arg(parser)
    add_timeout_arg(parser)
    add_idle_timeout_arg(parser)
    add_quiet_arg(parser)
    add_only_arg(parser)
    add_skip_arg(parser)
    add_type_arg(parser)
    add_config_arg(parser)
    add_context_limit_arg(parser)


__all__ = [
    "add_dry_run_arg",
    "add_resume_arg",
    "add_config_arg",
    "add_only_arg",
    "add_skip_arg",
    "add_type_arg",
    "add_priority_arg",
    "add_max_workers_arg",
    "add_timeout_arg",
    "add_idle_timeout_arg",
    "add_handoff_threshold_arg",
    "add_context_limit_arg",
    "add_quiet_arg",
    "add_skip_analysis_arg",
    "add_max_issues_arg",
    "parse_issue_ids",
    "parse_issue_types",
    "parse_priorities",
    "VALID_ISSUE_TYPES",
    "VALID_PRIORITIES",
    "add_common_auto_args",
    "add_common_parallel_args",
]
