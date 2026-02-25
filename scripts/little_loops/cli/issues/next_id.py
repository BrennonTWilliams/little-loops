"""ll-issues next-id: Print the next globally unique issue number."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_next_id(config: BRConfig) -> int:
    """Print the next globally unique issue number.

    Args:
        config: Project configuration

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_parser import get_next_issue_number

    next_num = get_next_issue_number(config)
    print(f"{next_num:03d}")
    return 0
