"""ll-issues set-status: Transition an issue to a new status value."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_set_status(config: BRConfig, args: argparse.Namespace) -> int:
    """Write a new status value into an issue's YAML frontmatter.

    Validates the target status against the canonical enum before writing.
    Prints the before→after transition to stdout on success.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id and .status

    Returns:
        Exit code (0 = success, 1 = error)
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    content = path.read_text()
    old_status = parse_frontmatter(content).get("status", "unknown")
    new_content = update_frontmatter(content, {"status": args.status})
    path.write_text(new_content)
    print(f"{args.issue_id}: {old_status} → {args.status}")
    return 0
