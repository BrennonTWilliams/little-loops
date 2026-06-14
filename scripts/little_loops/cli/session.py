"""ll-session: query the unified session store (SQLite + FTS5).

Wraps :mod:`little_loops.session_store` with a CLI surface so operators can
search and inspect the per-project ``.ll/history.db`` without re-parsing the
scattered JSON/markdown sources the analyze-* skills read.

Subcommands:
    search   FTS5 full-text query with BM25-ranked results and optional --kind filter
    recent   most recent rows for an event kind (tool, file, issue, loop, correction, message, skill, cli)
    backfill seed the database from existing on-disk sources
    related  issue events for a given issue ID
    path     resolve JSONL file path for a session ID
    grep     regex search over message_events with covering summary node context
    expand   return message_events covered by a summary node
    describe metadata for a summary node
    prune    delete raw event rows older than configured max-age and VACUUM (ENH-1906)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.history_reader import (
    ll_describe,
    ll_expand,
    ll_grep,
    related_issue_events,
    sessions_for_issue,
)
from little_loops.history_reader import search as history_search
from little_loops.logger import Logger
from little_loops.session_store import (
    DEFAULT_DB_PATH,
    backfill,
    backfill_incremental,
    cli_event_context,
    connect,
    prune,
    recent,
    search,
)
from little_loops.user_messages import get_project_folder


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
  %(prog)s grep "auth middleware"                 # Regex search over message_events
  %(prog)s expand 42                              # Messages covered by summary node 42
  %(prog)s describe 42                            # Metadata for summary node 42
  %(prog)s prune --dry-run                        # Show what would be pruned
  %(prog)s prune                                  # Delete old raw events and VACUUM
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
        choices=["tool", "file", "issue", "loop", "correction", "message", "skill", "cli"],
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
        choices=["tool", "file", "issue", "loop", "correction", "message", "skill", "cli"],
        default=None,
        help="Event kind to list (required unless --issue is given)",
    )
    recent_parser.add_argument(
        "--issue",
        default=None,
        metavar="ID",
        help="Filter to sessions that touched this issue ID (e.g. ENH-1710)",
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

    backfill_parser = subparsers.add_parser(
        "backfill", help="Seed the database from existing on-disk sources"
    )
    backfill_parser.add_argument(
        "--since",
        metavar="DATE",
        default=None,
        help="Only process JSONL files modified after DATE (ISO 8601 or YYYY-MM-DD); uses incremental mode",
    )
    backfill_parser.add_argument(
        "--host",
        choices=["claude-code", "codex", "opencode", "pi"],
        default=None,
        help="Host to discover session logs for (default: auto-detect from LL_HOOK_HOST env)",
    )
    backfill_parser.add_argument(
        "--extract-decisions",
        action="store_true",
        default=False,
        dest="extract_decisions",
        help="After backfill, run extract-from-completed to mine completed issues for rules (ENH-2152)",
    )

    grep_parser = subparsers.add_parser(
        "grep", help="Regex search over message_events with summary node context"
    )
    grep_parser.add_argument("pattern", metavar="PATTERN", help="Regex pattern (case-insensitive)")
    grep_parser.add_argument(
        "--summary-id",
        type=int,
        default=None,
        metavar="ID",
        help="Restrict search to messages covered by this summary node ID",
    )
    grep_parser.add_argument(
        "--limit", type=int, default=50, metavar="N", help="Maximum results (default: 50)"
    )
    add_json_arg(grep_parser)

    expand_parser = subparsers.add_parser(
        "expand", help="Return message_events covered by a summary node"
    )
    expand_parser.add_argument(
        "summary_id", type=int, metavar="SUMMARY_ID", help="Summary node ID to expand"
    )
    add_json_arg(expand_parser)

    describe_parser = subparsers.add_parser("describe", help="Show metadata for a summary node")
    describe_parser.add_argument(
        "node_id", type=int, metavar="NODE_ID", help="Summary node ID to describe"
    )
    add_json_arg(describe_parser)

    prune_parser = subparsers.add_parser(
        "prune",
        help="Prune raw event rows older than configured max-age and VACUUM the database",
    )
    prune_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report which rows would be deleted without actually deleting them",
    )
    add_json_arg(prune_parser)

    return parser


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments. Exposed for testing."""
    return _build_parser().parse_args()


def _run_extract_decisions(since: str | None = None) -> None:
    """Invoke ll-issues decisions extract-from-completed after a backfill."""
    import subprocess
    import sys

    cmd = ["ll-issues", "decisions", "extract-from-completed"]
    if since:
        cmd += ["--since", since]
    try:
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            print("extract-from-completed exited non-zero; decisions.yaml unchanged", file=sys.stderr)
    except FileNotFoundError:
        print("ll-issues not found; skipping extract-from-completed", file=sys.stderr)


