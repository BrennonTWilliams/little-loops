"""ll-issues format-check: deterministic structural linter for issue formatting (ENH-2426)."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import FormatGaps


def add_format_check_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the format-check subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "format-check",
        help="Deterministic structural linter for issue formatting "
        "(missing/renamed/empty/boilerplate/malformed_id/prose_dep_drift/stale_prose_dep)",
    )
    p.set_defaults(command="format-check")
    p.add_argument(
        "issue_id",
        nargs="?",
        default=None,
        help="Issue ID (e.g., 2426, ENH-2426, P3-ENH-2426); omit when using --all",
    )
    p.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Sweep every active issue (bugs/features/enhancements/epics) instead of one",
    )
    p.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    add_config_arg(p)
    return p


def _print_gaps(gaps: FormatGaps) -> None:
    for name in gaps.missing:
        print(f"  missing: {name}")
    for entry in gaps.renamed:
        print(f"  renamed: {entry}")
    for name in gaps.empty:
        print(f"  empty: {name}")
    for name in gaps.boilerplate:
        print(f"  boilerplate: {name}")
    for entry in gaps.malformed_id:
        print(f"  malformed_id: {entry}")
    for entry in gaps.prose_dep_drift:
        print(f"  prose_dep_drift: {entry}")
    for entry in gaps.stale_prose_dep:
        print(f"  stale_prose_dep: {entry}")


def cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int:
    """Report structural format gaps for one issue, or sweep all active issues.

    Gap classes: missing/renamed/empty/boilerplate/malformed_id/
    prose_dep_drift/stale_prose_dep.

    Returns:
        0 when structurally compliant (all issues, in --all mode), 1 when gaps
        were found (any issue, in --all mode) or the issue is not found.
    """
    from little_loops.cli.output import print_json
    from little_loops.issue_parser import check_format_gaps, find_issues
    from little_loops.issue_progress import _ALL_STATUSES
    from little_loops.issue_template import resolve_templates_dir

    issue_id: str | None = getattr(args, "issue_id", None)
    check_all: bool = getattr(args, "all", False)
    fmt = getattr(args, "format", "text") or "text"

    if not issue_id and not check_all:
        print("Error: provide an issue ID or --all", file=sys.stderr)
        return 1

    all_issues = find_issues(config, status_filter=set(_ALL_STATUSES))
    issue_statuses = {info.issue_id: info.status for info in all_issues}
    templates_dir = resolve_templates_dir(config)

    if check_all:
        # Sweep only active issues (default status_filter excludes
        # done/cancelled/deferred) — a closed issue's stale prose is no
        # longer worth gating on. `issue_statuses` above still covers every
        # issue so drift/stale classification against *targets* is accurate.
        active_issues = find_issues(config)
        results: dict[str, FormatGaps] = {}
        for info in sorted(active_issues, key=lambda i: i.issue_id):
            try:
                gaps = check_format_gaps(
                    info.path,
                    templates_dir=templates_dir,
                    issue_statuses=issue_statuses,
                )
            except OSError as exc:
                print(f"Warning: skipping {info.path}: {exc}", file=sys.stderr)
                continue
            if gaps.has_gaps:
                results[info.issue_id] = gaps

        if fmt == "json":
            print_json({issue_id: gaps.to_dict() for issue_id, gaps in results.items()})
            return 1 if results else 0

        if not results:
            print(f"Formatted: all {len(active_issues)} issue(s) are structurally compliant")
            return 0

        print(
            f"Needs formatting — structural gaps in {len(results)}/{len(active_issues)} issue(s):"
        )
        for gapped_id, gaps in results.items():
            print(f"{gapped_id}:")
            _print_gaps(gaps)
        return 1

    from little_loops.cli.issues.show import _resolve_issue_id

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        print(f"Error: Issue '{issue_id}' not found.", file=sys.stderr)
        return 1

    gaps = check_format_gaps(
        path,
        templates_dir=templates_dir,
        issue_statuses=issue_statuses,
    )

    if fmt == "json":
        print_json(gaps.to_dict())
        return 1 if gaps.has_gaps else 0

    if not gaps.has_gaps:
        print(f"Formatted: {issue_id} is structurally compliant")
        return 0

    print(f"Needs formatting — structural gaps for {issue_id}:")
    _print_gaps(gaps)
    return 1
