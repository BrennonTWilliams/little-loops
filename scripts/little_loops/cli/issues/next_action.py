"""ll-issues next-action: Print the next refinement action needed across all active issues."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_next_action(config: BRConfig, args: argparse.Namespace) -> int:
    """Print the next refinement action needed across all active issues.

    Output: NEEDS_FORMAT|NEEDS_VERIFY|NEEDS_SCORE|NEEDS_REFINE <id>  (exit 1)
            ALL_DONE                                                   (exit 0)

    Args:
        config: Project configuration
        args: Parsed arguments with optional .refine_cap, .ready_threshold, .outcome_threshold

    Returns:
        Exit code (1 = work remains, 0 = all done)
    """
    from little_loops.issue_parser import find_issues, is_formatted

    issues = find_issues(config)
    issues.sort(key=lambda i: (i.priority_int, -int(i.issue_id.split("-")[1])))

    refine_cap: int = getattr(args, "refine_cap", 5)
    ready_threshold: int = getattr(args, "ready_threshold", 85)
    outcome_threshold: int = getattr(args, "outcome_threshold", 70)

    for issue in issues:
        if not is_formatted(issue.path):
            print(f"NEEDS_FORMAT {issue.issue_id}")
            return 1
        if "/ll:verify-issues" not in issue.session_commands:
            print(f"NEEDS_VERIFY {issue.issue_id}")
            return 1
        cs = issue.confidence_score
        oc = issue.outcome_confidence
        if cs is None or oc is None:
            print(f"NEEDS_SCORE {issue.issue_id}")
            return 1
        if issue.session_command_counts.get("/ll:refine-issue", 0) < refine_cap:
            if cs < ready_threshold or oc < outcome_threshold:
                print(f"NEEDS_REFINE {issue.issue_id}")
                return 1

    print("ALL_DONE")
    return 0