def main_session() -> int:
    """Entry point for ll-session command.

    Returns:
        0 on success, 1 when no subcommand is given or on error.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-session", sys.argv[1:]):
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
            issue_filter = getattr(args, "issue", None)

            # --issue only: show sessions that co-occurred with the issue
            if issue_filter and not args.kind:
                refs = sessions_for_issue(issue_filter, limit=args.limit, db=args.db)
                if args.json:
                    from dataclasses import asdict

                    print_json([asdict(r) for r in refs])
                    return 0
                if not refs:
                    print(f"No sessions found for {issue_filter}.")
                    return 0
                for r in refs:
                    path = r.jsonl_path or "(no path)"
                    print(f"{r.session_id}  {path}")
                return 0

            if not args.kind:
                logger.error("recent: --kind is required unless --issue is given")
                return 1

            rows = recent(args.db, kind=args.kind, limit=args.limit)
            if issue_filter:
                session_ids = {r.session_id for r in sessions_for_issue(issue_filter, db=args.db)}
                rows = [r for r in rows if r.get("session_id") in session_ids]
            if args.json:
                print_json(list(rows))
                return 0
            if not rows:
                print(f"No {args.kind} events.")
                return 0
            for row in rows:
                fields = ", ".join(
                    f"{k}={v}" for k, v in row.items() if k != "id" and v is not None
                )
                print(fields)
            return 0

        if args.command == "backfill":
            since_flag = getattr(args, "since", None)
            if since_flag is not None:
                from datetime import datetime

                try:
                    try:
                        dt = datetime.fromisoformat(since_flag.replace("Z", "+00:00"))
                    except ValueError:
                        dt = datetime.strptime(since_flag, "%Y-%m-%d")
                    since_ts = dt.timestamp()
                except ValueError:
                    logger.error(f"Invalid date: {since_flag!r}. Use YYYY-MM-DD or ISO 8601.")
                    return 1
                project_folder = get_project_folder(host=args.host)
                if project_folder is None:
                    logger.error("No session project folder found; cannot discover JSONL files.")
                    return 1
                jsonl_files = list(project_folder.glob("*.jsonl"))
                inc_counts = backfill_incremental(
                    args.db, jsonl_files=jsonl_files, since_ts=since_ts
                )
                inc_total = sum(inc_counts.values())
                logger.success(
                    f"Backfilled {inc_total} rows (incremental, since {since_flag}; "
                    f"tools={inc_counts['tools']}, messages={inc_counts['messages']}, "
                    f"sessions={inc_counts['sessions']}, corrections={inc_counts.get('corrections', 0)})"
                )
                if getattr(args, "extract_decisions", False):
                    _run_extract_decisions(since=since_flag)
                return 0
            # Full backfill (no --since): discover JSONL files so non-Claude-Code
            # hosts also get message/tool/session backfill (ENH-1945).
            project_folder = get_project_folder(host=args.host)
            full_jsonl_files: list[Path] | None = (
                list(project_folder.glob("*.jsonl")) if project_folder else None
            )
            counts = backfill(args.db, jsonl_files=full_jsonl_files)
            total = sum(counts.values())
            logger.success(
                f"Backfilled {total} rows "
                f"(issues={counts['issues']}, loops={counts['loops']}, "
                f"tools={counts['tools']}, messages={counts.get('messages', 0)}, "
                f"sessions={counts.get('sessions', 0)}, corrections={counts.get('corrections', 0)}, "
                f"summaries={counts.get('summaries', 0)})"
            )
            if getattr(args, "extract_decisions", False):
                _run_extract_decisions(since=None)
            return 0

        if args.command == "grep":
            grep_results = ll_grep(
                args.pattern,
                summary_id=args.summary_id,
                limit=args.limit,
                db=args.db,
            )
            if args.json:
                from dataclasses import asdict

                print_json([asdict(r) for r in grep_results])
                return 0
            if not grep_results:
                print("No matches.")
                return 0
            for gr in grep_results:
                node_info = f"  [node {gr.summary_id}/{gr.summary_kind}]" if gr.summary_id else ""
                snippet = gr.content[:120].replace("\n", " ")
                print(f"{gr.ts}  {snippet}{node_info}")
            return 0

        if args.command == "expand":
            messages = ll_expand(args.summary_id, db=args.db)
            if args.json:
                print_json(messages)
                return 0
            if not messages:
                print(f"No messages found for summary node {args.summary_id}.")
                return 0
            for m in messages:
                snippet = (m.get("content") or "")[:120].replace("\n", " ")
                print(f"{m.get('ts', '')}  {snippet}")
            return 0

        if args.command == "describe":
            node = ll_describe(args.node_id, db=args.db)
            if node is None:
                print(f"Summary node {args.node_id} not found.")
                return 1
            if args.json:
                from dataclasses import asdict

                print_json(asdict(node))
                return 0
            print(f"id={node.id}  kind={node.kind}  level={node.level}  session={node.session_id}")
            print(f"ts_start={node.ts_start}  ts_end={node.ts_end}")
            print(f"tokens={node.tokens}  created_at={node.created_at}")
            print(f"content: {node.content[:200]}")
            return 0

        if args.command == "prune":
            import json as _json

            from little_loops.config.core import resolve_config_path

            config: dict | None = None
            config_path = resolve_config_path(Path.cwd())
            if config_path is not None:
                try:
                    config = _json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    config = None

            result = prune(args.db, config=config, dry_run=args.dry_run)

            if args.json:
                print_json(result)
                return 0

            if args.dry_run:
                print("DRY RUN — no rows deleted\n")

            if result["gate_unmet"]:
                print("Gates unmet — pruning skipped:")
                for reason in result["gate_unmet"]:
                    print(f"  {reason}")
                print(
                    f"\nDB: {result['db_size_mb']:.1f} MB  |  "
                    f"project age: {result['project_age_days']}d"
                )
                return 0

            if not result["pruned"]:
                print("No pruning configured (raw_event_max_age_days is null).")
                return 0

            deleted = result.get("deleted", {})
            total = sum(deleted.values())
            if total == 0:
                print("Gates met — no eligible rows found.")
            else:
                label = "Would delete" if args.dry_run else "Deleted"
                for table, count in deleted.items():
                    print(f"  {table}: {count:,} rows")
                print(f"\n{label} {total:,} rows total.")

            if not args.dry_run and result.get("vacuumed"):
                print("Database VACUUMed.")

            return 0

        return 1
