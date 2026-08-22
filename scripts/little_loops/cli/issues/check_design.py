"""ll-issues check-design: Exit 0 if the Program Design gate passes (ENH-2967).

Single CLI owner of the `design_gate_failed()` predicate, replacing the three
independent inline `python3 -c "..."` blocks in autodev.yaml that each
re-derived the same "Program Design gate failed" boolean from raw
`format-check --format json` output.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_check_design(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 if the Program Design gate passes for the issue, 1 if it fails.

    Fails open (exit 0) on projects that haven't armed the Program Design
    specificity gate, mirroring `check_format_gaps()`'s existing fail-open
    behavior — this command adds no new failure mode on top of it.

    Returns:
        0 when the gate passes (or is inert), 1 when it fails, 2 when the
        issue cannot be resolved (BUG-3294 — "cannot evaluate" is distinct
        from a genuine negative).
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.issue_parser import check_format_gaps, design_gate_failed

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    gaps = check_format_gaps(path)
    return 1 if design_gate_failed(gaps) else 0
