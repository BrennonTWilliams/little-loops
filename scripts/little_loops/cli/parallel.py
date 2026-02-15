"""ll-parallel: Parallel issue management using git worktrees."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from little_loops.cli_args import (
    add_dry_run_arg,
    add_max_issues_arg,
    add_only_arg,
    add_quiet_arg,
    add_resume_arg,
    add_skip_arg,
    add_timeout_arg,
    add_type_arg,
    parse_issue_ids,
    parse_issue_types,
)
from little_loops.config import BRConfig
from little_loops.logger import Logger


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
  %(prog)s --type BUG          # Process only bugs
  %(prog)s --type BUG,ENH      # Process bugs and enhancements
""",
    )

    # Parallel-specific arguments (--workers, not --max-workers)
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
        "--worktree-base",
        type=Path,
        default=None,
        help="Base directory for git worktrees",
    )
    parser.add_argument(
        "--cleanup",
        "-c",
        action="store_true",
        help="Clean up all worktrees and exit",
    )
    parser.add_argument(
        "--merge-pending",
        action="store_true",
        help="Attempt to merge pending work from previous interrupted runs",
    )
    parser.add_argument(
        "--clean-start",
        action="store_true",
        help="Remove all worktrees and start fresh (skip pending work check)",
    )
    parser.add_argument(
        "--ignore-pending",
        action="store_true",
        help="Report pending work but continue without merging",
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
        "--overlap-detection",
        action="store_true",
        help="Enable pre-flight overlap detection to reduce merge conflicts (ENH-143)",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="With --overlap-detection, warn about overlaps instead of serializing",
    )

    # Add common arguments from shared module
    add_dry_run_arg(parser)
    add_resume_arg(parser)
    add_timeout_arg(parser)
    add_quiet_arg(parser)
    add_only_arg(parser)
    add_skip_arg(parser)
    add_type_arg(parser)

    # Add max-issues and config individually (different help text needed)
    add_max_issues_arg(parser)
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
    only_ids = parse_issue_ids(args.only)
    skip_ids = parse_issue_ids(args.skip)
    type_prefixes = parse_issue_types(args.type)

    # Detect current branch for rebase/merge operations (BUG-439)
    _branch_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    _base_branch = _branch_result.stdout.strip() if _branch_result.returncode == 0 else "main"

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
        type_prefixes=type_prefixes,
        merge_pending=args.merge_pending,
        clean_start=args.clean_start,
        ignore_pending=args.ignore_pending,
        overlap_detection=args.overlap_detection,
        serialize_overlapping=not args.warn_only,
        base_branch=_base_branch,
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
