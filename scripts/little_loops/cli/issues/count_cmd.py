"""ll-issues count: Count active issues with optional type/priority filters."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from little_loops.cli.output import print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_count(config: BRConfig, args: argparse.Namespace) -> int:
    """Print active issue counts.

    Args:
        config: Project configuration
        args: Parsed arguments with optional .type, .priority, and .json attributes

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_parser import find_issues

    type_prefixes = {args.type} if getattr(args, "type", None) else None
    issues = find_issues(config, type_prefixes=type_prefixes)

    if getattr(args, "priority", None):
        issues = [i for i in issues if i.priority == args.priority]

    if getattr(args, "json", False):
        by_type: dict[str, int] = {"BUG": 0, "FEAT": 0, "ENH": 0}
        by_priority: dict[str, int] = {
            "P0": 0, "P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0,
        }
        for issue in issues:
            prefix = issue.issue_id.split("-", 1)[0]
            if prefix in by_type:
                by_type[prefix] += 1
            if issue.priority in by_priority:
                by_priority[issue.priority] += 1

        print_json({"total": len(issues), "by_type": by_type, "by_priority": by_priority})
        return 0

    print(len(issues))
    return 0
