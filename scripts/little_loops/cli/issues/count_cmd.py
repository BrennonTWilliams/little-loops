"""ll-issues count: Count issues with optional type/priority/status filters."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from little_loops.cli.output import print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_count(config: BRConfig, args: argparse.Namespace) -> int:
    """Print issue counts with optional status, type, and priority filters.

    Args:
        config: Project configuration
        args: Parsed arguments with optional .type, .priority, .status, and .json attributes

    Returns:
        Exit code (0 = success)
    """
    from little_loops.cli.issues.search import _load_issues_with_status

    status = getattr(args, "status", "active") or "active"
    include_active = status in ("active", "all")
    include_completed = status in ("completed", "all")
    include_deferred = status in ("deferred", "all")

    raw = _load_issues_with_status(config, include_active, include_completed, include_deferred)
    issues = [issue for issue, _stat in raw]

    from little_loops.cli_args import parse_priorities

    if getattr(args, "type", None):
        issues = [i for i in issues if i.issue_id.split("-", 1)[0] == args.type]

    priority_filter = parse_priorities(getattr(args, "priority", None))
    if priority_filter is not None:
        issues = [i for i in issues if i.priority in priority_filter]

    if getattr(args, "json", False):
        by_type: dict[str, int] = {"BUG": 0, "FEAT": 0, "ENH": 0}
        by_priority: dict[str, int] = {
            "P0": 0,
            "P1": 0,
            "P2": 0,
            "P3": 0,
            "P4": 0,
            "P5": 0,
        }
        for issue in issues:
            prefix = issue.issue_id.split("-", 1)[0]
            if prefix in by_type:
                by_type[prefix] += 1
            if issue.priority in by_priority:
                by_priority[issue.priority] += 1

        print_json(
            {"total": len(issues), "status": status, "by_type": by_type, "by_priority": by_priority}
        )
        return 0

    print(len(issues))
    return 0
