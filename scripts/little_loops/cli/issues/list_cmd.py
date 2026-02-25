"""ll-issues list: List active issues with optional type/priority filters."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_list(config: BRConfig, args: argparse.Namespace) -> int:
    """List active issues with optional filters.

    Args:
        config: Project configuration
        args: Parsed arguments with optional .type and .priority attributes

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_parser import find_issues

    type_prefixes = {args.type} if args.type else None
    issues = find_issues(config, type_prefixes=type_prefixes)

    if args.priority:
        issues = [i for i in issues if i.priority == args.priority]

    if not issues:
        print("No active issues found.")
        return 0

    for issue in issues:
        print(f"{issue.path.name}  {issue.title}")
    return 0
