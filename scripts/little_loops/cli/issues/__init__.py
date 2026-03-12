"""ll-issues: Issue management CLI with sub-commands."""

from __future__ import annotations

import argparse
from pathlib import Path


def main_issues() -> int:
    """Entry point for ll-issues command.

    Dispatches to sub-commands for issue management and visualization.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    from little_loops.cli.issues.count_cmd import cmd_count
    from little_loops.cli.issues.impact_effort import cmd_impact_effort
    from little_loops.cli.issues.list_cmd import cmd_list
    from little_loops.cli.issues.next_id import cmd_next_id
    from little_loops.cli.issues.refine_status import cmd_refine_status
    from little_loops.cli.issues.sequence import cmd_sequence
    from little_loops.cli.issues.show import cmd_show
    from little_loops.cli_args import add_config_arg
    from little_loops.config import BRConfig

    parser = argparse.ArgumentParser(
        prog="ll-issues",
        description="Issue management and visualization utilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Sub-commands:
  next-id        Print next globally unique issue number
  list           List active issues with optional filters
  count          Count active issues (total or filtered)
  show           Show summary card for a single issue
  sequence       Suggest dependency-ordered implementation sequence
  impact-effort  Display impact vs effort matrix for active issues
  refine-status  Show refinement depth table sorted by commands touched

Examples:
  %(prog)s next-id
  %(prog)s list --type FEAT --priority P2
  %(prog)s count
  %(prog)s count --json
  %(prog)s count --type BUG
  %(prog)s show FEAT-518
  %(prog)s sequence --limit 10
  %(prog)s impact-effort
  %(prog)s refine-status
  %(prog)s refine-status --type BUG
  %(prog)s refine-status --format json
  %(prog)s refine-status --json
""",
    )

    subs = parser.add_subparsers(dest="command", help="Available commands")

    nid = subs.add_parser("next-id", aliases=["ni"], help="Print next globally unique issue number")
    nid.set_defaults(command="next-id")
    add_config_arg(nid)

    ls = subs.add_parser("list", aliases=["l"], help="List active issues")
    ls.set_defaults(command="list")
    ls.add_argument("--type", choices=["BUG", "FEAT", "ENH"], help="Filter by issue type")
    ls.add_argument(
        "--priority",
        choices=["P0", "P1", "P2", "P3", "P4", "P5"],
        help="Filter by priority level",
    )
    ls.add_argument(
        "--flat",
        action="store_true",
        help="Output flat list (current format) for scripting compatibility",
    )
    ls.add_argument("--json", action="store_true", help="Output as JSON array")
    add_config_arg(ls)

    cnt = subs.add_parser("count", aliases=["c"], help="Count active issues")
    cnt.set_defaults(command="count")
    cnt.add_argument("--type", choices=["BUG", "FEAT", "ENH"], help="Filter by issue type")
    cnt.add_argument(
        "--priority",
        choices=["P0", "P1", "P2", "P3", "P4", "P5"],
        help="Filter by priority level",
    )
    cnt.add_argument("--json", action="store_true", help="Output as JSON with breakdowns")
    add_config_arg(cnt)

    seq = subs.add_parser(
        "sequence", aliases=["seq"], help="Suggest implementation order based on dependencies"
    )
    seq.set_defaults(command="sequence")
    seq.add_argument(
        "--limit", type=int, default=10, help="Maximum number of issues to show (default: 10)"
    )
    add_config_arg(seq)

    show = subs.add_parser("show", aliases=["s"], help="Show summary card for an issue")
    show.set_defaults(command="show")
    show.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")
    add_config_arg(show)

    ie = subs.add_parser("impact-effort", aliases=["ie"], help="Display impact vs effort matrix")
    ie.set_defaults(command="impact-effort")
    add_config_arg(ie)

    refine_s = subs.add_parser(
        "refine-status",
        aliases=["rs"],
        help="Show refinement depth table sorted by commands touched",
    )
    refine_s.set_defaults(command="refine-status")
    refine_s.add_argument("--type", choices=["BUG", "FEAT", "ENH"], help="Filter by issue type")
    refine_s.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    refine_s.add_argument(
        "--no-key",
        action="store_true",
        default=False,
        help="Suppress the Key section below the table",
    )
    refine_s.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output as JSON array. Matches ll-issues list --json interface. (--format json outputs NDJSON instead)",
    )
    add_config_arg(refine_s)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)

    from little_loops.cli.output import configure_output

    configure_output(config.cli)

    if args.command == "next-id":
        return cmd_next_id(config)
    if args.command == "list":
        return cmd_list(config, args)
    if args.command == "count":
        return cmd_count(config, args)
    if args.command == "sequence":
        return cmd_sequence(config, args)
    if args.command == "show":
        return cmd_show(config, args)
    if args.command == "impact-effort":
        return cmd_impact_effort(config, args)
    if args.command == "refine-status":
        return cmd_refine_status(config, args)
    return 1
