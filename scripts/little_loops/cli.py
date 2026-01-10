"""CLI entry points for little-loops.

Provides command-line interfaces for automated issue management:
- ll-auto: Sequential issue processing
- ll-parallel: Parallel issue processing with git worktrees
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


if __name__ == "__main__":
    sys.exit(main_auto())
