"""ll-issues check-unresolved-decisions: decision-group-aware residual probe (BUG-3278).

Companion to ``ll-issues locate-options``/``check-decidable``, but counts
*decision groups* rather than option blocks: a group is resolved as a unit
(any member option's own span carries a ``> **Selected:**`` callout, or the
group's section holds exactly one group and carries a
``### Decision Rationale`` subsection), so a correctly-decided single-decision
issue reports 0 even though its losing options carry no marker of their own.
This is the gate ``/ll:decide-issue`` Phase 7b and Phase 3b step 4 run before
clearing ``decision_needed`` — see ``locate_unresolved_decisions``'s docstring
for why it is not interchangeable with ``locate_unresolved_options``/
``check-open-questions``.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def add_check_unresolved_decisions_parser(
    subs: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    """Register the check-unresolved-decisions subparser on *subs* (BUG-3278)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "check-unresolved-decisions",
        help=(
            "Exit 0 if no decision group remains unresolved, group-aware "
            "unlike check-open-questions (BUG-3278)"
        ),
    )
    p.set_defaults(command="check-unresolved-decisions")
    p.add_argument("issue_id", help="Issue ID (e.g., 3278, BUG-3278, P2-BUG-3278)")
    p.add_argument("--json", "-j", action="store_true", help="Output as JSON object")
    add_config_arg(p)
    return p


def cmd_check_unresolved_decisions(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 if the issue has no unresolved decision group, 1 otherwise (BUG-3278).

    Returns:
        0 when :func:`locate_unresolved_decisions` returns no groups. 1 with an
        ``UNRESOLVED_DECISIONS_REMAIN`` stderr token naming each surviving
        group's heading and line range otherwise. 2 when the issue ID does not
        resolve — distinct from 1 so the FSM ``exit_code`` evaluator's mapping
        (0->on_yes, 1->on_no, 2+->on_error) never confuses "unresolvable ID"
        with a genuine residual (matches the house convention already used by
        ``check-open-questions``/``check-decidable`` since BUG-3294).

    Passes ``include_approximate_tiers=True`` — the widened tier/directive
    coverage this CLI exists to expose, unlike the conservative default the
    loop-gate consumers of ``locate_unresolved_options`` depend on.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.cli.output import print_json
    from little_loops.issue_parser import locate_unresolved_decisions

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    content = path.read_text()
    unresolved = locate_unresolved_decisions(content, include_approximate_tiers=True)

    if getattr(args, "json", False):
        print_json({"id": args.issue_id, "unresolved": [g.to_dict() for g in unresolved]})
        return 1 if unresolved else 0

    if not unresolved:
        print(f"No unresolved decision group remains: {args.issue_id}")
        return 0

    print(
        f"UNRESOLVED_DECISIONS_REMAIN: {args.issue_id} — "
        f"{len(unresolved)} unresolved decision point(s):",
        file=sys.stderr,
    )
    for group in unresolved:
        heading = group.heading or "(whole document)"
        print(f"  - {heading} (lines {group.start_line}-{group.end_line})", file=sys.stderr)
    return 1
