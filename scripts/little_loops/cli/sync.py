"""ll-sync: GitHub Issues sync."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli_args import add_config_arg, add_dry_run_arg, add_quiet_arg
from little_loops.config import BRConfig
from little_loops.logger import Logger
from little_loops.sync import GitHubSyncManager, SyncResult, SyncStatus


def main_sync() -> int:
    """Entry point for ll-sync command.

    Sync local issues with GitHub Issues.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        prog="ll-sync",
        description="Sync local .issues/ files with GitHub Issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status             # Show sync status
  %(prog)s push               # Push all local issues to GitHub
  %(prog)s push BUG-123       # Push specific issue
  %(prog)s pull               # Pull GitHub Issues to local
""",
    )

    subparsers = parser.add_subparsers(dest="action", help="Sync action")

    # Status subcommand
    subparsers.add_parser("status", help="Show sync status")

    # Push subcommand
    push_parser = subparsers.add_parser("push", help="Push local issues to GitHub")
    push_parser.add_argument(
        "issue_ids",
        nargs="*",
        help="Specific issue IDs to push (e.g., BUG-123)",
    )

    # Pull subcommand
    pull_parser = subparsers.add_parser("pull", help="Pull GitHub Issues to local")
    pull_parser.add_argument(
        "--labels",
        "-l",
        type=str,
        help="Filter by labels (comma-separated)",
    )

    # Common args
    add_config_arg(parser)
    add_quiet_arg(parser)
    add_dry_run_arg(parser)

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return 1

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)
    logger = Logger(verbose=not getattr(args, "quiet", False))

    # Check sync is enabled
    if not config.sync.enabled:
        logger.error("Sync is not enabled. Add to .claude/ll-config.json:")
        logger.error('  "sync": { "enabled": true }')
        return 1

    dry_run = getattr(args, "dry_run", False)
    manager = GitHubSyncManager(config, logger, dry_run=dry_run)

    if args.action == "status":
        status = manager.get_status()
        _print_sync_status(status, logger)
        return 0

    elif args.action == "push":
        if dry_run:
            logger.info("[DRY RUN] Showing what would be pushed (no changes will be made)")
        issue_ids = args.issue_ids if args.issue_ids else None
        result = manager.push_issues(issue_ids)
        _print_sync_result(result, logger)
        return 0 if result.success else 1

    elif args.action == "pull":
        if dry_run:
            logger.info("[DRY RUN] Showing what would be pulled (no changes will be made)")
        labels = args.labels.split(",") if args.labels else None
        result = manager.pull_issues(labels)
        _print_sync_result(result, logger)
        return 0 if result.success else 1

    return 1


def _print_sync_status(status: SyncStatus, logger: Logger) -> None:
    """Print sync status in formatted output."""
    logger.info("=" * 80)
    logger.info("SYNC STATUS")
    logger.info("=" * 80)
    logger.info(f"Provider: {status.provider}")
    logger.info(f"Repository: {status.repo}")
    logger.info("")
    logger.info(f"Local Issues:     {status.local_total}")
    logger.info(f"Synced to GitHub: {status.local_synced}")
    logger.info(f"GitHub Issues:    {status.github_total}")
    logger.info("")
    logger.info(f"Unsynced local:   {status.local_unsynced}  (local only, not on GitHub)")
    logger.info(f"GitHub-only:      {status.github_only}  (on GitHub, not local)")
    logger.info("=" * 80)


def _print_sync_result(result: SyncResult, logger: Logger) -> None:
    """Print sync result in formatted output."""
    logger.info("=" * 80)
    logger.info(f"SYNC {result.action.upper()} {'COMPLETE' if result.success else 'FAILED'}")
    logger.info("=" * 80)
    logger.info("")
    logger.info("## SUMMARY")
    logger.info(f"- Created: {len(result.created)}")
    logger.info(f"- Updated: {len(result.updated)}")
    logger.info(f"- Skipped: {len(result.skipped)}")
    logger.info(f"- Failed:  {len(result.failed)}")
    logger.info("")
    if result.created:
        logger.info("## CREATED")
        for item in result.created:
            logger.info(f"  - {item}")
        logger.info("")
    if result.updated:
        logger.info("## UPDATED")
        for item in result.updated:
            logger.info(f"  - {item}")
        logger.info("")
    if result.failed:
        logger.info("## FAILED")
        for issue_id, reason in result.failed:
            logger.error(f"  - {issue_id}: {reason}")
        logger.info("")
    if result.errors:
        logger.info("## ERRORS")
        for error in result.errors:
            logger.error(f"  - {error}")
    logger.info("=" * 80)
