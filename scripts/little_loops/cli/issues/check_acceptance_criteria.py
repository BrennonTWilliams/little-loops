"""ll-issues check-acceptance-criteria: automatability probe (ENH-3031).

Scans ``## Acceptance Criteria`` checkbox items (``- [ ]`` / ``- [x]``) for
manual-verification verbs — a criterion that requires a human to do something
by hand is exactly the decay mode refine-to-ready-issue exists to prevent,
and the confidence-check rubric (complexity / test_coverage / ambiguity /
change_surface) has no axis that can see it: a manual step scores well on all
four. Exits 0 when every criterion is machine-checkable; exits 1 with a
``MANUAL_CRITERIA_REMAIN`` token otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig

# Manual-verification verbs/phrases. `looks` alone was measured to fire on
# unrelated prose (ENH-3031 Codebase Research Findings); only the full phrase
# is kept.
_MANUAL_VERB_RE = re.compile(
    r"\btemporarily\b"
    r"|\bmanually\b"
    r"|\bby hand\b"
    r"|\bverify by\b"
    r"|\bvisually confirm\b"
    r"|\bcheck that .* looks\b",
    re.IGNORECASE,
)

_CHECKBOX_ITEM_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s*(.+)$")


def add_check_acceptance_criteria_parser(
    subs: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    """Register the check-acceptance-criteria subparser on *subs* (ENH-3031)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "check-acceptance-criteria",
        help=(
            "Exit 0 if every '## Acceptance Criteria' checkbox item is "
            "machine-checkable, 1 if any require manual verification (ENH-3031)"
        ),
    )
    p.set_defaults(command="check-acceptance-criteria")
    p.add_argument("issue_id", help="Issue ID (e.g., 3031, ENH-3031, P2-ENH-3031)")
    add_config_arg(p)
    return p


def _find_manual_criteria(content: str) -> list[str]:
    """Return checkbox-item texts under Acceptance Criteria that read as manual."""
    from little_loops.issue_parser import _section_body

    body = _section_body(content, "Acceptance Criteria")
    if not body:
        return []

    manual: list[str] = []
    item_lines: list[str] = []

    def _flush() -> None:
        if not item_lines:
            return
        joined = " ".join(item_lines)
        if _MANUAL_VERB_RE.search(joined):
            manual.append(joined)

    for line in body.splitlines():
        m = _CHECKBOX_ITEM_RE.match(line)
        if m:
            _flush()
            item_lines = [m.group(1).strip()]
        elif item_lines and line.strip() and not line.strip().startswith("#"):
            item_lines.append(line.strip())
        else:
            _flush()
            item_lines = []
    _flush()
    return manual


def cmd_check_acceptance_criteria(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 if no acceptance criterion reads as manual, 1 otherwise (ENH-3031).

    Returns:
        0 when no checkbox item under ``## Acceptance Criteria`` matches a
        manual-verification verb. 1 with a ``MANUAL_CRITERIA_REMAIN`` stderr
        token otherwise.
    """
    from little_loops.cli.issues.show import _resolve_issue_id

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    content = path.read_text()
    manual = _find_manual_criteria(content)

    if not manual:
        print(f"Automatable: {args.issue_id} has no manual-verification acceptance criteria")
        return 0

    detail = "; ".join(manual)
    print(
        f"MANUAL_CRITERIA_REMAIN: {args.issue_id} — "
        f"{len(manual)} manual criterion/criteria ({detail}); "
        f"rewrite as a machine-checkable step or run /ll:refine-issue {args.issue_id} --auto",
        file=sys.stderr,
    )
    return 1
