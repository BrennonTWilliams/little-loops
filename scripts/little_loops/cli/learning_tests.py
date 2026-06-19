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

    if getattr(args, "stale_aware", False):
        import json as _json
        from pathlib import Path

        from little_loops.config.core import resolve_config_path
        from little_loops.config.features import LearningTestsConfig
        from little_loops.learning_tests.gate import is_record_stale

        config_path = resolve_config_path(Path.cwd())
        lt_config = LearningTestsConfig()
        if config_path is not None:
            try:
                data = _json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    lt_config = LearningTestsConfig.from_dict(data.get("learning_tests", {}))
            except (OSError, _json.JSONDecodeError):
                pass

        if record.status != "proven" or is_record_stale(record, lt_config.stale_after_days):
            return 1

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


def cmd_orphans(args: argparse.Namespace) -> int:
    import json as _json
    from pathlib import Path

    from little_loops.config.core import resolve_config_path
    from little_loops.issue_parser import slugify
    from little_loops.learning_tests import list_records, mark_stale
    from little_loops.learning_tests.import_scan import get_imported_packages

    source_dirs: list[Path]
    if args.scope:
        source_dirs = [Path(d.strip()) for d in args.scope.split(",")]
    else:
        resolved: list[Path] | None = None
        config_path = resolve_config_path(Path.cwd())
        if config_path is not None:
            try:
                data = _json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    raw = data.get("learning_tests", {}).get("scan_dirs")
                    if raw:
                        resolved = [Path(d) for d in raw]
            except (OSError, _json.JSONDecodeError):
                pass
        source_dirs = resolved if resolved is not None else [Path("scripts/")]

    imported = get_imported_packages(source_dirs)

    records = list_records()
    orphans = [r for r in records if r.target.split()[0].lower() not in imported]

    if not orphans:
        print("No orphaned records found.")
        return 0

    for record in orphans:
        print(f"{record.target}  (status: {record.status}, date: {record.date})")

    if args.mark_stale:
        for record in orphans:
            mark_stale(slugify(record.target))
        print(f"\nMarked {len(orphans)} record(s) stale.")
        return 0

    return 1


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
        check_parser.add_argument(
            "--stale-aware",
            action="store_true",
            default=False,
            dest="stale_aware",
            help=(
                "Exit 1 if the record is absent or date-stale "
                "(even if status=proven); exit 0 only if proven and within stale_after_days threshold"
            ),
        )

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

        orphans_parser = subparsers.add_parser(
            "orphans",
            help="List records for packages no longer imported; exit 1 if any found",
            description=(
                "Detect learning test records whose target package is no longer imported "
                "anywhere in the configured source directories."
            ),
        )
        orphans_parser.add_argument(
            "--mark-stale",
            action="store_true",
            default=False,
            dest="mark_stale",
            help="Atomically mark all orphaned records stale and exit 0",
        )
        orphans_parser.add_argument(
            "--scope",
            default=None,
            metavar="DIRS",
            help=(
                "Comma-separated list of directories to scan for imports "
                "(default: learning_tests.scan_dirs config key, fallback 'scripts/')"
            ),
        )

        parsed = parser.parse_args()

        if parsed.command == "check":
            return cmd_check(parsed)
        elif parsed.command == "list":
            return cmd_list(parsed)
        elif parsed.command == "mark-stale":
            return cmd_mark_stale(parsed)
        elif parsed.command == "orphans":
            return cmd_orphans(parsed)
        else:
            parser.print_help()
            return 1
