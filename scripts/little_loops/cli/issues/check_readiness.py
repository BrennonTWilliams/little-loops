"""ll-issues check-readiness: Exit 0 if an issue meets readiness thresholds."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 if the issue's confidence and outcome scores meet thresholds.

    Reads thresholds from ll-config.json (commands.confidence_gate), falling
    back to the values supplied via --readiness / --outcome CLI args so callers
    can pass loop-context defaults without special-casing the config file.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id, .readiness, .outcome

    Returns:
        0 if both thresholds are met, 1 otherwise
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter

    default_readiness: int = args.readiness
    default_outcome: int = args.outcome

    config_path = config.project_root / ".ll" / "ll-config.json"
    try:
        raw = json.loads(config_path.read_text())
        cg = raw.get("commands", {}).get("confidence_gate", {})
        readiness = cg.get("readiness_threshold", default_readiness)
        outcome = cg.get("outcome_threshold", default_outcome)
    except Exception:
        readiness = default_readiness
        outcome = default_outcome

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    fm = parse_frontmatter(path.read_text(), coerce_types=True)
    confidence = int(fm.get("confidence_score") or 0)
    outcome_val = int(fm.get("outcome_confidence") or 0)

    return 0 if (confidence >= readiness and outcome_val >= outcome) else 1
