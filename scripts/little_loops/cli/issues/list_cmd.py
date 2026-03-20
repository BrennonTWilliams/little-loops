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
    from datetime import date

    from little_loops.cli.issues.search import (
        _load_issues_with_status,
        _parse_discovered_date,
        _sort_issues,
    )

    status = getattr(args, "status", "active") or "active"
    include_active = status in ("active", "all")
    include_completed = status in ("completed", "all")
    include_deferred = status in ("deferred", "all")

    raw = _load_issues_with_status(config, include_active, include_completed, include_deferred)

    from little_loops.cli_args import parse_priorities

    type_filter = getattr(args, "type", None)
    priority_filter: set[str] | None = parse_priorities(getattr(args, "priority", None))

    filtered = [
        (issue, stat)
        for issue, stat in raw
        if (not type_filter or issue.issue_id.split("-", 1)[0] == type_filter)
        and (not priority_filter or issue.priority in priority_filter)
    ]

    # Sort
    sort_field = getattr(args, "sort", "priority") or "priority"
    need_content = sort_field in {"created", "completed"}
    enriched: list[tuple] = []
    for issue, stat in filtered:
        disc_date: date | None = None
        comp_date: date | None = None
        if need_content:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                content = ""
            if sort_field == "created":
                disc_date = _parse_discovered_date(content)
            elif sort_field == "completed":
                from little_loops.issue_history.parsing import _parse_completion_date

                comp_date = _parse_completion_date(content, issue.path)
        enriched.append((issue, stat, disc_date, comp_date))

    if getattr(args, "desc", False):
        descending = True
    elif getattr(args, "asc", False):
        descending = False
    else:
        descending = sort_field in {"created", "completed"}

    enriched = _sort_issues(enriched, sort_field, descending)

    limit = getattr(args, "limit", None)
    if limit is not None and limit < 1:
        import sys

        print(f"Error: --limit must be a positive integer, got {limit}", file=sys.stderr)
        return 1

    if limit is not None:
        enriched = enriched[:limit]

    issues_with_status = [(item[0], item[1]) for item in enriched]

    if not issues_with_status:
        print("No active issues")
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
                    "discovered_date": str(disc_date) if disc_date else None,
                }
                for issue, stat, disc_date, _comp_date in enriched
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
        header = colorize(f"{label} ({len(group)})", f"{TYPE_COLOR.get(prefix, '0')};1")
        lines.append(header)
        for issue, stat in group:
            issue_type = issue.issue_id.split("-", 1)[0]
            colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_type, "0"))
            colored_priority = colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))
            status_tag = f" [{stat}]" if stat != "active" else ""
            lines.append(f"  {colored_priority}  {colored_id}  {issue.title}{status_tag}")
        lines.append("")
    lines.append(f"Total: {len(issues_with_status)} active issues")
    print("\n".join(lines))
    return 0
