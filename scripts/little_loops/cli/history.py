"""ll-history: Display summary statistics and analysis for completed issues."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_config_arg, add_intent_arg, add_intent_limit_arg, add_json_arg
from little_loops.config import BRConfig
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context, resolve_history_db


def main_history() -> int:
    """Entry point for ll-history command.

    Display summary statistics and analysis for completed issues.

    Returns:
        Exit code (0 = success)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-history", sys.argv[1:]):
        from little_loops.issue_history import (
            HistoryDbUnavailable,
            analyze_agent_quality,
            analyze_rework,
            calculate_analysis,
            calculate_summary,
            count_loop_runs_in_window,
            format_agent_quality_json,
            format_agent_quality_markdown,
            format_agent_quality_text,
            format_agent_quality_yaml,
            format_analysis_json,
            format_analysis_markdown,
            format_analysis_text,
            format_analysis_yaml,
            format_rework_json,
            format_rework_markdown,
            format_rework_text,
            format_rework_yaml,
            format_summary_json,
            format_summary_text,
            issue_events_ever_recorded,
            scan_completed_issues,
            scan_completed_issues_from_db,
            synthesize_docs,
        )

        parser = argparse.ArgumentParser(
            prog="ll-history",
            description="Display summary statistics and analysis for completed issues",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s summary              # Show summary statistics
  %(prog)s summary --json       # Output as JSON
  %(prog)s analyze              # Full analysis report
  %(prog)s analyze --format markdown  # Markdown report
  %(prog)s analyze --compare 30 # Compare last 30 days to previous
  %(prog)s export "session log"  # Export topic-filtered issue excerpts
  %(prog)s export "sprint CLI" --output docs/arch/sprint.md
  %(prog)s rework               # Reopen/follow-up/touch-back/revert rates
  %(prog)s rework --format json # Rework analysis as JSON
  %(prog)s quality              # Fix-rate/correction/cost/tokens/retry trends
  %(prog)s quality --format json # Agent quality analysis as JSON
  %(prog)s audit-issue-collisions  # (issue_num, transition) dedup collisions
""",
        )

        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # summary subcommand (existing)
        summary_parser = subparsers.add_parser("summary", help="Show issue statistics")
        summary_parser.add_argument(
            "-j",
            "--json",
            action="store_true",
            help="Output as JSON instead of formatted text",
        )
        summary_parser.add_argument(
            "-d",
            "--directory",
            type=Path,
            default=None,
            help="Path to issues directory (default: .issues)",
        )
        summary_parser.add_argument(
            "-S",
            "--since",
            type=str,
            default=None,
            metavar="DATE",
            help="Only count issues/loop-runs on or after DATE (YYYY-MM-DD)",
        )
        summary_parser.add_argument(
            "--until",
            type=str,
            default=None,
            metavar="DATE",
            help="Only count issues/loop-runs on or before DATE (YYYY-MM-DD)",
        )

        # analyze subcommand (new - FEAT-110)
        analyze_parser = subparsers.add_parser(
            "analyze",
            help="Full analysis with trends, subsystems, and debt metrics",
        )
        analyze_parser.add_argument(
            "-f",
            "--format",
            type=str,
            choices=["text", "json", "markdown", "yaml"],
            default="text",
            help="Output format (default: text)",
        )
        analyze_parser.add_argument(
            "-d",
            "--directory",
            type=Path,
            default=None,
            help="Path to issues directory (default: .issues)",
        )
        analyze_parser.add_argument(
            "-p",
            "--period",
            type=str,
            choices=["weekly", "monthly", "quarterly"],
            default="monthly",
            help="Grouping period for trends (default: monthly)",
        )
        date_filter_group = analyze_parser.add_mutually_exclusive_group()
        date_filter_group.add_argument(
            "-c",
            "--compare",
            type=int,
            default=None,
            metavar="DAYS",
            help="Compare last N days to previous N days",
        )
        date_filter_group.add_argument(
            "--since",
            "-S",
            type=str,
            default=None,
            metavar="DATE",
            help="Only analyze issues completed on or after DATE (YYYY-MM-DD)",
        )
        analyze_parser.add_argument(
            "--until",
            type=str,
            default=None,
            metavar="DATE",
            help="Only analyze issues completed on or before DATE (YYYY-MM-DD)",
        )

        # export subcommand (FEAT-503, renamed from generate-docs in ENH-523)
        gendocs_parser = subparsers.add_parser(
            "export",
            help="Export topic-filtered excerpts from completed issue history",
        )
        gendocs_parser.add_argument(
            "topic",
            type=str,
            help="Topic, area, or system to generate documentation for",
        )
        gendocs_parser.add_argument(
            "--output",
            "-o",
            type=Path,
            default=None,
            help="Write output to file instead of stdout",
        )
        gendocs_parser.add_argument(
            "-f",
            "--format",
            type=str,
            choices=["narrative", "structured"],
            default="narrative",
            help="Output format (default: narrative)",
        )
        gendocs_parser.add_argument(
            "-d",
            "--directory",
            type=Path,
            default=None,
            help="Path to issues directory (default: .issues)",
        )
        gendocs_parser.add_argument(
            "--since",
            "-S",
            type=str,
            default=None,
            metavar="DATE",
            help="Only include issues completed after DATE (YYYY-MM-DD)",
        )
        gendocs_parser.add_argument(
            "--min-relevance",
            type=float,
            default=0.5,
            metavar="FLOAT",
            help="Minimum relevance score threshold (default: 0.5)",
        )
        gendocs_parser.add_argument(
            "--type",
            type=str,
            choices=["BUG", "FEAT", "ENH", "EPIC"],
            default=None,
            dest="issue_type",
            help="Filter by issue type",
        )
        gendocs_parser.add_argument(
            "--scoring",
            type=str,
            choices=["intersection", "bm25", "hybrid"],
            default="intersection",
            help="Relevance scoring method: intersection (default), bm25, or hybrid",
        )

        # rework subcommand (FEAT-2867)
        rework_parser = subparsers.add_parser(
            "rework",
            help="Reopen/follow-up/touch-back/revert rates and quality-adjusted throughput",
        )
        rework_parser.add_argument(
            "-f",
            "--format",
            type=str,
            choices=["text", "json", "markdown", "yaml"],
            default="text",
            help="Output format (default: text)",
        )
        rework_parser.add_argument(
            "--min-sample",
            type=int,
            default=None,
            metavar="N",
            help="Minimum closed issues per window before a rate is reported (default: 5)",
        )
        rework_parser.add_argument(
            "--follow-up-days",
            type=int,
            default=None,
            metavar="N",
            help="Lookahead window in days for follow-up/touch-back detection (default: 14)",
        )

        # quality subcommand (FEAT-3183)
        quality_parser = subparsers.add_parser(
            "quality",
            help="Fix-rate, correction rate, cost/tokens per issue, and retry inflation trends",
        )
        quality_parser.add_argument(
            "-f",
            "--format",
            type=str,
            choices=["text", "json", "markdown", "yaml"],
            default="text",
            help="Output format (default: text)",
        )
        quality_parser.add_argument(
            "--min-sample",
            type=int,
            default=None,
            metavar="N",
            help="Minimum closed issues (or loop runs) per window before a rate is "
            "reported (default: 5)",
        )

        # sessions subcommand (ENH-1711)
        sessions_parser = subparsers.add_parser(
            "sessions",
            help="List sessions that touched an issue",
        )
        sessions_parser.add_argument(
            "issue_id",
            metavar="ISSUE_ID",
            help="Issue ID (e.g., ENH-1710)",
        )
        sessions_parser.add_argument(
            "--limit", type=int, default=20, metavar="N", help="Maximum results (default: 20)"
        )
        add_json_arg(sessions_parser)

        # audit-issue-collisions subcommand (BUG-3006)
        collisions_parser = subparsers.add_parser(
            "audit-issue-collisions",
            help="Report (issue_num, transition) dedup collisions in issue_events/issue_snapshots",
        )
        add_json_arg(collisions_parser)

        # root subcommand (ENH-1955)
        root_parser = subparsers.add_parser(
            "root",
            help="Show the project-root summary node (top-level condensed view)",
        )
        root_parser.add_argument(
            "--expand",
            action="store_true",
            help="Expand and display all messages under the root node",
        )
        root_parser.add_argument(
            "--limit",
            type=int,
            default=20,
            metavar="N",
            help="Maximum messages to show with --expand (default: 20)",
        )
        add_json_arg(root_parser)

        add_config_arg(parser)
        add_intent_arg(parser)
        add_intent_limit_arg(parser)

        args = parser.parse_args()

        if not args.command:
            parser.print_help()
            return 1

        # Determine directories
        project_root = args.config or Path.cwd()
        config = BRConfig(project_root)
        configure_output(config.cli)
        logger = Logger(use_color=use_color_enabled())
        issues_dir = (
            getattr(args, "directory", None) or config.project_root / config.issues.base_dir
        )

        if args.command == "summary":
            from datetime import date as date_type

            since_date = date_type.fromisoformat(args.since) if args.since else None
            until_date = date_type.fromisoformat(args.until) if args.until else None

            # Prefer the unified session DB when it's available and queryable;
            # fall back to the file-parsing path only when it isn't — never on
            # zero matching rows, or a legitimately empty window would trip an
            # unfiltered, mislabeled file scan (ENH-3237 "the fallback trap").
            #
            # "Available" means issue_events has ever recorded a transition,
            # not just that the DB file exists: `cli_event_context` above
            # writes a `cli_events` row (and so creates the DB file) on
            # *every* `ll-history` invocation, so `db_path.exists()` alone is
            # true from the very first call ever made — including a project
            # that has never backfilled or live-written any issue lifecycle
            # data. Gating on file existence would then silently report "0
            # completed issues" for a project with real `done` issue files.
            db_path = resolve_history_db(project_root / DEFAULT_DB_PATH)
            issues = None
            source = "files"
            try:
                db_available = issue_events_ever_recorded(db_path)
            except HistoryDbUnavailable:
                db_available = False
            if db_available:
                try:
                    issues = scan_completed_issues_from_db(
                        db_path, since=since_date, until=until_date
                    )
                    source = "issue_events"
                except HistoryDbUnavailable:
                    issues = None
            if issues is None:
                issues = scan_completed_issues(issues_dir)
                if since_date or until_date:
                    issues = [
                        i
                        for i in issues
                        if i.completed_date is not None
                        and (since_date is None or i.completed_date >= since_date)
                        and (until_date is None or i.completed_date <= until_date)
                    ]
                source = "files"

            loop_runs_started, loop_runs_ended = count_loop_runs_in_window(
                db_path, since_date, until_date
            )
            summary = calculate_summary(
                issues,
                source=source,
                since=since_date,
                until=until_date,
                loop_runs_started=loop_runs_started,
                loop_runs_ended=loop_runs_ended,
            )

            if args.json:
                print(format_summary_json(summary))
            else:
                print(format_summary_text(summary))

            return 0

        if args.command == "analyze":
            # New analyze logic (FEAT-110)
            from datetime import date as date_type

            db_path = resolve_history_db(project_root / DEFAULT_DB_PATH)
            issues = scan_completed_issues(issues_dir)

            since_date = date_type.fromisoformat(args.since) if args.since else None
            until_date = date_type.fromisoformat(args.until) if args.until else None
            if since_date or until_date:
                issues = [
                    i
                    for i in issues
                    if i.completed_date is not None
                    and (since_date is None or i.completed_date >= since_date)
                    and (until_date is None or i.completed_date <= until_date)
                ]

            analysis = calculate_analysis(
                issues,
                issues_dir=issues_dir,
                period_type=args.period,
                compare_days=args.compare,
                project_root=project_root,
                db_path=db_path,
            )

            if args.format == "json":
                print(format_analysis_json(analysis))
            elif args.format == "yaml":
                print(format_analysis_yaml(analysis))
            elif args.format == "markdown":
                print(format_analysis_markdown(analysis))
            else:
                print(format_analysis_text(analysis))

            return 0

        if args.command == "rework":
            from little_loops.issue_history.rework import (
                FOLLOW_UP_WINDOW_DAYS,
                MIN_SAMPLE_SIZE,
            )
            from little_loops.issue_parser import find_issues

            db_path = resolve_history_db(project_root / DEFAULT_DB_PATH)
            all_statuses = {
                "open",
                "in_progress",
                "blocked",
                "deferred",
                "done",
                "cancelled",
            }
            all_issues = find_issues(config, status_filter=all_statuses)
            rework_analysis = analyze_rework(
                all_issues,
                db=db_path,
                min_sample=args.min_sample or MIN_SAMPLE_SIZE,
                follow_up_days=args.follow_up_days or FOLLOW_UP_WINDOW_DAYS,
            )

            if args.format == "json":
                print(format_rework_json(rework_analysis))
            elif args.format == "yaml":
                print(format_rework_yaml(rework_analysis))
            elif args.format == "markdown":
                print(format_rework_markdown(rework_analysis))
            else:
                print(format_rework_text(rework_analysis))

            return 0

        if args.command == "quality":
            from little_loops.issue_history.rework import MIN_SAMPLE_SIZE
            from little_loops.issue_parser import find_issues

            db_path = resolve_history_db(project_root / DEFAULT_DB_PATH)
            all_statuses = {
                "open",
                "in_progress",
                "blocked",
                "deferred",
                "done",
                "cancelled",
            }
            all_issues = find_issues(config, status_filter=all_statuses)
            # Deliberately `is None` rather than `args.min_sample or MIN_SAMPLE_SIZE`:
            # the latter would silently discard an explicit `--min-sample 0`.
            min_sample = args.min_sample if args.min_sample is not None else MIN_SAMPLE_SIZE
            quality_analysis = analyze_agent_quality(all_issues, db=db_path, min_sample=min_sample)

            if args.format == "json":
                print(format_agent_quality_json(quality_analysis))
            elif args.format == "yaml":
                print(format_agent_quality_yaml(quality_analysis))
            elif args.format == "markdown":
                print(format_agent_quality_markdown(quality_analysis))
            else:
                print(format_agent_quality_text(quality_analysis))

            return 0

        if args.command == "audit-issue-collisions":
            from little_loops.issue_history.collisions import (
                audit_issue_collisions,
                format_collision_audit_text,
            )

            db_path = resolve_history_db(project_root / DEFAULT_DB_PATH)
            groups = audit_issue_collisions(db_path, issues_dir)

            if args.json:
                from dataclasses import asdict

                print_json(
                    [
                        {
                            "table": g.table,
                            "issue_num": g.issue_num,
                            "classification": g.classification,
                            "entries": [asdict(e) for e in g.entries],
                        }
                        for g in groups
                    ]
                )
            else:
                print(format_collision_audit_text(groups))

            return 0

        if args.command == "sessions":
            from little_loops.history_reader import sessions_for_issue

            db_path = resolve_history_db(project_root / DEFAULT_DB_PATH)
            refs = sessions_for_issue(args.issue_id, limit=args.limit, db=db_path)
            if args.json:
                from dataclasses import asdict

                print_json([asdict(r) for r in refs])
            elif not refs:
                print(f"No sessions found for {args.issue_id}.")
            else:
                for r in refs:
                    path = r.jsonl_path or "(no path)"
                    print(f"{r.session_id}  {path}")
            return 0

        if args.command == "root":
            from little_loops.history_reader import ll_describe, ll_expand

            db_path = resolve_history_db(project_root / DEFAULT_DB_PATH)
            conn = None
            try:
                import sqlite3

                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                root_row = conn.execute(
                    "SELECT id FROM summary_nodes"
                    " WHERE session_id IS NULL AND parent_id IS NULL"
                    " ORDER BY level DESC LIMIT 1"
                ).fetchone()
            except sqlite3.Error:
                root_row = None
            finally:
                if conn:
                    conn.close()

            if root_row is None:
                print("No project-root summary node found.")
                print("Run 'll-session backfill' with compaction enabled to generate one.")
                return 1

            root_id = root_row["id"]
            node = ll_describe(root_id, db=db_path)
            if node is None:
                print(f"Root summary node {root_id} metadata not found.")
                return 1

            if args.json:
                messages = ll_expand(root_id, db=db_path) if args.expand else []
                from dataclasses import asdict

                print_json(
                    {
                        "node": asdict(node),
                        "message_count": len(messages),
                        "messages": [dict(m) for m in messages[: args.limit]]
                        if args.expand
                        else [],
                    }
                )
            else:
                print(f"id={node.id}  kind={node.kind}  level={node.level}")
                print(f"ts_start={node.ts_start}  ts_end={node.ts_end}")
                print(f"tokens={node.tokens}  created_at={node.created_at}")
                if node.content:
                    print(f"content: {node.content[:300]}")

                if args.expand:
                    messages = ll_expand(root_id, db=db_path)
                    print(f"\n--- {len(messages)} messages covered ---")
                    for m in messages[: args.limit]:
                        snippet = (m.get("content") or "")[:120].replace("\n", " ")
                        print(f"{m.get('ts', '')}  {snippet}")
            return 0

        if args.command == "export":
            from datetime import date as date_type

            from little_loops.issue_history.analysis import _load_issue_contents

            issues = scan_completed_issues(issues_dir)
            contents = _load_issue_contents(issues)

            since_date = None
            if args.since:
                since_date = date_type.fromisoformat(args.since)

            doc = synthesize_docs(
                topic=args.topic,
                issues=issues,
                contents=contents,
                format=args.format,
                min_relevance=args.min_relevance,
                since=since_date,
                issue_type=args.issue_type,
                scoring=args.scoring,
            )

            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(doc, encoding="utf-8")
                logger.success(f"Documentation written to {args.output}")
            else:
                print(doc)

            return 0

        return 1
