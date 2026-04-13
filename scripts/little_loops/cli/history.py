"""ll-history: Display summary statistics and analysis for completed issues."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.cli_args import add_config_arg
from little_loops.config import BRConfig
from little_loops.logger import Logger


def main_history() -> int:
    """Entry point for ll-history command.

    Display summary statistics and analysis for completed issues.

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_history import (
        calculate_analysis,
        calculate_summary,
        format_analysis_json,
        format_analysis_markdown,
        format_analysis_text,
        format_analysis_yaml,
        format_summary_json,
        format_summary_text,
        scan_completed_issues,
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
        choices=["BUG", "FEAT", "ENH"],
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

    add_config_arg(parser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Determine directories
    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)
    configure_output(config.cli)
    logger = Logger(use_color=use_color_enabled())
    issues_dir = args.directory or config.project_root / config.issues.base_dir
    completed_dir = issues_dir / "completed"

    if args.command == "summary":
        # Existing summary logic
        issues = scan_completed_issues(completed_dir)
        summary = calculate_summary(issues)

        if args.json:
            print(format_summary_json(summary))
        else:
            print(format_summary_text(summary))

        return 0

    if args.command == "analyze":
        # New analyze logic (FEAT-110)
        from datetime import date as date_type

        issues = scan_completed_issues(completed_dir)

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

    if args.command == "export":
        from datetime import date as date_type

        from little_loops.issue_history.analysis import _load_issue_contents

        issues = scan_completed_issues(completed_dir)
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
