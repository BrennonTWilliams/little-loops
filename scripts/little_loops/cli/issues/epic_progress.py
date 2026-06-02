"""ll-issues epic-progress: EPIC child-issue progress aggregation and display."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig

_ALL_STATUSES: set[str] = {"open", "in_progress", "blocked", "done", "cancelled", "deferred"}

_STATUS_ORDER = ["in_progress", "blocked", "open", "done", "cancelled", "deferred"]


def add_epic_progress_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the epic-progress subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "epic-progress",
        aliases=["ep"],
        help="Show aggregate progress for an EPIC (done/total, blocked, oldest open)",
    )
    p.set_defaults(command="epic-progress")
    p.add_argument("epic_id", help="EPIC ID (e.g., EPIC-1773)")
    p.add_argument(
        "--format",
        "-f",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    add_config_arg(p)
    return p


def cmd_epic_progress(config: BRConfig, args: argparse.Namespace) -> int:
    """Display progress aggregates for a single EPIC.

    Returns:
        0 on success, 1 on error (EPIC not found or bad ID).
    """
    from little_loops.cli.output import TYPE_COLOR, colorize, print_json, sparkline
    from little_loops.issue_parser import find_issues
    from little_loops.issue_progress import compute_epic_progress

    epic_id = args.epic_id.strip().upper()
    if not epic_id.startswith("EPIC-"):
        print(f"Error: expected an EPIC ID (e.g., EPIC-1773), got {args.epic_id!r}")
        return 1

    all_issues = find_issues(config, status_filter=_ALL_STATUSES)
    prog = compute_epic_progress(epic_id, all_issues)

    if prog is None:
        print(f"Error: EPIC {epic_id!r} not found")
        return 1

    fmt = getattr(args, "format", "text") or "text"

    if fmt == "json":
        print_json(prog.to_dict())
        return 0

    total = len(prog.children)
    if total == 0:
        print(f"{epic_id}: {prog.epic_title}")
        print("  (no children)")
        return 0

    done_count = prog.by_status.get("done", 0) + prog.by_status.get("cancelled", 0)
    blocked_count = prog.by_status.get("blocked", 0)
    pct = round(prog.percent_done)

    if fmt == "markdown":
        lines = [
            f"## {epic_id}: {prog.epic_title}",
            f"- **Progress**: {done_count}/{total} done ({pct}%)",
        ]
        status_parts = [
            f"{prog.by_status[s]} {s}" for s in _STATUS_ORDER if prog.by_status.get(s, 0) > 0
        ]
        lines.append("- **Status**: " + "  •  ".join(status_parts))
        if prog.oldest_open is not None:
            age_str = (
                f" ({prog.oldest_open_age_days} days)"
                if prog.oldest_open_age_days is not None
                else ""
            )
            lines.append(f"- **Oldest open**: {prog.oldest_open.issue_id}{age_str}")
        if blocked_count > 0:
            for bc in (c for c in prog.children if c.status == "blocked"):
                by_str = ", ".join(bc.blocked_by) if bc.blocked_by else "(unknown)"
                lines.append(f"- **Blocked**: {bc.issue_id} → blocked_by {by_str}")
        print("\n".join(lines))
        return 0

    # text format
    epic_color = TYPE_COLOR.get("EPIC", "35")
    print(colorize(f"{epic_id}: {prog.epic_title}", f"{epic_color};1"))

    bar = colorize(sparkline(done_count, total, width=16), "32")
    print(f"  Progress:     {bar}  {done_count}/{total} done ({pct}%)")

    status_parts = [
        f"{prog.by_status[s]} {s}" for s in _STATUS_ORDER if prog.by_status.get(s, 0) > 0
    ]
    print(f"  Status:       {'  •  '.join(status_parts)}")

    if prog.oldest_open is not None:
        age_str = (
            f" ({prog.oldest_open_age_days} days)" if prog.oldest_open_age_days is not None else ""
        )
        issue_type = prog.oldest_open.issue_id.split("-", 1)[0]
        colored_id = colorize(prog.oldest_open.issue_id, TYPE_COLOR.get(issue_type, "0"))
        print(f"  Oldest open:  {colored_id}{age_str}")

    if blocked_count > 0:
        for bc in (c for c in prog.children if c.status == "blocked"):
            by_str = ", ".join(bc.blocked_by) if bc.blocked_by else "(unknown)"
            print(f"  Blocked:      {bc.issue_id} → blocked_by {by_str}")

    return 0
