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
    from little_loops.issue_parser import IssueParser

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    # Only skip non-terminal issues (check frontmatter status, not directory)
    issue_info = IssueParser(config).parse_file(path)
    if issue_info.status in ("done", "cancelled", "deferred"):
        print(
            f"Error: Issue '{args.issue_id}' has status '{issue_info.status}', not an active issue.",
            file=sys.stderr,
        )
        return 1

    new_name = re.sub(r"^P\d-", f"{args.priority}-", path.name)
    new_path = path.parent / new_name

    if path == new_path:
        # Already at target priority — nothing to rename, but frontmatter still
        # needs reconciling (BUG-3286 Prefix-rewrite sync rule): this is exactly
        # the state of a drifted issue whose filename is already correct.
        from little_loops.file_utils import atomic_write
        from little_loops.frontmatter import update_frontmatter

        content = path.read_text(encoding="utf-8")
        updated_content = update_frontmatter(content, {"priority": args.priority})
        if updated_content != content:
            atomic_write(path, updated_content, encoding="utf-8")

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
