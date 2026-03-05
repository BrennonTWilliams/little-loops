"""ll-issues list: List active issues with optional type/priority filters."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_list(config: BRConfig, args: argparse.Namespace) -> int:
    """List active issues with optional filters.

    Args:
        config: Project configuration
        args: Parsed arguments with optional .type, .priority, and .flat attributes

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_parser import find_issues

    type_prefixes = {args.type} if getattr(args, "type", None) else None
    issues = find_issues(config, type_prefixes=type_prefixes)

    if getattr(args, "priority", None):
        issues = [i for i in issues if i.priority == args.priority]

    if not issues:
        print("No active issues found.")
        return 0

    if getattr(args, "flat", False):
        for issue in issues:
            print(f"{issue.path.name}  {issue.title}")
        return 0

    # Group by type prefix
    buckets: dict[str, list] = {"BUG": [], "FEAT": [], "ENH": []}
    for issue in issues:
        prefix = issue.issue_id.split("-", 1)[0]
        if prefix in buckets:
            buckets[prefix].append(issue)

    type_labels = {"BUG": "Bugs", "FEAT": "Features", "ENH": "Enhancements"}
    lines: list[str] = []
    for prefix, label in type_labels.items():
        group = buckets[prefix]
        header = colorize(f"{label} ({len(group)})", f"{TYPE_COLOR.get(prefix, '0')};1")
        lines.append(header)
        for issue in group:
            issue_type = issue.issue_id.split("-", 1)[0]
            colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_type, "0"))
            colored_priority = colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))
            lines.append(f"  {colored_priority}  {colored_id}  {issue.title}")
        lines.append("")
    lines.append(f"Total: {len(issues)} active issues")
    print("\n".join(lines))
    return 0
