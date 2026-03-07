"""ll-auto: Process all backlog issues sequentially in priority order."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.output import configure_output
from little_loops.cli_args import add_common_auto_args, parse_issue_ids, parse_issue_types
from little_loops.config import BRConfig
from little_loops.issue_manager import AutoManager


def main_auto() -> int:
    """Entry point for ll-auto command.

    Process all backlog issues sequentially in priority order.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        description="Process all backlog issues sequentially in priority order",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Process all issues in priority order
  %(prog)s --max-issues 5     # Process at most 5 issues
  %(prog)s --resume           # Resume from previous state
  %(prog)s --dry-run          # Preview what would be processed
  %(prog)s --category bugs    # Only process bugs
  %(prog)s --only BUG-001,BUG-002  # Process only specific issues
  %(prog)s --skip BUG-003     # Skip specific issues
  %(prog)s --type BUG          # Process only bugs
  %(prog)s --type BUG,ENH      # Process bugs and enhancements
""",
    )

    # Add common arguments from shared module
    add_common_auto_args(parser)

    # Add tool-specific arguments
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter to specific category (bugs, features, enhancements)",
    )

    args = parser.parse_args()

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)
    configure_output(config.cli)

    if args.idle_timeout is not None:
        config.automation.idle_timeout_seconds = args.idle_timeout

    # Parse issue ID filters
    only_ids = parse_issue_ids(args.only)
    skip_ids = parse_issue_ids(args.skip)
    type_prefixes = parse_issue_types(args.type)

    manager = AutoManager(
        config=config,
        dry_run=args.dry_run,
        max_issues=args.max_issues,
        resume=args.resume,
        category=args.category,
        only_ids=only_ids,
        skip_ids=skip_ids,
        type_prefixes=type_prefixes,
        verbose=not args.quiet,
    )

    return manager.run()
