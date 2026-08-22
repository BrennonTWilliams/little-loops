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
    p.add_argument(
        "--proposal-unsound",
        action="store_true",
        help=(
            "Query mode (ENH-3250): exit 0 if verify_verdict == PROPOSAL_UNSOUND, "
            "1 otherwise. Used by refine-to-ready-issue.yaml's check_proposal_unsound "
            "gate to route that failure kind to reconcile_issue instead of "
            "refine_followup. Does not affect the default VALID/NON_VALID behavior."
        ),
    )
    p.add_argument(
        "--evidence-unverified",
        action="store_true",
        help=(
            "Query mode (BUG-3282): exit 0 if verify_verdict == EVIDENCE_UNVERIFIED, "
            "1 otherwise. Used by refine-to-ready-issue.yaml's "
            "check_evidence_unverified gate, placed ahead of check_proposal_unsound "
            "(evidence outranks proposal). Does not affect the default VALID/NON_VALID "
            "behavior."
        ),
    )
    add_config_arg(p)
    return p


def cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 unless the issue's frontmatter records verify_verdict: NON_VALID (ENH-3031).

    With ``--proposal-unsound`` (ENH-3250), behaves as a distinct query mode
    instead: exit 0 if ``verify_verdict == PROPOSAL_UNSOUND``, 1 otherwise
    (including when the field is absent) — a plain ``fragment: shell_exit``
    binary probe for ``refine-to-ready-issue.yaml``'s ``check_proposal_unsound``
    gate. ``PROPOSAL_UNSOUND`` still falls through the default mode below as
    non-VALID → exit 1, so the default contract is unchanged.

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
        return 2

    fm = parse_frontmatter(path.read_text(), coerce_types=True)
    verdict = fm.get("verify_verdict")

    if getattr(args, "evidence_unverified", False):
        if verdict is not None and str(verdict).upper() == "EVIDENCE_UNVERIFIED":
            print(f"Verified: {args.issue_id} verify_verdict={verdict!r}")
            return 0
        print(
            f"NOT_EVIDENCE_UNVERIFIED: {args.issue_id} — verify_verdict={verdict!r}",
            file=sys.stderr,
        )
        return 1

    if getattr(args, "proposal_unsound", False):
        if verdict is not None and str(verdict).upper() == "PROPOSAL_UNSOUND":
            print(f"Verified: {args.issue_id} verify_verdict={verdict!r}")
            return 0
        print(
            f"NOT_PROPOSAL_UNSOUND: {args.issue_id} — verify_verdict={verdict!r}",
            file=sys.stderr,
        )
        return 1

    if verdict is None or str(verdict).upper() == "VALID":
        print(f"Verified: {args.issue_id} verify_verdict={verdict!r}")
        return 0

    print(
        f"VERIFY_VERDICT_NON_VALID: {args.issue_id} — "
        f"verify_verdict={verdict!r}; run /ll:verify-issues {args.issue_id} --auto",
        file=sys.stderr,
    )
    return 1
