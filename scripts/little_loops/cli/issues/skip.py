"""ll-issues skip: Deprioritize an issue by bumping its priority prefix."""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

    from little_loops.config import BRConfig


def cmd_skip(config: BRConfig, args: argparse.Namespace) -> int:
    """Deprioritize an issue by renaming its priority prefix.

    Renames the issue file to the given priority (default P5), appends a
    ``## Skip Log`` entry with timestamp and optional reason, and prints the
    new file path to stdout so callers can confirm the rename.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id, .priority, and .reason

    Returns:
        Exit code (0 = success, 1 = error)
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.issue_lifecycle import skip_issue

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    # Only skip active issues
    parent_name = path.parent.name
    if parent_name in ("completed", "deferred"):
        print(
            f"Error: Issue '{args.issue_id}' is in {parent_name}/, not an active issue.",
            file=sys.stderr,
        )
        return 1

    new_name = re.sub(r"^P\d-", f"{args.priority}-", path.name)
    new_path = path.parent / new_name

    if path == new_path:
        # Already at target priority — nothing to rename, still print path
        try:
            rel = str(new_path.relative_to(config.project_root))
        except ValueError:
            rel = str(new_path)
        print(f"Deprioritized {args.issue_id} to {args.priority}: {rel}")
        return 0

    try:
        skip_issue(path, new_path, args.reason)
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        rel = str(new_path.relative_to(config.project_root))
    except ValueError:
        rel = str(new_path)

    print(f"Deprioritized {args.issue_id} to {args.priority}: {rel}")
    return 0
