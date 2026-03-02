"""ll-history: Display summary statistics and analysis for completed issues."""

from __future__ import annotations

import argparse
from pathlib import Path


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
  %(prog)s generate-docs "session log"  # Synthesize docs from history
  %(prog)s generate-docs "sprint CLI" --output docs/arch/sprint.md
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # summary subcommand (existing)
    summary_parser = subparsers.add_parser("summary", help="Show issue statistics")
    summary_parser.add_argument(
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
    analyze_parser.add_argument(
        "-c",
        "--compare",
        type=int,
        default=None,
        metavar="DAYS",
        help="Compare last N days to previous N days",
    )

    # generate-docs subcommand (FEAT-503)
    gendocs_parser = subparsers.add_parser(
        "generate-docs",
        help="Synthesize documentation from completed issue history",
    )
    gendocs_parser.add_argument(
        "topic",
        type=str,
        help="Topic, area, or system to generate documentation for",
    )
    gendocs_parser.add_argument(
        "--output",
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
        type=str,
        default=None,
        metavar="DATE",
        help="Only include issues completed after DATE (YYYY-MM-DD)",
    )
    gendocs_parser.add_argument(
        "--min-relevance",
        type=float,
        default=0.3,
        metavar="FLOAT",
        help="Minimum relevance score threshold (default: 0.3)",
    )
    gendocs_parser.add_argument(
        "--type",
        type=str,
        choices=["BUG", "FEAT", "ENH"],
        default=None,
        dest="issue_type",
        help="Filter by issue type",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Determine directories
    issues_dir = args.directory or Path.cwd() / ".issues"
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
        issues = scan_completed_issues(completed_dir)
        analysis = calculate_analysis(
            issues,
            issues_dir=issues_dir,
            period_type=args.period,
            compare_days=args.compare,
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

    if args.command == "generate-docs":
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
        )

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(doc, encoding="utf-8")
            print(f"Documentation written to {args.output}")
        else:
            print(doc)

        return 0

    return 1
