"""ll-issues arm-proposal-revision: re-open a refuted proposal's decision (BUG-3574).

Reuses BUG-3592's refuted-option -> ``decision_needed`` contract for a
``PROPOSAL_UNSOUND`` verdict: writes a refuted-option marker for the selected
option into ``## Open Questions`` and sets ``decision_needed: true`` so
``/ll:decide-issue`` re-decides among the remaining eligible options. Decided
before decide-issue runs because decide-issue cannot be trusted with the
no-alternative case (it would deposit options or re-select the refuted design).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig

_NO_EVIDENCE = "B6 finding (no evidence persisted)"


def add_arm_proposal_revision_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the arm-proposal-revision subparser on *subs* (BUG-3574)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "arm-proposal-revision",
        help=(
            "Mark the selected option refuted and set decision_needed so decide-issue "
            "re-decides; exit 1 when no eligible alternative remains (BUG-3574)"
        ),
    )
    p.set_defaults(command="arm-proposal-revision")
    p.add_argument("issue_id", help="Issue ID (e.g., 3574, BUG-3574, P3-BUG-3574)")
    add_config_arg(p)
    return p


def _selected_eligible_label(content: str) -> tuple[str | None, bool]:
    """Return ``(label, others_remain)`` for the selected eligible option.

    ``label`` is the exact ``LocatedOption.label`` of the first ``Selected:``
    callout that names an eligible option (``None`` when there is none).
    ``others_remain`` is True when another eligible option would remain.
    """
    from little_loops.issue_parser import (
        _SELECTED_CALLOUT_RE,
        _normalize_option_label,
        _option_label,
        _section_body,
        locate_enumerable_options,
    )

    located = locate_enumerable_options(content)
    eligible = [o for o in located.options if o.eligible]
    if not eligible:
        return None, False
    body = _section_body(content, "Proposed Solution") or ""
    for match in _SELECTED_CALLOUT_RE.finditer(body):
        short = _option_label(match.group(1))
        if short is None:
            continue
        for option in eligible:
            if _normalize_option_label(option.label) == short:
                return option.label, len(eligible) > 1
    return None, False


def _append_marker(content: str, item: str) -> str:
    from little_loops.issue_parser import _section_body_with_offset

    found = _section_body_with_offset(content, "Open Questions")
    if found is None:
        block = f"\n## Open Questions\n\n1. {item}\n"
        status = re.search(r"^## Status\b", content, re.MULTILINE)
        if status:
            return content[: status.start()] + block.lstrip("\n") + "\n" + content[status.start() :]
        return content.rstrip("\n") + "\n" + block
    body, offset = found
    number = len(re.findall(r"^\s*\d+[.)]\s", body, re.MULTILINE)) + 1
    stripped = body.rstrip()
    trailing = body[len(stripped) :]
    insert_at = offset + len(stripped)
    return content[:insert_at] + f"\n{number}. {item}" + trailing + content[offset + len(body) :]


def cmd_arm_proposal_revision(config: BRConfig, args: argparse.Namespace) -> int:
    """Arm a proposal revision; prints ``[PROPOSAL_REVISION_ARMED] <ID>`` when it acts.

    Returns:
        0 armed (marker written, ``decision_needed: true``), 1 with
        ``[NO_ALTERNATIVE] <ID>`` and no file change when there is no eligible
        alternative, 2 when the issue is not found.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    content = path.read_text()
    label, others_remain = _selected_eligible_label(content)
    if label is None or not others_remain:
        print(f"[NO_ALTERNATIVE] {args.issue_id}")
        return 1

    fm = parse_frontmatter(content)
    evidence = " ".join(str(fm.get("verify_evidence") or "").split()) or _NO_EVIDENCE
    item = (
        f"**Refuted option**: {label} — /ll:verify-issues {date.today().isoformat()}: "
        f"{evidence}. Which remaining option replaces it?"
    )
    new_content = update_frontmatter(_append_marker(content, item), {"decision_needed": True})
    path.write_text(new_content)
    print(f"[PROPOSAL_REVISION_ARMED] {args.issue_id}")
    return 0
