"""ll-issues rearm-spike: re-arm a refuted spike after its decision resolves (BUG-3593).

If the issue carries ``spike_refuted: true``, removes ``spike_attempted`` and
``spike_refuted`` so ``spike_needed`` re-applies and one new spike can run on the
chosen approach. Otherwise a no-op.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def add_rearm_spike_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the rearm-spike subparser on *subs* (BUG-3593)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "rearm-spike",
        help="Re-arm a refuted spike: drop spike_attempted/spike_refuted (BUG-3593)",
    )
    p.set_defaults(command="rearm-spike")
    p.add_argument("issue_id", help="Issue ID (e.g., 3593, BUG-3593, P2-BUG-3593)")
    add_config_arg(p)
    return p


def cmd_rearm_spike(config: BRConfig, args: argparse.Namespace) -> int:
    """Re-arm a refuted spike; prints ``[SPIKE_REARMED] <ID>`` when it acts.

    Returns:
        0 on a resolvable ID (acted or no-op), 2 when the issue is not found.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter, remove_frontmatter_keys

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    content = path.read_text()
    fm = parse_frontmatter(content)
    if str(fm.get("spike_refuted", "")).lower() != "true":
        return 0
    path.write_text(remove_frontmatter_keys(content, ("spike_attempted", "spike_refuted")))
    print(f"[SPIKE_REARMED] {args.issue_id}")
    return 0
