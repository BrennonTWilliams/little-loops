"""ll-sprint: Sprint and sequence management with dependency-aware execution."""

from __future__ import annotations

import argparse

# Re-export for backward compatibility (used in tests and cli/__init__.py)
from little_loops.cli.sprint._helpers import _render_execution_plan
from little_loops.cli.sprint.create import _cmd_sprint_create
from little_loops.cli.sprint.edit import _cmd_sprint_edit
from little_loops.cli.sprint.manage import _cmd_sprint_analyze, _cmd_sprint_delete, _cmd_sprint_list
from little_loops.cli.sprint.run import (
    _cleanup_sprint_state,
    _cmd_sprint_run,
    _get_sprint_state_file,
    _load_sprint_state,
    _save_sprint_state,
    _sprint_signal_handler,
)
from little_loops.cli.sprint.show import (
    _cmd_sprint_show,
    _render_dependency_graph,
    _render_health_summary,
)

__all__ = [
    "main_sprint",
    "_render_execution_plan",
    "_render_dependency_graph",
    "_render_health_summary",
    "_cmd_sprint_create",
    "_cmd_sprint_show",
    "_cmd_sprint_edit",
    "_cmd_sprint_list",
    "_cmd_sprint_delete",
    "_cmd_sprint_analyze",
    "_cmd_sprint_run",
    "_sprint_signal_handler",
    "_get_sprint_state_file",
    "_load_sprint_state",
    "_save_sprint_state",
    "_cleanup_sprint_state",
]


def main_sprint() -> int:
    """Entry point for ll-sprint command.

    Manage and execute sprint/sequence definitions.

    Returns:
        Exit code (0 = success)
    """
    from little_loops.cli_args import (
        add_config_arg,
        add_dry_run_arg,
        add_max_workers_arg,
        add_quiet_arg,
        add_resume_arg,
        add_skip_analysis_arg,
        add_skip_arg,
        add_timeout_arg,
        add_type_arg,
    )
    from little_loops.config import BRConfig
    from little_loops.sprint import SprintManager

    parser = argparse.ArgumentParser(
        prog="ll-sprint",
        description="Manage and execute sprint/sequence definitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s create sprint-1 --issues BUG-001,FEAT-010 --description "Q1 fixes"
  %(prog)s run sprint-1
  %(prog)s run sprint-1 --dry-run
  %(prog)s list
  %(prog)s show sprint-1
  %(prog)s edit sprint-1 --add BUG-045,ENH-050
  %(prog)s edit sprint-1 --remove BUG-001
  %(prog)s edit sprint-1 --prune
  %(prog)s edit sprint-1 --revalidate
  %(prog)s delete sprint-1
  %(prog)s analyze sprint-1
  %(prog)s analyze sprint-1 --format json
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create subcommand
    create_parser = subparsers.add_parser("create", help="Create a new sprint")
    create_parser.add_argument("name", help="Sprint name (used as filename)")
    create_parser.add_argument(
        "--issues",
        required=True,
        help="Comma-separated issue IDs (e.g., BUG-001,FEAT-010)",
    )
    create_parser.add_argument("--description", "-d", default="", help="Sprint description")
    add_max_workers_arg(create_parser, default=2)
    add_timeout_arg(create_parser, default=3600)
    add_skip_arg(
        create_parser,
        help_text=(
            "Comma-separated list of issue IDs to exclude from sprint (e.g., BUG-003,FEAT-004)"
        ),
    )
    add_type_arg(create_parser)

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Execute a sprint")
    run_parser.add_argument("sprint", help="Sprint name to execute")
    add_dry_run_arg(run_parser)
    add_max_workers_arg(run_parser)
    add_timeout_arg(run_parser)
    add_config_arg(run_parser)
    add_resume_arg(run_parser)
    add_quiet_arg(run_parser)
    add_skip_arg(
        run_parser,
        help_text=(
            "Comma-separated list of issue IDs to skip during execution (e.g., BUG-003,FEAT-004)"
        ),
    )
    add_skip_analysis_arg(run_parser)
    add_type_arg(run_parser)

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List all sprints")
    list_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed information"
    )

    # show subcommand
    show_parser = subparsers.add_parser("show", help="Show sprint details")
    show_parser.add_argument("sprint", help="Sprint name to show")
    add_config_arg(show_parser)
    add_skip_analysis_arg(show_parser)

    # edit subcommand
    edit_parser = subparsers.add_parser("edit", help="Edit a sprint's issue list")
    edit_parser.add_argument("sprint", help="Sprint name to edit")
    edit_parser.add_argument(
        "--add",
        default=None,
        help="Comma-separated issue IDs to add (e.g., BUG-045,ENH-050)",
    )
    edit_parser.add_argument(
        "--remove",
        default=None,
        help="Comma-separated issue IDs to remove",
    )
    edit_parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove invalid (missing file) and completed issue references",
    )
    edit_parser.add_argument(
        "--revalidate",
        action="store_true",
        help="Re-run dependency analysis after edits",
    )
    add_config_arg(edit_parser)

    # delete subcommand
    delete_parser = subparsers.add_parser("delete", help="Delete a sprint")
    delete_parser.add_argument("sprint", help="Sprint name to delete")

    # analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze sprint for file conflicts between issues"
    )
    analyze_parser.add_argument("sprint", help="Sprint name to analyze")
    analyze_parser.add_argument(
        "-f",
        "--format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    add_config_arg(analyze_parser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Commands that don't need project root
    if args.command == "list":
        return _cmd_sprint_list(args, SprintManager())
    if args.command == "delete":
        return _cmd_sprint_delete(args, SprintManager())

    # Commands that need project root
    from pathlib import Path

    project_root = args.config if hasattr(args, "config") and args.config else Path.cwd()
    config = BRConfig(project_root)
    manager = SprintManager(config=config)

    if args.command == "create":
        return _cmd_sprint_create(args, manager)
    if args.command == "show":
        return _cmd_sprint_show(args, manager)
    if args.command == "edit":
        return _cmd_sprint_edit(args, manager)
    if args.command == "run":
        return _cmd_sprint_run(args, manager, config)
    if args.command == "analyze":
        return _cmd_sprint_analyze(args, manager)

    return 1
