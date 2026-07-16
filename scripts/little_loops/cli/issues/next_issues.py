"""ll-issues next-issues: Print all active issues in ranked order."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_next_issues(config: BRConfig, args: argparse.Namespace) -> int:
    """Print all active issues ranked per ``config.issues.next_issue``.

    The default ``confidence_first`` strategy is byte-identical to the prior
    hardcoded sort: ``(-outcome_confidence, -confidence_score, priority_int)``.

    Args:
        config: Project configuration
        args: Parsed arguments with optional .json, .path, .count, and
            .include_blocked flags.

    Returns:
        Exit code (0 = at least one found, 1 = no issues, all-blocked, or
        invalid sort config)
    """
    from little_loops.cli.issues.search import build_sort_key
    from little_loops.cli.output import print_json
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.issue_parser import find_issues

    try:
        sort_key = build_sort_key(config.issues.next_issue)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    include_blocked = bool(getattr(args, "include_blocked", False))

    if include_blocked:
        # EPICs are umbrella containers meant to be decomposed via scope
        # resolution, never ranked as implementable leaves (BUG-2638).
        all_issues = [i for i in find_issues(config) if not i.issue_id.startswith("EPIC-")]
        if not all_issues:
            return 1

        graph = DependencyGraph.from_issues(find_issues(config))
        blocked_by_map: dict[str, list[str]] = {
            issue_id: sorted(graph.blocked_by.get(issue_id, set()))
            for issue_id in (i.issue_id for i in all_issues)
        }
        # Soft `depends_on` prerequisites still open per issue. Hard `blocked`
        # stays edge-only; this surfaces ordering deferrals that would otherwise
        # report as ready in --include-blocked (ENH-2635).
        pending_prereq_map: dict[str, list[str]] = {
            issue_id: sorted(graph.get_pending_prerequisites(issue_id))
            for issue_id in (i.issue_id for i in all_issues)
        }

        all_issues.sort(key=sort_key)
        count = getattr(args, "count", None)
        ranked = all_issues[:count] if count else all_issues
    else:
        issues = [
            i for i in find_issues(config, skip_blocked=True) if not i.issue_id.startswith("EPIC-")
        ]
        if not issues:
            all_active = [i for i in find_issues(config) if not i.issue_id.startswith("EPIC-")]
            if all_active:
                print(
                    f"Error: No ready issues ({len(all_active)} blocked, 0 ready)",
                    file=sys.stderr,
                )
            return 1

        issues.sort(key=sort_key)
        count = getattr(args, "count", None)
        ranked = issues[:count] if count else issues
        blocked_by_map = {}
        pending_prereq_map = {}

    if getattr(args, "json", False):
        rows: list[dict[str, object]] = []
        for i in ranked:
            row: dict[str, object] = {
                "id": i.issue_id,
                "path": str(i.path),
                "outcome_confidence": i.outcome_confidence,
                "confidence_score": i.confidence_score,
                "priority": i.priority,
            }
            if include_blocked:
                row["blocked"] = bool(blocked_by_map.get(i.issue_id))
                row["blocked_by"] = blocked_by_map.get(i.issue_id, [])
                row["pending_prerequisites"] = pending_prereq_map.get(i.issue_id, [])
            rows.append(row)
        print_json(rows)
        return 0

    if getattr(args, "path", False):
        for i in ranked:
            print(str(i.path))
        return 0

    for i in ranked:
        print(i.issue_id)
    return 0
