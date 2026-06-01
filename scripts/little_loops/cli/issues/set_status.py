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

    When ``--cascade`` is set, also propagates the status to active children
    (those with status ``open``, ``in_progress``, or ``blocked``). Child
    resolution uses union of ``relates_to:`` (forward) + ``parent:`` (backward)
    lookups.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id, .status, .cascade, .cascade_to

    Returns:
        Exit code (0 = success, 1 = error); exit 1 if any child update fails.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter
    from little_loops.issue_progress import _OPEN_STATUSES, _TERMINAL_STATUSES

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    # Validate cascade before making any changes
    if getattr(args, "cascade", False):
        if args.status not in _TERMINAL_STATUSES:
            print(
                f"Error: --cascade is only valid when target status is done or "
                f"cancelled, got '{args.status}'.",
                file=sys.stderr,
            )
            return 1

    content = path.read_text()
    old_status = parse_frontmatter(content).get("status", "unknown")
    new_content = update_frontmatter(content, {"status": args.status})
    path.write_text(new_content)
    print(f"{args.issue_id}: {old_status} → {args.status}")

    # Cascade to children
    if getattr(args, "cascade", False):
        fm = parse_frontmatter(content)
        epic_id = fm.get("id", args.issue_id).upper()

        from little_loops.issue_parser import find_issues

        all_issues = find_issues(config)

        # Union of forward (relates_to:) + backward (parent:)
        forward_ids: set[str] = set(fm.get("relates_to", []))
        backward_ids: set[str] = {i.issue_id for i in all_issues if i.parent and i.parent.upper() == epic_id}
        child_ids = forward_ids | backward_ids

        children = [i for i in all_issues if i.issue_id.upper() in child_ids]
        active = [c for c in children if c.status in _OPEN_STATUSES]
        skipped = [c for c in children if c not in active]

        print(f"  Cascading to {len(active)} active children (default: {args.cascade_to}):")

        failures = 0
        for child in active:
            try:
                child_content = child.path.read_text()
                child_new = update_frontmatter(child_content, {"status": args.cascade_to})
                child.path.write_text(child_new)
                print(f"    {child.issue_id} → {args.cascade_to}")
            except OSError as exc:
                print(f"    {child.issue_id}: FAILED ({exc})", file=sys.stderr)
                failures += 1

        if skipped:
            print(f"  ({len(skipped)} children already terminal/other — unchanged)")

        if failures:
            return 1

    return 0
