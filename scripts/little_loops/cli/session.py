"""ll-session: query the unified session store (SQLite + FTS5).

Wraps :mod:`little_loops.session_store` with a CLI surface so operators can
search and inspect the per-project ``.ll/history.db`` without re-parsing the
scattered JSON/markdown sources the analyze-* skills read.

Subcommands:
    search   FTS5 full-text query with BM25-ranked results
    recent   most recent rows for an event kind (tool, file, issue, loop, correction)
    backfill seed the database from existing on-disk sources
"""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, backfill, recent, search


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ll-session."""
    parser = argparse.ArgumentParser(
        prog="ll-session",
        description="Query the unified session store (SQLite + FTS5)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s search --fts "rate limit"   # Full-text search, BM25-ranked
  %(prog)s recent --kind loop          # Recent loop events
  %(prog)s backfill                    # Seed the database from on-disk sources
""",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the session database (default: .ll/history.db)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    search_parser = subparsers.add_parser("search", help="FTS5 full-text search")
    search_parser.add_argument("--fts", required=True, metavar="QUERY", help="FTS5 match query")
    search_parser.add_argument(
        "--limit", type=int, default=20, metavar="N", help="Maximum results (default: 20)"
    )

    recent_parser = subparsers.add_parser("recent", help="Recent events by kind")
    recent_parser.add_argument(
        "--kind",
        required=True,
        choices=["tool", "file", "issue", "loop", "correction", "message"],
        help="Event kind to list",
    )
    recent_parser.add_argument(
        "--limit", type=int, default=20, metavar="N", help="Maximum rows (default: 20)"
    )

    subparsers.add_parser("backfill", help="Seed the database from existing on-disk sources")

    return parser


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments. Exposed for testing."""
    return _build_parser().parse_args()


def main_session() -> int:
    """Entry point for ll-session command.

    Returns:
        0 on success, 1 when no subcommand is given or on error.
    """
    configure_output()
    logger = Logger(use_color=use_color_enabled())

    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "search":
        try:
            results = search(args.db, query=args.fts, limit=args.limit)
        except ValueError as exc:
            logger.error(str(exc))
            return 1
        if not results:
            print("No matches.")
            return 0
        for row in results:
            anchor = f"  ({row['anchor']})" if row.get("anchor") else ""
            print(f"[{row['kind']}] {row['content']}{anchor}")
        return 0

    if args.command == "recent":
        rows = recent(args.db, kind=args.kind, limit=args.limit)
        if not rows:
            print(f"No {args.kind} events.")
            return 0
        for row in rows:
            fields = ", ".join(f"{k}={v}" for k, v in row.items() if k != "id" and v is not None)
            print(fields)
        return 0

    if args.command == "backfill":
        counts = backfill(args.db)
        total = sum(counts.values())
        logger.success(
            f"Backfilled {total} rows "
            f"(issues={counts['issues']}, loops={counts['loops']}, "
            f"tools={counts['tools']}, messages={counts.get('messages', 0)})"
        )
        return 0

    return 1
