"""ll-issues next-id: Print the next globally unique issue number."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def positive_int(value: str) -> int:
    """Argparse type validator that requires a positive integer."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a valid integer") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"--count must be a positive integer, got {n}")
    return n


def cmd_next_id(config: BRConfig, count: int = 1) -> int:
    """Print the next globally unique issue number(s).

    Args:
        config: Project configuration
        count: Number of consecutive IDs to emit (default 1)

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_parser import get_next_issue_number

    base = get_next_issue_number(config)
    for i in range(count):
        print(f"{base + i:03d}")
    return 0
