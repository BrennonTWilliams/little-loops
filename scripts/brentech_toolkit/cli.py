"""CLI entry points for brentech-toolkit.

Provides command-line interfaces for automated issue management:
- br-auto: Sequential issue processing
- br-parallel: Parallel issue processing with git worktrees
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from brentech_toolkit.config import BRConfig
from brentech_toolkit.issue_manager import AutoManager
from brentech_toolkit.logger import Logger


def main_auto() -> int:
    """Entry point for br-auto command.

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
""",
    )

    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="Resume from previous checkpoint",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--max-issues", "-m",
        type=int,
        default=0,
        help="Limit number of issues to process (0 = unlimited)",
    )
    parser.add_argument(
        "--category", "-c",
        type=str,
        default=None,
        help="Filter to specific category (bugs, features, enhancements)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to project root (default: current directory)",
    )

    args = parser.parse_args()

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)

    manager = AutoManager(
        config=config,
        dry_run=args.dry_run,
        max_issues=args.max_issues,
        resume=args.resume,
        category=args.category,
    )

    return manager.run()


def main_parallel() -> int:
    """Entry point for br-parallel command.

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
""",
    )

    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Number of parallel workers (default: from config or 2)",
    )
    parser.add_argument(
        "--include-p0",
        action="store_true",
        help="Include P0 issues in parallel processing",
    )
    parser.add_argument(
        "--priority", "-p",
        type=str,
        default=None,
        help="Comma-separated priorities to process (default: all)",
    )
    parser.add_argument(
        "--max-issues", "-m",
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
        "--dry-run", "-n",
        action="store_true",
        help="Preview without making changes",
    )
    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="Resume from previous state",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=None,
        help="Timeout per issue in seconds",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--cleanup", "-c",
        action="store_true",
        help="Clean up all worktrees and exit",
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

    # Handle cleanup mode
    if args.cleanup:
        worktree_base = args.worktree_base or config.get_worktree_base()
        if worktree_base.exists():
            import subprocess
            # List and remove worktrees
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                if line.startswith("worktree "):
                    path = line.split(" ", 1)[1]
                    if str(worktree_base) in path:
                        logger.info(f"Removing worktree: {path}")
                        subprocess.run(
                            ["git", "worktree", "remove", "--force", path],
                            capture_output=True,
                        )
            logger.success("Cleanup complete")
        else:
            logger.info("No worktrees to clean up")
        return 0

    # Build priority filter (for future parallel processing)
    # Currently unused as we fall back to sequential processing
    _ = [p.strip().upper() for p in args.priority.split(",")] if args.priority else config.issue_priorities

    # Parallel processing requires the orchestrator from blender_agents
    # For now, fall back to sequential processing with a warning
    logger.warning(
        "Parallel processing requires project-specific orchestrator. "
        "Falling back to sequential processing."
    )
    logger.info("For full parallel support, use the project's parallel_issue_manager.py")

    # Use sequential manager as fallback
    manager = AutoManager(
        config=config,
        dry_run=args.dry_run,
        max_issues=args.max_issues,
        resume=args.resume,
    )

    return manager.run()


if __name__ == "__main__":
    sys.exit(main_auto())
