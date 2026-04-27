"""ll-issues anchor-sweep: rewrite file:line refs in active issue files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_anchor_sweep(config: BRConfig, args: argparse.Namespace) -> int:
    """Rewrite file:line references in active issue files to anchor form.

    Scans bugs/, features/, and enhancements/ under the issues directory for
    references like ``file.py:42`` outside code fences, resolves each to its
    enclosing function/class/section, and rewrites in-place.

    Args:
        config: Project configuration.
        args: Parsed arguments with .dry_run and .issues_dir.

    Returns:
        0 on success, 1 on error.
    """
    from little_loops.issues.anchor_sweep import sweep_issues

    issues_dir = Path(args.issues_dir)
    if not issues_dir.is_absolute():
        issues_dir = config.project_root / issues_dir

    if not issues_dir.is_dir():
        print(f"Error: issues directory not found: {issues_dir}", file=sys.stderr)
        return 1

    dry_run: bool = args.dry_run
    result = sweep_issues(issues_dir, dry_run=dry_run)

    mode = "[dry-run] " if dry_run else ""
    if result.changes:
        for change in result.changes:
            print(f"{mode}{change}")
        if dry_run:
            print(f"\n{mode}Would modify {len(result.changes)} file(s). Re-run without --dry-run to apply.")
        else:
            print(f"\nModified {len(result.modified_files)} file(s).")
    else:
        print(f"{mode}No file:line references found in active issue files.")

    if result.skipped_refs:
        print(
            f"Warning: {result.skipped_refs} reference(s) could not be resolved and were left unchanged.",
            file=sys.stderr,
        )

    return 0
