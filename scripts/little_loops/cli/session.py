"""ll-session: query the unified session store (SQLite + FTS5).

Wraps :mod:`little_loops.session_store` with a CLI surface so operators can
search and inspect the per-project ``.ll/history.db`` without re-parsing the
scattered JSON/markdown sources the analyze-* skills read.

Subcommands:
    search   FTS5 full-text query with BM25-ranked results and optional --kind filter
    recent   most recent rows for an event kind (tool, file, issue, loop, correction)
    backfill seed the database from existing on-disk sources
    related  issue events for a given issue ID
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.history_reader import related_issue_events
from little_loops.history_reader import search as history_search
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, backfill, connect, recent, search


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ll-session."""
    parser = argparse.ArgumentParser(
        prog="ll-session",
        description="Query the unified session store (SQLite + FTS5)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s search --fts "rate limit"              # Full-text search, BM25-ranked
  %(prog)s search --fts "error" --kind loop       # FTS5 search filtered by kind
  %(prog)s recent --kind loop                     # Recent loop events
  %(prog)s related BUG-1759                       # Events for a specific issue
  %(prog)s backfill                               # Seed the database from on-disk sources
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

    path_parser = subparsers.add_parser("path", help="Resolve JSONL file path for a session ID")
    path_parser.add_argument("session_id", metavar="SESSION_ID", help="Session ID to look up")

    search_parser = subparsers.add_parser("search", help="FTS5 full-text search")
    search_parser.add_argument("--fts", required=True, metavar="QUERY", help="FTS5 match query")
    search_parser.add_argument(
        "--kind",
        choices=["tool", "file", "issue", "loop", "correction", "message"],
        default=None,
        help="Filter results by event kind",
    )
    search_parser.add_argument(
        "--limit", type=int, default=20, metavar="N", help="Maximum results (default: 20)"
    )
    add_json_arg(search_parser)

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
    recent_parser.add_argument(
        "--json", action="store_true", dest="json", help="Output as JSON array"
    )

    related_parser = subparsers.add_parser("related", help="Issue events for an issue ID")
    related_parser.add_argument("issue_id", metavar="ISSUE_ID", help="Issue ID (e.g., BUG-1759)")
    related_parser.add_argument(
        "--limit", type=int, default=20, metavar="N", help="Maximum results (default: 20)"
    )
    add_json_arg(related_parser)

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

    if args.command == "path":
        conn = connect(args.db)
        try:
            row = conn.execute(
                "SELECT jsonl_path FROM sessions WHERE session_id = ?", (args.session_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            print(f"Session {args.session_id} not found.")
            return 1
        print(row["jsonl_path"])
        return 0

    if args.command == "search":
        results: list[Any]
        if args.kind:
            results = history_search(args.fts, kind=args.kind, limit=args.limit, db=args.db)
        else:
            try:
                results = search(args.db, query=args.fts, limit=args.limit)
            except ValueError as exc:
                logger.error(str(exc))
                return 1
        if args.json:
            if (
                isinstance(results, list)
                and results
                and hasattr(results[0], "__dataclass_fields__")
            ):
                from dataclasses import asdict

                results = [asdict(r) for r in results]
            print_json(list(results))
            return 0
        if not results:
            print("No matches.")
            return 0
        for row in results:
            if hasattr(row, "__dataclass_fields__"):
                anchor = f"  ({row.anchor})" if row.anchor else ""
                print(f"[{row.kind}] {row.content}{anchor}")
            else:
                anchor = f"  ({row['anchor']})" if row.get("anchor") else ""
                print(f"[{row['kind']}] {row['content']}{anchor}")
        return 0

    if args.command == "related":
        events = related_issue_events(args.issue_id, limit=args.limit, db=args.db)
        if args.json:
            from dataclasses import asdict

            print_json([asdict(e) for e in events])
            return 0
        if not events:
            print(f"No events for {args.issue_id}.")
            return 0
        for e in events:
            fields = ", ".join(
                f"{k}={getattr(e, k)}"
                for k in ("ts", "transition", "issue_type", "priority")
                if getattr(e, k)
            )
            print(fields)
        return 0

    if args.command == "recent":
        rows = recent(args.db, kind=args.kind, limit=args.limit)
        if args.json:
            print_json(list(rows))
            return 0
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
            f"tools={counts['tools']}, messages={counts.get('messages', 0)}, "
            f"sessions={counts.get('sessions', 0)})"
        )
        return 0

    return 1
