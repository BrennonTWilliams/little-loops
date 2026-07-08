"""ll-issues check-open-questions: coverage-aware decidability probe (ENH-2446).

Companion to /ll:decide-issue --validate-only and the ENH-2443 count-based
``check-decidable`` probe. Counts BOTH (a) option blocks in ``## Proposed Solution``
that lack a ``> **Selected:**`` or ``### Decision Rationale`` marker AND
(b) free-form open questions in ``## Edge Cases`` / ``## Confidence Check Notes``
/ ``## Open Questions``. Exits 0 when neither surface has gaps; exits 1 with an
``OPEN_QUESTIONS_REMAIN`` token otherwise.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def add_check_open_questions_parser(
    subs: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    """Register the check-open-questions subparser on *subs* (ENH-2446)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "check-open-questions",
        help=(
            "Exit 0 if an issue has no unresolved options AND no open questions in "
            "Edge Cases / Confidence Check Notes / Open Questions (ENH-2446)"
        ),
    )
    p.set_defaults(command="check-open-questions")
    p.add_argument("issue_id", help="Issue ID (e.g., 2446, ENH-2446, P2-ENH-2446)")
    add_config_arg(p)
    return p


def cmd_check_open_questions(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 if the issue has no unresolved decision surface, 1 otherwise (ENH-2446).

    Returns:
        0 when ``count_unresolved_options`` AND ``count_open_questions_in_sections``
        both return 0. 1 with an ``OPEN_QUESTIONS_REMAIN`` stderr token otherwise.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.issue_parser import (
        count_open_questions_in_sections,
        count_unresolved_options,
    )

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    content = path.read_text()
    unresolved_options = count_unresolved_options(content)
    open_questions = count_open_questions_in_sections(content)

    if unresolved_options == 0 and open_questions == 0:
        print(f"Decidable (coverage-aware): {args.issue_id} has no unresolved decision surface")
        return 0

    print(
        f"OPEN_QUESTIONS_REMAIN: {args.issue_id} — "
        f"{open_questions} open question(s) and {unresolved_options} unresolved option(s); "
        f"run /ll:refine-issue {args.issue_id} --auto",
        file=sys.stderr,
    )
    return 1
