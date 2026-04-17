"""ll-issues next-issue: Print the highest-confidence active issue."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_next_issue(config: BRConfig, args: argparse.Namespace) -> int:
    """Print the top-ranked active issue per ``config.issues.next_issue``.

    The default ``confidence_first`` strategy is byte-identical to the prior
    hardcoded sort: ``(-outcome_confidence, -confidence_score, priority_int)``.

    Args:
        config: Project configuration
        args: Parsed arguments with optional .json and .path flags

    Returns:
        Exit code (0 = found, 1 = no issues or invalid sort config)
    """
    from little_loops.cli.issues.search import build_sort_key
    from little_loops.cli.output import print_json
    from little_loops.cli_args import parse_issue_ids
    from little_loops.issue_parser import find_issues

    try:
        sort_key = build_sort_key(config.issues.next_issue)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    skip_ids = parse_issue_ids(getattr(args, "skip", None))
    issues = find_issues(config, skip_ids=skip_ids or None)
    if not issues:
        return 1

    issues.sort(key=sort_key)

    top = issues[0]

    if getattr(args, "json", False):
        print_json(
            {
                "id": top.issue_id,
                "path": str(top.path),
                "outcome_confidence": top.outcome_confidence,
                "confidence_score": top.confidence_score,
                "priority": top.priority,
            }
        )
        return 0

    if getattr(args, "path", False):
        print(str(top.path))
        return 0

    print(top.issue_id)
    return 0
