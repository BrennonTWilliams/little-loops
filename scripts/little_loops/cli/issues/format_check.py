"""ll-issues format-check: deterministic structural linter for issue formatting (ENH-2426)."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def add_format_check_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the format-check subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "format-check",
        help="Deterministic structural linter for issue formatting "
        "(missing/renamed/empty/boilerplate)",
    )
    p.set_defaults(command="format-check")
    p.add_argument("issue_id", help="Issue ID (e.g., 2426, ENH-2426, P3-ENH-2426)")
    p.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    add_config_arg(p)
    return p


def cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int:
    """Report structural format gaps (missing/renamed/empty/boilerplate) for an issue.

    Returns:
        0 when structurally compliant, 1 when gaps were found or the issue is not found.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.cli.output import print_json
    from little_loops.issue_parser import check_format_gaps
    from little_loops.issue_template import resolve_templates_dir

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    gaps = check_format_gaps(path, templates_dir=resolve_templates_dir(config))
    fmt = getattr(args, "format", "text") or "text"

    if fmt == "json":
        print_json(gaps.to_dict())
        return 1 if gaps.has_gaps else 0

    if not gaps.has_gaps:
        print(f"Formatted: {args.issue_id} is structurally compliant")
        return 0

    print(f"Needs formatting — structural gaps for {args.issue_id}:")
    for name in gaps.missing:
        print(f"  missing: {name}")
    for entry in gaps.renamed:
        print(f"  renamed: {entry}")
    for name in gaps.empty:
        print(f"  empty: {name}")
    for name in gaps.boilerplate:
        print(f"  boilerplate: {name}")
    return 1
