"""ll-issues path: Print the file path for an issue ID."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

    from little_loops.config import BRConfig


def cmd_path(config: BRConfig, args: argparse.Namespace) -> int:
    """Print relative path to an issue file.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id (str) and optional .json (bool)

    Returns:
        0 if found, 1 if not found
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.cli.output import print_json

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    try:
        rel_path = str(path.relative_to(config.project_root))
    except ValueError:
        rel_path = str(path)

    if getattr(args, "json", False):
        print_json({"path": rel_path})
        return 0

    print(rel_path)
    return 0
