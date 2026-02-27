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
        lines.append(f"{label} ({len(group)})")
        for issue in group:
            lines.append(f"  {issue.priority}  {issue.issue_id}  {issue.title}")
        lines.append("")
    lines.append(f"Total: {len(issues)} active issues")
    print("\n".join(lines))
    return 0
