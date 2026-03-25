"""ll-issues next-issues: Print all active issues in ranked order."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_next_issues(config: BRConfig, args: argparse.Namespace) -> int:
    """Print all active issues sorted by outcome confidence and readiness.

    Sort key: (-(outcome_confidence or -1), -(confidence_score or -1), priority_int)

    Args:
        config: Project configuration
        args: Parsed arguments with optional .json, .path flags and .count

    Returns:
        Exit code (0 = at least one found, 1 = no issues)
    """
    from little_loops.cli.output import print_json
    from little_loops.issue_parser import find_issues

    issues = find_issues(config)
    if not issues:
        return 1

    issues.sort(
        key=lambda i: (
            -(i.outcome_confidence if i.outcome_confidence is not None else -1),
            -(i.confidence_score if i.confidence_score is not None else -1),
            i.priority_int,
        )
    )

    count = getattr(args, "count", None)
    ranked = issues[:count] if count else issues

    if getattr(args, "json", False):
        print_json(
            [
                {
                    "id": i.issue_id,
                    "path": str(i.path),
                    "outcome_confidence": i.outcome_confidence,
                    "confidence_score": i.confidence_score,
                    "priority": i.priority,
                }
                for i in ranked
            ]
        )
        return 0

    if getattr(args, "path", False):
        for i in ranked:
            print(str(i.path))
        return 0

    for i in ranked:
        print(i.issue_id)
    return 0
