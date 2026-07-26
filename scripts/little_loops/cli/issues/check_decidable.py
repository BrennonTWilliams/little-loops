"""ll-issues check-decidable: deterministic decidability probe for decision_needed issues.

ENH-2443: FSM companion to /ll:decide-issue --validate-only. `decide`'s slash_command
state can't be called from a shell state, so this re-implements the same enumerable-option
counting logic in pure Python for a real non-LLM evaluator (mirrors format-check /
ENH-2426).
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_check_decidable(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 if the issue has >=1 enumerable option to decide between, 1 otherwise.

    Returns:
        0 when count_enumerable_options finds >=1 option, 1 when it finds 0 or the
        issue is not found.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.issue_parser import locate_enumerable_options

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    count, heading = locate_enumerable_options(path.read_text())
    if count >= 1:
        print(f"Decidable: {args.issue_id} has {count} enumerable option(s) in '{heading}'")
        return 0

    # ENH-2821: locate_enumerable_options() already scans the whole document
    # (## Proposed Solution, the fallback sections, then every H2 section including
    # nested H3s), so a count of 0 here means the document genuinely has none —
    # not that the probe looked in the wrong place.
    print(
        f"OPTIONS_MISSING: {args.issue_id} — decision_needed is true but no enumerable "
        "alternatives were found anywhere in the document; "
        f"run /ll:refine-issue {args.issue_id} --auto",
        file=sys.stderr,
    )
    return 1
