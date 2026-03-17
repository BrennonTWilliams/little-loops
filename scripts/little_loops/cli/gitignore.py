"""ll-gitignore: Suggest and apply .gitignore patterns."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli_args import add_config_arg, add_dry_run_arg, add_quiet_arg
from little_loops.git_operations import (
    GitignorePattern,
    add_patterns_to_gitignore,
    suggest_gitignore_patterns,
)
from little_loops.logger import Logger


def main_gitignore() -> int:
    """Entry point for ll-gitignore command.

    Scan for untracked files, suggest .gitignore patterns, and optionally apply them.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    parser = argparse.ArgumentParser(
        prog="ll-gitignore",
        description="Suggest and apply .gitignore patterns based on untracked files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Show suggestions and apply approved patterns
  %(prog)s --dry-run          # Preview suggestions without modifying .gitignore
  %(prog)s --quiet            # Suppress non-essential output
""",
    )

    add_dry_run_arg(parser)
    add_quiet_arg(parser)
    add_config_arg(parser)

    args = parser.parse_args()

    repo_root = args.config or Path.cwd()
    logger = Logger(verbose=not args.quiet)
    dry_run: bool = args.dry_run

    if dry_run:
        logger.info("[DRY RUN] Showing suggestions without modifying .gitignore")

    suggestion = suggest_gitignore_patterns(repo_root=repo_root, logger=logger)

    if not suggestion.has_suggestions:
        logger.info("No .gitignore suggestions — your repo looks clean.")
        return 0

    logger.info(suggestion.summary)

    # Display categorized suggestions
    categories: dict[str, list[GitignorePattern]] = {}
    for pattern in suggestion.patterns:
        categories.setdefault(pattern.category, []).append(pattern)

    for category, patterns in sorted(categories.items()):
        logger.info(f"\n  [{category}]")
        for p in patterns:
            file_count = len(p.files_matched)
            files_label = f"{file_count} file{'s' if file_count != 1 else ''}"
            logger.info(f"    {p.pattern:<30} {p.description} ({files_label})")

    if dry_run:
        return 0

    pattern_strings = [p.pattern for p in suggestion.patterns]
    success = add_patterns_to_gitignore(pattern_strings, repo_root=repo_root, logger=logger)

    return 0 if success else 1
