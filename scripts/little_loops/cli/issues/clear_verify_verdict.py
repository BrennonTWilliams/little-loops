"""ll-issues clear-verify-verdict: removes the persisted verify_verdict (BUG-3571).

Run immediately before ``/ll:verify-issues --check`` so a verdict from an earlier
invocation cannot satisfy ``check-verify-verdict`` when the current call fails.
Mirrors ``set-scores --clear``.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def add_clear_verify_verdict_parser(
    subs: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    """Register the clear-verify-verdict subparser on *subs* (BUG-3571)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "clear-verify-verdict",
        help="Remove the issue's persisted verify_verdict from frontmatter (BUG-3571)",
    )
    p.set_defaults(command="clear-verify-verdict")
    p.add_argument("issue_id", help="Issue ID (e.g., 3571, BUG-3571, P2-BUG-3571)")
    add_config_arg(p)
    return p


def cmd_clear_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int:
    """Remove ``verify_verdict`` from an issue's frontmatter (absent key is a no-op).

    Returns:
        0 on success, 2 when the issue is not found.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import remove_frontmatter_keys

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    content = path.read_text()
    new_content = remove_frontmatter_keys(content, ("verify_verdict",))
    if new_content != content:
        path.write_text(new_content)
    return 0
