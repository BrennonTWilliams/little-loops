"""ll-issues list: List active issues with optional type/priority/status filters."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize, print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_list(config: BRConfig, args: argparse.Namespace) -> int:
    """List issues with optional filters.

    Args:
        config: Project configuration
        args: Parsed arguments with optional .type, .priority, .status, .flat, and .json attributes

    Returns:
        Exit code (0 = success)
    """
    from little_loops.cli.issues.search import _load_issues_with_status

    status = getattr(args, "status", "active") or "active"
    include_active = status in ("active", "all")
    include_completed = status in ("completed", "all")
    include_deferred = status in ("deferred", "all")

    raw = _load_issues_with_status(config, include_active, include_completed, include_deferred)

    type_filter = getattr(args, "type", None)
    priority_filter = getattr(args, "priority", None)

    issues_with_status = [
        (issue, stat)
        for issue, stat in raw
        if (not type_filter or issue.issue_id.split("-", 1)[0] == type_filter)
        and (not priority_filter or issue.priority == priority_filter)
    ]

    limit = getattr(args, "limit", None)
    if limit is not None and limit < 1:
        import sys
        print(f"Error: --limit must be a positive integer, got {limit}", file=sys.stderr)
        return 1

    if limit is not None:
        issues_with_status = issues_with_status[:limit]

    if not issues_with_status:
        print("No issues found.")
        return 0

    if getattr(args, "json", False):
        print_json(
            [
                {
                    "id": issue.issue_id,
                    "priority": issue.priority,
                    "type": issue.issue_id.split("-", 1)[0],
                    "title": issue.title,
                    "path": str(issue.path),
                    "status": stat,
                }
                for issue, stat in issues_with_status
            ]
        )
        return 0

    if getattr(args, "flat", False):
        for issue, _stat in issues_with_status:
            print(f"{issue.path.name}  {issue.title}")
        return 0

    # Group by type prefix
    buckets: dict[str, list] = {"BUG": [], "FEAT": [], "ENH": []}
    for issue, stat in issues_with_status:
        prefix = issue.issue_id.split("-", 1)[0]
        if prefix in buckets:
            buckets[prefix].append((issue, stat))

    type_labels = {"BUG": "Bugs", "FEAT": "Features", "ENH": "Enhancements"}
    lines: list[str] = []
    for prefix, label in type_labels.items():
        group = buckets[prefix]
        if not group:
            continue
        header = colorize(f"{label} ({len(group)})", f"{TYPE_COLOR.get(prefix, '0')};1")
        lines.append(header)
        for issue, stat in group:
            issue_type = issue.issue_id.split("-", 1)[0]
            colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_type, "0"))
            colored_priority = colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))
            status_tag = f" [{stat}]" if stat != "active" else ""
            lines.append(f"  {colored_priority}  {colored_id}  {issue.title}{status_tag}")
        lines.append("")
    lines.append(f"Total: {len(issues_with_status)} issue(s) found")
    print("\n".join(lines))
    return 0
