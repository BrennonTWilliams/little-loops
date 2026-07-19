"""ll-session: query the unified session store (SQLite + FTS5).

Wraps :mod:`little_loops.session_store` with a CLI surface so operators can
search and inspect the per-project ``.ll/history.db`` without re-parsing the
scattered JSON/markdown sources the analyze-* skills read.

Subcommands:
    search   FTS5 full-text query with BM25-ranked results and optional --kind filter
    recent   most recent rows for an event kind (tool, file, issue, loop, correction,
             message, skill, cli, snapshot, commit, test_run, usage, orchestration_run)
    skill-stats per-skill invocation/success-rate rollup (ENH-2460)
    backfill ingest on-disk sources into raw_events + issue/loop/commit tables (ENH-2581)
    rebuild  wipe+re-derive the JSONL-derived cache tables from raw_events (ENH-2581)
    compact  sweep old raw_events into per-session retention summaries (ENH-2581)
    related  issue events for a given issue ID
    path     resolve JSONL file path for a session ID
    grep     regex search over message_events with covering summary node context
    expand   return message_events covered by a summary node
    describe metadata for a summary node
    prune    delete compacted raw_events rows older than configured max-age and VACUUM (ENH-1906)
    recompress rewrite legacy uncompressed raw_events payloads as zlib BLOBs and VACUUM
    export   dump selected tables as JSONL for visualization or external tooling
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
    VALID_KINDS,
    backfill,
    backfill_incremental,
    backfill_snapshots,
    cli_event_context,
    compact,
    connect,
    export_history,
    prune,
    rebuild,
    recent,
    recompress_raw_events,
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
  %(prog)s backfill                               # Ingest on-disk sources (raw_events + issues/loops/commits)
  %(prog)s backfill --rebuild                     # Ingest, then materialize cache tables in one call
  %(prog)s rebuild                                # Re-derive cache tables from raw_events
  %(prog)s compact --and-prune                    # Sweep+summarize old raw_events, then delete
  %(prog)s grep "auth middleware"                 # Regex search over message_events
  %(prog)s expand 42                              # Messages covered by summary node 42
  %(prog)s describe 42                            # Metadata for summary node 42
  %(prog)s prune --dry-run                        # Show what would be pruned
  %(prog)s prune                                  # Delete old raw events and VACUUM
  %(prog)s recompress                             # Compress legacy raw_events payloads and VACUUM
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
        choices=list(VALID_KINDS),
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
        choices=list(VALID_KINDS),
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
        "--mcp-server",
        default=None,
        metavar="NAME",
        help="Filter --kind tool rows to this MCP server (ENH-2511)",
    )
    recent_parser.add_argument(
        "--mcp-tool",
        default=None,
        metavar="NAME",
        help="Filter --kind tool rows to this MCP tool (ENH-2511)",
    )
    recent_parser.add_argument(
        "--mcp-outcome",
        choices=["success", "error", "timeout"],
        default=None,
        help="Filter --kind tool rows to this MCP outcome (ENH-2511)",
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
    backfill_parser.add_argument(
        "--snapshots",
        action="store_true",
        default=False,
        help="Hydrate issue_snapshots table from existing .issues/ files (ENH-2151)",
    )
    backfill_parser.add_argument(
        "--max-sessions",
        type=int,
        default=None,
        metavar="N",
        dest="max_sessions",
        help="Cap the number of sessions compacted in this run (newest first); useful for large DBs",
    )
    backfill_parser.add_argument(
        "--rebuild",
        action="store_true",
        default=False,
        help=(
            "Also materialize the JSONL-derived cache tables from raw_events "
            "in this call (ingest + rebuild in one step; ENH-2581)"
        ),
    )

    rebuild_parser = subparsers.add_parser(
        "rebuild",
        help="Wipe+re-derive the JSONL-derived cache tables from raw_events (ENH-2581)",
    )
    rebuild_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to ll-config.json (default: auto-resolve from cwd)",
    )
    add_json_arg(rebuild_parser)

    compact_parser = subparsers.add_parser(
        "compact",
        help="Sweep old raw_events into per-session retention summaries (ENH-2581)",
    )
    compact_parser.add_argument(
        "--and-prune",
        action="store_true",
        default=False,
        dest="and_prune",
        help="Also delete the newly-compacted raw_events rows and VACUUM afterward",
    )
    compact_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to ll-config.json (default: auto-resolve from cwd)",
    )
    add_json_arg(compact_parser)

    export_parser = subparsers.add_parser(
        "export",
        help="Dump selected tables as JSONL for visualization or external tooling",
    )
    export_parser.add_argument(
        "--tables",
        nargs="+",
        metavar="TYPE",
        default=None,
        help=(
            "Types to include (default: all non-message tables). "
            "Choices: session, issue_event, issue_snapshot, skill_event, "
            "loop_event, correction, summary_node, message_event, commit_event, "
            "test_run_event, usage_event, orchestration_run, session_lifecycle_event"
        ),
    )
    export_parser.add_argument(
        "--since",
        metavar="DATE",
        default=None,
        help="Only rows at or after this ISO 8601 date/datetime",
    )
    export_parser.add_argument(
        "--include-messages",
        action="store_true",
        default=False,
        dest="include_messages",
        help="Also include message_events (~46 K rows); ignored when --tables is given",
    )
    export_parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default=None,
        help="Write output to FILE instead of stdout",
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

    skill_stats_parser = subparsers.add_parser(
        "skill-stats",
        help="Per-skill invocation/success-rate rollup from skill_events (ENH-2460)",
    )
    skill_stats_parser.add_argument(
        "--since",
        metavar="DATE",
        default=None,
        help="Only count rows at or after this ISO 8601 date/datetime",
    )
    add_json_arg(skill_stats_parser)

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

    recompress_parser = subparsers.add_parser(
        "recompress",
        help="Rewrite legacy uncompressed raw_events payloads as zlib BLOBs and VACUUM",
    )
    recompress_parser.add_argument(
        "--batch",
        type=int,
        default=2000,
        metavar="N",
        help="Rows to rewrite per transaction (default: 2000)",
    )
    add_json_arg(recompress_parser)

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
            print(
                "extract-from-completed exited non-zero; decisions.yaml unchanged", file=sys.stderr
            )
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

            mcp_server = getattr(args, "mcp_server", None)
            mcp_tool = getattr(args, "mcp_tool", None)
            mcp_outcome = getattr(args, "mcp_outcome", None)
            if args.kind == "tool" and (mcp_server or mcp_tool or mcp_outcome):
                from little_loops.history_reader import recent_tool_events

                rows = recent_tool_events(
                    mcp_server=mcp_server,
                    mcp_tool=mcp_tool,
                    mcp_outcome=mcp_outcome,
                    limit=args.limit,
                    db=args.db,
                )
            else:
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
            if getattr(args, "snapshots", False):
                count = backfill_snapshots(args.db)
                logger.success(f"Backfilled {count} issue snapshots.")
                return 0

            # Read project config so compaction settings are respected (same
            # pattern as the prune handler).
            import json as _json

            from little_loops.config.core import resolve_config_path

            _config: dict | None = None
            _config_path = resolve_config_path(Path.cwd())
            if _config_path is not None:
                try:
                    _config = _json.loads(_config_path.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    _config = None

            max_sessions = getattr(args, "max_sessions", None)
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
                also_rebuild = getattr(args, "rebuild", False)
                inc_counts = backfill_incremental(
                    args.db,
                    jsonl_files=jsonl_files,
                    since_ts=since_ts,
                    config=_config,
                    also_rebuild=also_rebuild,
                )
                inc_total = sum(inc_counts.values())
                logger.success(
                    f"Backfilled {inc_total} rows (incremental, since {since_flag}; "
                    f"raw_events={inc_counts['raw_events']}"
                    + (
                        f", messages={inc_counts.get('messages', 0)}, "
                        f"sessions={inc_counts.get('sessions', 0)}, "
                        f"corrections={inc_counts.get('corrections', 0)})"
                        if also_rebuild
                        else ")"
                    )
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
            counts = backfill(
                args.db,
                jsonl_files=full_jsonl_files,
                config=_config,
                max_sessions=max_sessions,
                repo_root=Path.cwd(),
                also_rebuild=getattr(args, "rebuild", False),
            )
            total = sum(counts.values())
            logger.success(
                f"Backfilled {total} rows "
                f"(issues={counts['issues']}, loops={counts['loops']}, "
                f"raw_events={counts.get('raw_events', 0)}, "
                f"snapshots={counts.get('snapshots', 0)}, commits={counts.get('commits', 0)}, "
                f"learning_tests={counts.get('learning_tests', 0)}"
                + (
                    f", tools={counts.get('tools', 0)}, messages={counts.get('messages', 0)}, "
                    f"sessions={counts.get('sessions', 0)}, corrections={counts.get('corrections', 0)}, "
                    f"summaries={counts.get('summaries', 0)})"
                    if getattr(args, "rebuild", False)
                    else ")"
                )
            )
            if getattr(args, "extract_decisions", False):
                _run_extract_decisions(since=None)
            return 0

        if args.command == "rebuild":
            import json as _json

            from little_loops.config.core import resolve_config_path

            config_path = getattr(args, "config", None) or resolve_config_path(Path.cwd())
            config = None
            if config_path is not None:
                try:
                    config = _json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    config = None

            counts = rebuild(args.db, config=config)
            if args.json:
                print_json(counts)
                return 0
            total = sum(counts.values())
            logger.success(
                f"Rebuilt {total} rows from raw_events "
                f"(tools={counts.get('tools', 0)}, messages={counts.get('messages', 0)}, "
                f"assistant_messages={counts.get('assistant_messages', 0)}, "
                f"skill_events={counts.get('skill_events', 0)}, sessions={counts.get('sessions', 0)}, "
                f"corrections={counts.get('corrections', 0)}, summaries={counts.get('summaries', 0)})"
            )
            return 0

        if args.command == "compact":
            import json as _json

            from little_loops.config.core import resolve_config_path

            config_path = getattr(args, "config", None) or resolve_config_path(Path.cwd())
            config = None
            if config_path is not None:
                try:
                    config = _json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    config = None

            compact_result = compact(args.db, config=config, and_prune=args.and_prune)
            if args.json:
                print_json(compact_result)
                return 0
            logger.success(
                f"Compacted {compact_result['compacted_rows']} raw event(s) into "
                f"{compact_result['summary_nodes']} retention summary node(s)"
                + (f"; pruned {compact_result['pruned_rows']} row(s)" if args.and_prune else "")
            )
            return 0

        if args.command == "skill-stats":
            from little_loops.history_reader import summarize_skills

            stats = summarize_skills(getattr(args, "since", None), db=args.db)
            if args.json:
                print_json(stats)
                return 0
            if not stats:
                print("No skill events.")
                return 0
            for s in stats:
                rate = f"{s['success_rate']:.0%}" if s["success_rate"] is not None else "n/a"
                avg = f"{s['avg_duration_ms']:.0f}ms" if s["avg_duration_ms"] is not None else "n/a"
                print(
                    f"{s['skill_name']}: invocations={s['invocations']} "
                    f"completions={s['completions']} success_rate={rate} avg_duration={avg}"
                )
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

            config = None
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

        if args.command == "recompress":
            result = recompress_raw_events(args.db, batch_size=args.batch)
            if args.json:
                print_json(result)
                return 0
            saved = result["size_before_mb"] - result["size_after_mb"]
            print(
                f"Recompressed {result['recompressed']:,} raw_events row(s).\n"
                f"DB: {result['size_before_mb']:.1f} MB -> "
                f"{result['size_after_mb']:.1f} MB (saved {saved:.1f} MB)"
            )
            return 0

        if args.command == "export":
            import json as _json

            out_path = getattr(args, "output", None)
            out = open(out_path, "w", encoding="utf-8") if out_path else sys.stdout
            count = 0
            try:
                for record in export_history(
                    args.db,
                    tables=getattr(args, "tables", None),
                    since=getattr(args, "since", None),
                    include_messages=getattr(args, "include_messages", False),
                ):
                    out.write(_json.dumps(record, default=str) + "\n")
                    count += 1
            finally:
                if out_path:
                    out.close()
            if out_path:
                logger.success(f"Exported {count:,} records to {out_path}")
            return 0

        return 1
