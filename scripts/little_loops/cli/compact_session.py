"""ll-compact-session: manually trigger session-memory compaction for one session (FEAT-2598).

Runs the same LCM compaction path (``session_store.compact_session``) the
soft-threshold background summarizer uses automatically, then prints the
resulting :class:`~little_loops.compaction.result.CompactResult`.

Distinct from ``ll-session compact``, which sweeps the *retention* axis
(``kind='retention'`` raw_events summarization, ENH-1906/ENH-2581) — this
command operates on the LCM/``summary_nodes`` compaction axis instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.compaction.result import compact_result_for_session
from little_loops.config.core import resolve_config_path
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context, compact_session


def _build_parser() -> argparse.ArgumentParser:
    """Build the ll-compact-session argument parser (exposed for testing)."""
    parser = argparse.ArgumentParser(
        prog="ll-compact-session",
        description=(
            "Manually trigger LCM session-memory compaction for one session "
            "(distinct from the 'll-session compact' retention sweep)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s SESSION_ID              # Compact one session, print the resulting summary
  %(prog)s SESSION_ID --json       # Output the CompactResult as JSON
""",
    )
    parser.add_argument("session_id", metavar="SESSION_ID", help="Session ID to compact")
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB_PATH, help="Path to the session database"
    )
    add_json_arg(parser)
    return parser


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse argv into a Namespace (exposed for testing)."""
    return _build_parser().parse_args(argv)


def main_compact_session(argv: list[str] | None = None) -> int:
    """Entry point for the ll-compact-session command."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-compact-session", sys.argv[1:]):
        args = _parse_args(argv)
        configure_output()
        logger = Logger(use_color=use_color_enabled())

        config_path = resolve_config_path(Path.cwd())
        config = None
        if config_path is not None:
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                config = None

        new_leaves = compact_session(args.session_id, args.db, config=config)
        result = compact_result_for_session(args.session_id, args.db)

        if args.json:
            print_json(
                {
                    "session_id": args.session_id,
                    "new_leaves": new_leaves,
                    "summary_text": result.summary_text if result else None,
                    "compacted_messages": result.compacted_messages if result else [],
                    "context_token_estimate": result.context_token_estimate if result else 0,
                }
            )
            return 0

        if result is None:
            logger.warning(f"No condensed summary produced for session {args.session_id}.")
            return 0

        logger.success(
            f"Compacted session {args.session_id}: {new_leaves} new leaf node(s), "
            f"~{result.context_token_estimate} token summary covering "
            f"{len(result.compacted_messages)} message(s)."
        )
        print()
        print(result.summary_text)
        return 0
