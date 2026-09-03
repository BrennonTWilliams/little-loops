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
from little_loops.text_utils import build_ref_index

if TYPE_CHECKING:
    from pathlib import Path

    from little_loops.config import BRConfig
    from little_loops.issues.research_triage import AxisCoverage


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

    index = build_ref_index(
        config.project_root, untracked_by_design=config.issues.untracked_by_design
    )
    coverages = triage_research_axes(path, config.project_root, index=index)

    _record_research_triage(config, args.issue_id, path, coverages)

    if getattr(args, "json", False):
        print_json({c.axis: c.to_dict() for c in coverages})
        return 0

    for coverage in coverages:
        state = "covered" if coverage.covered else "unmet"
        suffix = f" — {coverage.evidence}" if coverage.evidence else ""
        print(f"{coverage.axis:15s} {state}{suffix}")
    return 0


def _record_research_triage(
    config: BRConfig,
    issue_id: str,
    issue_path: Path,
    coverages: tuple[AxisCoverage, ...],
) -> None:
    """Best-effort telemetry write of this invocation's per-axis verdict (ENH-2990).

    Runs on both the ``--json`` and text output paths. Gated explicitly on
    ``config.analytics_capture.cli_commands`` rather than relying on
    ``cli_event_context``'s own gate — that gate only applies when a caller
    passes ``config``, and no ``ll-*`` entry point does, making it dead code
    today (ENH-2932 regression, out of scope here). ``write_research_triage``
    is itself fail-soft (never raises), so this never alters
    :func:`cmd_research_triage`'s exit-0 contract.
    """
    import os

    from little_loops.config.features import feature_enabled_for
    from little_loops.issues.research_triage import issue_refined_at
    from little_loops.session_store import resolve_history_db, write_research_triage

    gate_open = feature_enabled_for(
        {"cli_commands": config.analytics_capture.cli_commands}, "cli_commands", "ll-issues"
    )
    if not gate_open:
        return

    refined_at = None
    try:
        content = issue_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        content = None
    if content is not None:
        refined = issue_refined_at(content)
        refined_at = refined.isoformat() if refined is not None else None

    write_research_triage(
        resolve_history_db(),
        issue_id=issue_id,
        refined_at=refined_at,
        session_id=os.environ.get("CLAUDE_SESSION_ID"),
        axes=[(c.axis, c.covered, c.reason, c.evidence) for c in coverages],
    )
