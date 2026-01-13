"""CLI entry points for little-loops.

Provides command-line interfaces for automated issue management:
- ll-auto: Sequential issue processing
- ll-parallel: Parallel issue processing with git worktrees
- ll-messages: Extract user messages from Claude Code logs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.config import BRConfig
from little_loops.issue_manager import AutoManager
from little_loops.logger import Logger
from little_loops.logo import print_logo


def main_auto() -> int:
    """Entry point for ll-auto command.

    Sequential automated issue management with Claude CLI.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        description="Automated sequential issue management with Claude CLI",
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
""",
    )

    parser.add_argument(
        "--resume",
        "-r",
        action="store_true",
        help="Resume from previous checkpoint",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--max-issues",
        "-m",
        type=int,
        default=0,
        help="Limit number of issues to process (0 = unlimited)",
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter to specific category (bugs, features, enhancements)",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to process (e.g., BUG-001,FEAT-002)",
    )
    parser.add_argument(
        "--skip",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to skip (e.g., BUG-003,FEAT-004)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to project root (default: current directory)",
    )

    args = parser.parse_args()

    print_logo()

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)

    # Parse issue ID filters
    only_ids = {i.strip().upper() for i in args.only.split(",")} if args.only else None
    skip_ids = {i.strip().upper() for i in args.skip.split(",")} if args.skip else None

    manager = AutoManager(
        config=config,
        dry_run=args.dry_run,
        max_issues=args.max_issues,
        resume=args.resume,
        category=args.category,
        only_ids=only_ids,
        skip_ids=skip_ids,
    )

    return manager.run()


def main_parallel() -> int:
    """Entry point for ll-parallel command.

    Parallel issue management using git worktrees.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        description="Parallel issue management with git worktrees",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Process with default workers
  %(prog)s --workers 3        # Use 3 parallel workers
  %(prog)s --dry-run          # Preview what would be processed
  %(prog)s --priority P1,P2   # Only process P1 and P2 issues
  %(prog)s --cleanup          # Clean up worktrees and exit
  %(prog)s --stream-output    # Stream Claude CLI output in real-time
  %(prog)s --only BUG-001,BUG-002  # Process only specific issues
  %(prog)s --skip BUG-003     # Skip specific issues
""",
    )

    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=None,
        help="Number of parallel workers (default: from config or 2)",
    )
    parser.add_argument(
        "--priority",
        "-p",
        type=str,
        default=None,
        help="Comma-separated priorities to process (default: all)",
    )
    parser.add_argument(
        "--max-issues",
        "-m",
        type=int,
        default=0,
        help="Maximum issues to process (0 = unlimited)",
    )
    parser.add_argument(
        "--worktree-base",
        type=Path,
        default=None,
        help="Base directory for git worktrees",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview without making changes",
    )
    parser.add_argument(
        "--resume",
        "-r",
        action="store_true",
        help="Resume from previous state",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=None,
        help="Timeout per issue in seconds",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--cleanup",
        "-c",
        action="store_true",
        help="Clean up all worktrees and exit",
    )
    parser.add_argument(
        "--stream-output",
        action="store_true",
        help="Stream Claude CLI subprocess output to console",
    )
    parser.add_argument(
        "--show-model",
        action="store_true",
        help="Make API call to verify and display model on worktree setup",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to process (e.g., BUG-001,FEAT-002)",
    )
    parser.add_argument(
        "--skip",
        type=str,
        default=None,
        help="Comma-separated list of issue IDs to skip (e.g., BUG-003,FEAT-004)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to project root",
    )

    args = parser.parse_args()

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)

    logger = Logger(verbose=not args.quiet)

    if not args.quiet:
        print_logo()

    # Handle cleanup mode
    if args.cleanup:
        from little_loops.parallel import WorkerPool

        parallel_config = config.create_parallel_config()
        pool = WorkerPool(parallel_config, config, logger, project_root)
        pool.cleanup_all_worktrees()
        logger.success("Cleanup complete")
        return 0

    # Build priority filter
    priority_filter = (
        [p.strip().upper() for p in args.priority.split(",")] if args.priority else None
    )

    # Parse issue ID filters
    only_ids = {i.strip().upper() for i in args.only.split(",")} if args.only else None
    skip_ids = {i.strip().upper() for i in args.skip.split(",")} if args.skip else None

    # Create parallel config with CLI overrides
    parallel_config = config.create_parallel_config(
        max_workers=args.workers,
        priority_filter=priority_filter,
        max_issues=args.max_issues,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout,
        stream_output=args.stream_output if args.stream_output else None,
        show_model=args.show_model if args.show_model else None,
        only_ids=only_ids,
        skip_ids=skip_ids,
    )

    # Delete state file if not resuming
    if not args.resume:
        state_file = config.get_parallel_state_file()
        if state_file.exists():
            state_file.unlink()

    # Create and run orchestrator
    from little_loops.parallel import ParallelOrchestrator

    orchestrator = ParallelOrchestrator(
        parallel_config=parallel_config,
        br_config=config,
        repo_path=project_root,
        verbose=not args.quiet,
    )

    return orchestrator.run()


def main_messages() -> int:
    """Entry point for ll-messages command.

    Extract user messages from Claude Code session logs.

    Returns:
        Exit code (0 = success)
    """
    from datetime import datetime

    from little_loops.user_messages import (
        extract_user_messages,
        get_project_folder,
        print_messages_to_stdout,
        save_messages,
    )

    parser = argparse.ArgumentParser(
        description="Extract user messages from Claude Code logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Last 100 messages to file
  %(prog)s -n 50                # Last 50 messages
  %(prog)s --since 2026-01-01   # Messages since date
  %(prog)s -o output.jsonl      # Custom output path
  %(prog)s --stdout             # Print to terminal
""",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=100,
        help="Maximum number of messages to extract (default: 100)",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Only include messages after this date (YYYY-MM-DD or ISO format)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path (default: .claude/user-messages-{timestamp}.jsonl)",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        help="Working directory to use (default: current directory)",
    )
    parser.add_argument(
        "--exclude-agents",
        action="store_true",
        help="Exclude agent session files (agent-*.jsonl)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print messages to stdout instead of writing to file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose progress information",
    )

    args = parser.parse_args()

    logger = Logger(verbose=args.verbose)

    # Parse since date if provided
    since = None
    if args.since:
        try:
            # Try ISO format first
            since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        except ValueError:
            try:
                # Try YYYY-MM-DD format
                since = datetime.strptime(args.since, "%Y-%m-%d")
            except ValueError:
                logger.error(f"Invalid date format: {args.since}")
                logger.error("Use YYYY-MM-DD or ISO format")
                return 1

    # Get project folder
    cwd = args.cwd or Path.cwd()
    project_folder = get_project_folder(cwd)

    if project_folder is None:
        logger.error(f"No Claude project folder found for: {cwd}")
        logger.error(f"Expected: ~/.claude/projects/{str(cwd).replace('/', '-')}")
        return 1

    logger.info(f"Project folder: {project_folder}")
    logger.info(f"Limit: {args.limit}")
    if since:
        logger.info(f"Since: {since}")

    # Extract messages
    messages = extract_user_messages(
        project_folder=project_folder,
        limit=args.limit,
        since=since,
        include_agent_sessions=not args.exclude_agents,
    )

    if not messages:
        logger.warning("No user messages found")
        return 0

    logger.info(f"Found {len(messages)} messages")

    # Output messages
    if args.stdout:
        print_messages_to_stdout(messages)
    else:
        output_path = save_messages(messages, args.output)
        logger.success(f"Saved {len(messages)} messages to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main_auto())
