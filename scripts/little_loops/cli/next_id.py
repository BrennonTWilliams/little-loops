"""ll-next-id: Print the next globally unique issue number."""

from __future__ import annotations

import argparse
from pathlib import Path


def main_next_id() -> int:
    """Entry point for ll-next-id command.

    Prints the next globally unique issue number by scanning all issue
    directories (active and completed). Wraps get_next_issue_number().

    Returns:
        Exit code (0 = success)
    """
    from little_loops.config import BRConfig
    from little_loops.issue_parser import get_next_issue_number

    parser = argparse.ArgumentParser(
        prog="ll-next-id",
        description="Print the next globally unique issue number",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Print next issue number (e.g., 042)
  %(prog)s --config /path     # Use specific project root
""",
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

    next_num = get_next_issue_number(config)
    print(f"{next_num:03d}")

    return 0
