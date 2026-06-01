"""ll-history-context: render a Historical Context block for an issue.

Queries .ll/history.db for user corrections and FTS5 matches relevant to an
issue ID and prints a ready-to-inject ``## Historical Context`` markdown block.
Returns empty output when the DB is missing, has no matches, or all rows are
stale.

Usage:
    ll-history-context <issue_id> [--file <path>] [--db <path>]
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.history_reader import (
    STALE_DAYS_DEFAULT,
    SearchResult,
    UserCorrection,
    find_user_corrections,
    recent_file_events,
    search,
)
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH

_MAX_ROWS = 5


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ll-history-context",
        description="Render a ## Historical Context block for an issue from .ll/history.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ENH-1708                        # Corrections matching the issue ID
  %(prog)s ENH-1708 --file src/foo.py      # Also include recent file events
  %(prog)s ENH-1708 --db custom/history.db # Use a non-default database
""",
    )
    parser.add_argument("issue_id", metavar="ISSUE_ID", help="Issue ID to query (e.g. ENH-1708)")
    parser.add_argument(
        "--file",
        metavar="PATH",
        default=None,
        help="Also include recent file events for this path",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the session database (default: .ll/history.db)",
    )
    return parser


def main_history_context() -> int:
    """Entry point for ll-history-context command.

    Returns:
        0 on success (including empty output when no matches or DB absent), 1 on argument error.
    """
    configure_output()
    logger = Logger(use_color=use_color_enabled())  # noqa: F841

    parser = _build_parser()
    args = parser.parse_args()

    cutoff = (datetime.now(UTC) - timedelta(days=STALE_DAYS_DEFAULT)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    corrections: list[UserCorrection] = find_user_corrections(
        topic=args.issue_id, limit=20, db=args.db
    )

    search_results: list[SearchResult] = search(
        query=args.issue_id, kind="correction", limit=20, db=args.db
    )
    fresh_search = [r for r in search_results if r.ts >= cutoff]

    file_contents: list[str] = []
    if args.file:
        for fe in recent_file_events(path=args.file, limit=5, db=args.db):
            file_contents.append(f"file:{fe.path}:{fe.op}")

    seen: set[str] = set()
    rows: list[str] = []

    for uc in corrections:
        h = _content_hash(uc.content)
        if h not in seen:
            seen.add(h)
            rows.append(uc.content)

    for sr in fresh_search:
        h = _content_hash(sr.content)
        if h not in seen:
            seen.add(h)
            rows.append(sr.content)

    for fc in file_contents:
        h = _content_hash(fc)
        if h not in seen:
            seen.add(h)
            rows.append(fc)

    rows = rows[:_MAX_ROWS]

    if not rows:
        return 0

    print("## Historical Context")
    print()
    for row in rows:
        print(f"- {row}")

    return 0
