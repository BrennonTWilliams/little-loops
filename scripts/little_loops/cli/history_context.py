"""ll-history-context: render a Historical Context block for an issue.

Queries .ll/history.db for user corrections and FTS5 matches relevant to an
issue ID and prints a ready-to-inject ``## Historical Context`` markdown block.
Returns empty output when the DB is missing, has no matches, or all rows are
stale.

Pass ``--project`` instead of an issue ID to print the project-wide context
digest that the session-start hook would inject (inspection / config-tuning
dry-run, ENH-1907).

Usage:
    ll-history-context <issue_id> [--file <path>] [--db <path>]
    ll-history-context --project [--db <path>]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.config.core import resolve_config_path
from little_loops.history_reader import (
    STALE_DAYS_DEFAULT,
    SearchResult,
    UserCorrection,
    find_user_corrections,
    project_digest,
    recent_file_events,
    render_project_context,
    search,
)
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

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
  %(prog)s --project                        # Print project-wide context digest
""",
    )
    parser.add_argument(
        "issue_id",
        metavar="ISSUE_ID",
        nargs="?",
        default=None,
        help="Issue ID to query (e.g. ENH-1708). Mutually exclusive with --project.",
    )
    parser.add_argument(
        "--project",
        action="store_true",
        default=False,
        help="Print the project-wide context digest (dry-run of session-start injection).",
    )
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
    with cli_event_context(DEFAULT_DB_PATH, "ll-history-context", sys.argv[1:]):
        configure_output()
        logger = Logger(use_color=use_color_enabled())  # noqa: F841

        parser = _build_parser()
        args = parser.parse_args()

        # Mutual-exclusion guard: require exactly one of issue_id or --project.
        if args.project and args.issue_id:
            parser.error("--project and ISSUE_ID are mutually exclusive")
        if not args.project and not args.issue_id:
            parser.error("one of ISSUE_ID or --project is required")

        # --project: print the project-wide digest dry-run and exit.
        if args.project:
            from little_loops.config.features import HistoryConfig

            cwd = Path.cwd()
            config_path = resolve_config_path(cwd)
            if config_path is not None:
                import json

                try:
                    merged = json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    merged = {}
            else:
                merged = {}

            _hist = HistoryConfig.from_dict(merged.get("history", {}))
            _sd = _hist.session_digest
            _sections = _sd.sections if _sd.sections else None
            digest = project_digest(args.db, days=_sd.days, sections=_sections)
            block = render_project_context(digest, char_cap=_sd.char_cap, days=_sd.days)
            if block:
                print(block)
            return 0

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
