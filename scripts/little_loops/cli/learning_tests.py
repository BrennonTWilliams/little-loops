"""ll-learning-tests: CLI for querying and managing the learning test registry."""

from __future__ import annotations

import argparse
import sys

from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["main_learning_tests"]


def cmd_check(args: argparse.Namespace) -> int:
    from little_loops.cli.output import print_json
    from little_loops.learning_tests import check_learning_test

    record = check_learning_test(args.target)
    if record is None:
        print(f"Error: no record found for {args.target!r}", file=sys.stderr)
        return 1
    print_json(record.to_dict())
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    from little_loops.cli.output import print_json
    from little_loops.learning_tests import list_records

    records = list_records()
    print_json([r.to_dict() for r in records])
    return 0


def cmd_mark_stale(args: argparse.Namespace) -> int:
    from little_loops.issue_parser import slugify
    from little_loops.learning_tests import check_learning_test, mark_stale

    record = check_learning_test(args.target)
    if record is None:
        print(f"Error: no record found for {args.target!r}", file=sys.stderr)
        return 1
    mark_stale(slugify(args.target))
    return 0


def main_learning_tests() -> int:
    """CLI handler for ll-learning-tests subcommands."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-learning-tests", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-learning-tests",
            description="Query and manage the little-loops learning test registry",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ll-learning-tests check "Anthropic SDK streaming"
  ll-learning-tests list
  ll-learning-tests mark-stale "Anthropic SDK streaming"
""",
        )

        subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
        subparsers.required = True

        check_parser = subparsers.add_parser(
            "check",
            help="Print a record as JSON; exit 1 if not found",
            description="Look up a learning test record by target name and print as JSON",
        )
        check_parser.add_argument("target", help="Target name (e.g. 'Anthropic SDK streaming')")

        subparsers.add_parser(
            "list",
            help="Print all records as a JSON array",
            description="List all learning test records in the registry",
        )

        stale_parser = subparsers.add_parser(
            "mark-stale",
            help="Mark a record as stale; exit 1 if not found",
            description="Set status=stale on a learning test record",
        )
        stale_parser.add_argument("target", help="Target name (e.g. 'Anthropic SDK streaming')")

        parsed = parser.parse_args()

        if parsed.command == "check":
            return cmd_check(parsed)
        elif parsed.command == "list":
            return cmd_list(parsed)
        elif parsed.command == "mark-stale":
            return cmd_mark_stale(parsed)
        else:
            parser.print_help()
            return 1
