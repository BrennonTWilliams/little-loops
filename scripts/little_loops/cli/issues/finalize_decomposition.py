"""ll-issues finalize-decomposition: close a decomposed parent + re-link its EPIC.

Backs ENH-1977 Fix 4. Invoked by ``rn-decompose``'s ``finalize_parent`` state once
children have been enqueued. Children may be passed positionally or via
``--children-file`` (one ID per line — the loop's ``children_<id>.txt`` artifact).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_finalize_decomposition(config: BRConfig, args: argparse.Namespace) -> int:
    """Close a decomposed parent and re-link children to the parent's EPIC.

    Args:
        config: Project configuration (provides the project root).
        args: Parsed args with ``.parent``, ``.children``, ``.children_file``,
            ``.issues_dir``, ``.no_move``.

    Returns:
        Exit code (0 on success, 1 if the parent could not be found).
    """
    from little_loops.recursive_finalize import finalize_decomposed_parent

    child_ids: list[str] = list(args.children or [])
    if args.children_file:
        cf = Path(args.children_file)
        if cf.exists():
            child_ids.extend(line.strip() for line in cf.read_text().splitlines() if line.strip())

    project_root = args.config or Path.cwd()
    issues_dir = Path(args.issues_dir)
    if not issues_dir.is_absolute():
        issues_dir = Path(project_root) / issues_dir

    result = finalize_decomposed_parent(
        args.parent,
        child_ids,
        issues_dir,
        move_to_completed=not args.no_move,
    )

    if result["warnings"] and "parent file not found" in result["warnings"][0]:
        print(f"Error: {result['warnings'][0]}", file=sys.stderr)
        return 1

    epic = result["epic"] or "(none)"
    print(
        f"Finalized {result['parent']}: status=done, "
        f"moved={result['moved']}, epic={epic}, children={len(result['children'])}"
    )
    for warning in result["warnings"]:
        print(f"  warning: {warning}", file=sys.stderr)
    return 0


def add_finalize_decomposition_parser(subs: argparse._SubParsersAction) -> None:
    """Register the ``finalize-decomposition`` subparser."""
    from little_loops.cli_args import add_config_arg

    fd = subs.add_parser(
        "finalize-decomposition",
        aliases=["fd"],
        help="Close a decomposed parent and re-link its children to the parent's EPIC",
    )
    fd.set_defaults(command="finalize-decomposition")
    fd.add_argument("parent", help="Decomposed parent issue ID (e.g., ENH-123)")
    fd.add_argument("children", nargs="*", help="Child issue IDs (or use --children-file)")
    fd.add_argument(
        "--children-file",
        dest="children_file",
        default=None,
        metavar="PATH",
        help="File with one child ID per line (e.g., run_dir/children_<id>.txt)",
    )
    fd.add_argument(
        "--issues-dir",
        dest="issues_dir",
        default=".issues",
        metavar="DIR",
        help="Issues base directory (default: .issues)",
    )
    fd.add_argument(
        "--no-move",
        action="store_true",
        dest="no_move",
        help="Do not move the closed parent into completed/ (status-only close)",
    )
    add_config_arg(fd)
