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
        0 when count_enumerable_options finds >=1 option, 1 when it finds 0, 2 when
        the issue cannot be resolved (BUG-3294 — "cannot evaluate" is distinct from
        a genuine negative).
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.issue_parser import locate_enumerable_options

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    located = locate_enumerable_options(path.read_text())
    if located.count >= 1:
        print(
            f"Decidable: {args.issue_id} has {located.count} enumerable option(s) "
            f"in '{located.heading}'"
        )
        if located.residual_directive is not None:
            rd = located.residual_directive
            line = rd.options[0].start_line if rd.options else "?"
            print(f"  + residual decision directive in '{rd.heading}' (line {line}) — not counted")
        return 0

    # BUG-3293: the two probes locate_enumerable_options() chains have different
    # scopes, so a count of 0 does not license one diagnosis. The tier sweep IS
    # document-wide (## Proposed Solution, the fallback sections, then every H2
    # section including nested H3s via _iter_h2_sections), and (BUG-3287) now
    # also probes the Pattern E directive alongside every tier win rather than
    # only as a terminal fallback — for that probe, "not that it looked in the
    # wrong place" holds. But the Pattern E directive probe
    # (_locate_directive_alternatives) is itself bounded to a fixed section list
    # (_DIRECTIVE_ALTERNATIVES_SECTIONS) and never runs elsewhere. A probe
    # observes an absence, not a cause: count == 0 is indistinguishable between
    # "none are written" and "some exist in a shape the locator does not
    # recognize" — so the message states both candidate causes instead of
    # asserting the document "genuinely has none".
    print(
        f"OPTIONS_MISSING: {args.issue_id} — decision_needed is true but no enumerable "
        "alternatives matched; either none are written, or they are in a shape the "
        "locator does not recognize (see BUG-3293). If none are written, run "
        f"/ll:refine-issue {args.issue_id} --auto",
        file=sys.stderr,
    )
    return 1
