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
    from little_loops.cli.issues.impact_effort import cmd_impact_effort
    from little_loops.cli.issues.list_cmd import cmd_list
    from little_loops.cli.issues.next_id import cmd_next_id
    from little_loops.cli.issues.sequence import cmd_sequence
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
  sequence       Suggest dependency-ordered implementation sequence
  impact-effort  Display impact vs effort matrix for active issues

Examples:
  %(prog)s next-id
  %(prog)s list --type FEAT --priority P2
  %(prog)s sequence --limit 10
  %(prog)s impact-effort
""",
    )

    subs = parser.add_subparsers(dest="command", help="Available commands")

    nid = subs.add_parser("next-id", help="Print next globally unique issue number")
    add_config_arg(nid)

    ls = subs.add_parser("list", help="List active issues")
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
    add_config_arg(ls)

    seq = subs.add_parser("sequence", help="Suggest implementation order based on dependencies")
    seq.add_argument(
        "--limit", type=int, default=10, help="Maximum number of issues to show (default: 10)"
    )
    add_config_arg(seq)

    ie = subs.add_parser("impact-effort", help="Display impact vs effort matrix")
    add_config_arg(ie)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)

    if args.command == "next-id":
        return cmd_next_id(config)
    if args.command == "list":
        return cmd_list(config, args)
    if args.command == "sequence":
        return cmd_sequence(config, args)
    if args.command == "impact-effort":
        return cmd_impact_effort(config, args)
    return 1
