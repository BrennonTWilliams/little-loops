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
        args: Parsed arguments with optional .json, .path, and .include_blocked flags

    Returns:
        Exit code (0 = found, 1 = no issues, all-blocked, or invalid sort config)
    """
    from little_loops.cli.issues.search import build_sort_key
    from little_loops.cli.output import print_json
    from little_loops.cli_args import parse_issue_ids
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.issue_parser import find_issues

    try:
        sort_key = build_sort_key(config.issues.next_issue)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    include_blocked = bool(getattr(args, "include_blocked", False))

    skip_ids = parse_issue_ids(getattr(args, "skip", None))

    if include_blocked:
        # Compute the full ranked set without filtering, then evaluate
        # each candidate's blocked status against the dep graph.
        # EPICs are umbrella containers meant to be decomposed via scope
        # resolution, never ranked as implementable leaves (BUG-2638).
        ranked = [
            i
            for i in find_issues(config, skip_ids=skip_ids or None)
            if not i.issue_id.startswith("EPIC-")
        ]
        if not ranked:
            return 1

        # Build the dep graph from every active issue so blocking edges outside
        # the requested slice are still correctly recognized.
        all_known_ids: set[str] | None = None
        try:
            from little_loops.dependency_mapper import gather_all_issue_ids

            issues_dir = config.project_root / config.issues.base_dir
            all_known_ids = gather_all_issue_ids(issues_dir, config=config)
        except Exception:
            pass
        graph = DependencyGraph.from_issues(find_issues(config), all_known_ids=all_known_ids)
        blocked_by_map: dict[str, list[str]] = {
            issue_id: sorted(graph.blocked_by.get(issue_id, set()))
            for issue_id in (i.issue_id for i in ranked)
        }

        ranked.sort(key=sort_key)
        top = ranked[0]
        top_blocked = bool(blocked_by_map.get(top.issue_id))
        top_blocked_by = blocked_by_map.get(top.issue_id, [])
        # Soft `depends_on` prerequisites still open for the post-sort pick.
        # Hard `blocked` stays edge-only; this surfaces ordering deferrals that
        # would otherwise report as ready in --include-blocked (ENH-2635).
        top_pending_prereqs = sorted(graph.get_pending_prerequisites(top.issue_id))
    else:
        issues = [
            i
            for i in find_issues(config, skip_ids=skip_ids or None, skip_blocked=True)
            if not i.issue_id.startswith("EPIC-")
        ]
        if not issues:
            # Distinguish "all active issues blocked" from "no active issues at
            # all" by counting the unfiltered active set; if non-empty, all of
            # them must currently be blocked.
            all_active = [
                i
                for i in find_issues(config, skip_ids=skip_ids or None)
                if not i.issue_id.startswith("EPIC-")
            ]
            if all_active:
                print(
                    f"Error: No ready issues ({len(all_active)} blocked, 0 ready)",
                    file=sys.stderr,
                )
            return 1

        issues.sort(key=sort_key)
        top = issues[0]
        top_blocked = False
        top_blocked_by = []
        top_pending_prereqs = []

    if getattr(args, "json", False):
        row: dict[str, object] = {
            "id": top.issue_id,
            "path": str(top.path),
            "outcome_confidence": top.outcome_confidence,
            "confidence_score": top.confidence_score,
            "priority": top.priority,
        }
        if include_blocked:
            row["blocked"] = top_blocked
            row["blocked_by"] = top_blocked_by
            row["pending_prerequisites"] = top_pending_prereqs
        print_json(row)
        return 0

    if getattr(args, "path", False):
        print(str(top.path))
        return 0

    print(top.issue_id)
    return 0
