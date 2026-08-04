"""ll-issues check-verify-verdict: reads the persisted claim-verification verdict (ENH-3031).

Companion to ``/ll:verify-issues <ID> --check``, which persists
``verify_verdict: VALID|NON_VALID`` to the target issue's frontmatter. A
slash command's internal exit-code contract never reaches the host CLI's
process exit code (`action_type: slash_command` runs through the host
session, not `fragment: shell_exit`), so refine-to-ready-issue gates on this
deterministic shell probe over the written artifact instead — mirrors
check_open_questions.py's shape exactly.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def add_check_verify_verdict_parser(
    subs: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    """Register the check-verify-verdict subparser on *subs* (ENH-3031)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "check-verify-verdict",
        help=(
            "Exit 0 if the issue's persisted verify_verdict is VALID (or absent — "
            "fail-open), 1 if NON_VALID (ENH-3031)"
        ),
    )
    p.set_defaults(command="check-verify-verdict")
    p.add_argument("issue_id", help="Issue ID (e.g., 3031, ENH-3031, P2-ENH-3031)")
    add_config_arg(p)
    return p


def cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 unless the issue's frontmatter records verify_verdict: NON_VALID (ENH-3031).

    Returns:
        0 when ``verify_verdict`` is ``VALID`` or absent (fail-open, matching
        this loop's non-fatal ``on_error`` convention for every other gate in
        this file). 1 with a ``VERIFY_VERDICT_NON_VALID`` stderr token when it
        is ``NON_VALID``.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    fm = parse_frontmatter(path.read_text(), coerce_types=True)
    verdict = fm.get("verify_verdict")

    if verdict is None or str(verdict).upper() == "VALID":
        print(f"Verified: {args.issue_id} verify_verdict={verdict!r}")
        return 0

    print(
        f"VERIFY_VERDICT_NON_VALID: {args.issue_id} — "
        f"verify_verdict={verdict!r}; run /ll:verify-issues {args.issue_id} --auto",
        file=sys.stderr,
    )
    return 1
