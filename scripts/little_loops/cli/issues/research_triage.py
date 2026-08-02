"""ll-issues research-triage: which research axes an issue already covers (ENH-2971).

``commands/refine-issue.md`` is markdown; its only route to Python is ``Bash``,
and its ``allowed-tools`` permits ``Bash(ll-issues:*)``. Without this entry
point :func:`~little_loops.issues.research_triage.triage_research_axes` is
unreachable from Step 3 and the change ships inert.

Follows ``set_flags.py``'s own-parser-plus-``--json`` shape rather than
``check_decidable.py``'s exit-code-only shape: Step 3 branches on the emitted
axis map, not on the exit code.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from little_loops.issues.research_triage import triage_research_axes

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def add_research_triage_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the research-triage subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "research-triage",
        help="Report which of refine-issue's three research axes the issue already covers",
    )
    p.set_defaults(command="research-triage")
    p.add_argument("issue_id", help="Issue ID to triage (e.g. ENH-2971)")
    p.add_argument(
        "--json",
        "-j",
        action="store_true",
        help='Emit {"locator": {...}, "analyzer": {...}, "pattern_finder": {...}}',
    )
    add_config_arg(p)
    return p


def cmd_research_triage(config: BRConfig, args: argparse.Namespace) -> int:
    """Print the per-axis coverage map for one issue.

    Exit 0 whenever the issue is readable, **including when every axis is
    unmet**: a nonzero exit there would be indistinguishable from a missing
    issue and would push refine-issue's Step 3 into an error branch on the
    common case. Only an unresolvable issue ID exits 1.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.cli.output import print_json

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    coverages = triage_research_axes(path, config.project_root)

    if getattr(args, "json", False):
        print_json({c.axis: c.to_dict() for c in coverages})
        return 0

    for coverage in coverages:
        state = "covered" if coverage.covered else "unmet"
        suffix = f" — {coverage.evidence}" if coverage.evidence else ""
        print(f"{coverage.axis:15s} {state}{suffix}")
    return 0
