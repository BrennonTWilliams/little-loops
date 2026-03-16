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
    from little_loops.cli.issues.append_log import cmd_append_log
    from little_loops.cli.issues.count_cmd import cmd_count
    from little_loops.cli.issues.impact_effort import cmd_impact_effort
    from little_loops.cli.issues.list_cmd import cmd_list
    from little_loops.cli.issues.next_id import cmd_next_id
    from little_loops.cli.issues.refine_status import cmd_refine_status
    from little_loops.cli.issues.search import cmd_search
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
  search         Search issues with filters and sorting
  count          Count active issues (total or filtered)
  show           Show summary card for a single issue
  sequence       Suggest dependency-ordered implementation sequence
  impact-effort  Display impact vs effort matrix for active issues
  refine-status  Show refinement depth table sorted by commands touched
  append-log     Append a session log entry to an issue file

Examples:
  %(prog)s next-id
  %(prog)s list --type FEAT --priority P2
  %(prog)s search "caching" --include-completed
  %(prog)s search --type BUG --priority P0-P2 --sort date
  %(prog)s search --since 2026-01-01 --json
  %(prog)s count
  %(prog)s count --json
  %(prog)s count --type BUG
  %(prog)s show FEAT-518
  %(prog)s sequence --limit 10
  %(prog)s impact-effort
  %(prog)s impact-effort --type BUG
  %(prog)s refine-status
  %(prog)s refine-status --type BUG
  %(prog)s refine-status --format json
  %(prog)s refine-status --json
  %(prog)s append-log .issues/bugs/P2-BUG-123-foo.md /ll:refine-issue
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
        "--status",
        choices=["active", "completed", "deferred", "all"],
        default="active",
        help="Filter by status (default: active)",
    )
    ls.add_argument(
        "--flat",
        action="store_true",
        help="Output flat list (current format) for scripting compatibility",
    )
    ls.add_argument("--json", action="store_true", help="Output as JSON array")
    ls.add_argument("--limit", "-n", type=int, metavar="N", default=None, help="Cap output at N issues (must be ≥ 1)")
    add_config_arg(ls)

    sr = subs.add_parser("search", aliases=["sr"], help="Search issues with filters and sorting")
    sr.set_defaults(command="search")
    sr.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Text to match against title and body (case-insensitive)",
    )
    sr.add_argument(
        "--type",
        choices=["BUG", "FEAT", "ENH"],
        action="append",
        dest="type",
        metavar="TYPE",
        help="Filter by issue type: BUG, FEAT, ENH (repeatable)",
    )
    sr.add_argument(
        "--priority",
        action="append",
        dest="priority",
        metavar="P",
        help="Filter by priority: P0-P5 or range e.g. P0-P2 (repeatable)",
    )
    sr.add_argument(
        "--status",
        choices=["active", "completed", "deferred", "all"],
        default="active",
        help="Filter by status (default: active)",
    )
    sr.add_argument(
        "--include-completed",
        action="store_true",
        default=False,
        dest="include_completed",
        help="Include completed issues (alias for --status all)",
    )
    sr.add_argument(
        "--label",
        action="append",
        dest="label",
        metavar="LABEL",
        help="Filter by label tag (repeatable)",
    )
    sr.add_argument("--since", metavar="DATE", help="Only issues on or after DATE (YYYY-MM-DD)")
    sr.add_argument("--until", metavar="DATE", help="Only issues on or before DATE (YYYY-MM-DD)")
    sr.add_argument(
        "--date-field",
        choices=["discovered", "updated"],
        default="discovered",
        dest="date_field",
        help="Date field to filter on (default: discovered)",
    )
    sr.add_argument(
        "--sort",
        choices=["priority", "id", "date", "type", "title"],
        default="priority",
        help="Sort field (default: priority)",
    )
    sr.add_argument("--asc", action="store_true", default=False, help="Sort ascending")
    sr.add_argument("--desc", action="store_true", default=False, help="Sort descending")
    sr.add_argument("--json", action="store_true", help="Output as JSON array")
    sr.add_argument(
        "--format",
        choices=["table", "list", "ids"],
        default="table",
        help="Output format: table (default), list, ids",
    )
    sr.add_argument("--limit", type=int, metavar="N", help="Cap results at N")
    add_config_arg(sr)

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
    seq.add_argument("--json", action="store_true", help="Output as JSON array")
    add_config_arg(seq)

    show = subs.add_parser("show", aliases=["s"], help="Show summary card for an issue")
    show.set_defaults(command="show")
    show.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")
    show.add_argument("--json", action="store_true", help="Output as JSON")
    add_config_arg(show)

    ie = subs.add_parser("impact-effort", aliases=["ie"], help="Display impact vs effort matrix")
    ie.set_defaults(command="impact-effort")
    ie.add_argument("--type", choices=["BUG", "FEAT", "ENH"], help="Filter by issue type")
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

    al = subs.add_parser(
        "append-log",
        aliases=["al"],
        help="Append a session log entry to an issue file",
    )
    al.set_defaults(command="append-log")
    al.add_argument("issue_path", help="Path to the issue markdown file")
    al.add_argument("log_command", help="Command name (e.g., /ll:refine-issue)")
    add_config_arg(al)

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
    if args.command == "search":
        return cmd_search(config, args)
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
    if args.command == "append-log":
        return cmd_append_log(config, args)
    return 1
