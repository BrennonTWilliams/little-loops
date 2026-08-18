"""ll-issues check-readiness: Exit 0 if an issue meets readiness thresholds."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig


@dataclass
class ReadinessStatus:
    """An issue's confidence/outcome scores against configured thresholds.

    Deliberately has no combined ``passed`` property: `cmd_check_readiness`
    requires both `meets_readiness` and `meets_outcome` and ignores `enabled`,
    while the `ll-auto` pre-Phase-1 gate (BUG-3004) consults `enabled` and
    `meets_readiness` only, mirroring `manage-issue` Phase 2.5 exactly. Folding
    these into one verdict would make one caller wrong.
    """

    confidence: int
    outcome: int
    readiness_threshold: int
    outcome_threshold: int
    enabled: bool
    raw_confidence: int | None = None
    raw_outcome: int | None = None

    @property
    def meets_readiness(self) -> bool:
        """Mirrors manage-issue Phase 2.5 — readiness only."""
        return self.confidence >= self.readiness_threshold

    @property
    def meets_outcome(self) -> bool:
        return self.outcome >= self.outcome_threshold


def _coerce_optional_int(raw: Any) -> int | None:
    """Coerce a frontmatter value to int, rejecting non-digit strings.

    Mirrors ``IssueParser._coerce_optional_int`` (issue_parser.py:2908) — not
    imported from there because that method is an instance method on a class
    this thin CLI leaf should not depend on. Correct on both `int` and `str`
    input via `str.isdigit()`; negatives and floats coerce to None.
    """
    return int(raw) if raw is not None and str(raw).isdigit() else None


def readiness_status(
    config: BRConfig,
    issue_id: str,
    *,
    default_readiness: int = 85,
    default_outcome: int = 65,
) -> ReadinessStatus | None:
    """Resolve an issue's readiness status, or None if the issue can't be found.

    Threshold resolution stays the absence-sensitive raw-JSON read this
    replaces (moved verbatim, not re-sourced from `config.commands.confidence_gate`):
    `default_readiness`/`default_outcome` win only when the `commands.confidence_gate`
    keys are absent from `ll-config.json`. `ConfidenceGateConfig` always populates
    non-None defaults, so it cannot express "absent" and would break the
    `--readiness`/`--outcome` CLI fallback the `autodev.yaml` call sites depend on.

    Args:
        config: Project configuration
        issue_id: Issue ID or path to resolve
        default_readiness: Fallback readiness threshold when unset in config
        default_outcome: Fallback outcome threshold when unset in config

    Returns:
        ReadinessStatus, or None if the issue could not be resolved.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter

    config_path = config.project_root / ".ll" / "ll-config.json"
    enabled = False
    try:
        raw = json.loads(config_path.read_text())
        cg = raw.get("commands", {}).get("confidence_gate", {})
        readiness = cg.get("readiness_threshold", default_readiness)
        outcome = cg.get("outcome_threshold", default_outcome)
        enabled = bool(cg.get("enabled", False))
    except Exception:
        readiness = default_readiness
        outcome = default_outcome

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        return None

    fm = parse_frontmatter(path.read_text(), coerce_types=True)
    raw_confidence = _coerce_optional_int(fm.get("confidence_score"))
    raw_outcome = _coerce_optional_int(fm.get("outcome_confidence"))
    confidence = int(fm.get("confidence_score") or 0)
    outcome_val = int(fm.get("outcome_confidence") or 0)

    return ReadinessStatus(
        confidence=confidence,
        outcome=outcome_val,
        readiness_threshold=readiness,
        outcome_threshold=outcome,
        enabled=enabled,
        raw_confidence=raw_confidence,
        raw_outcome=raw_outcome,
    )


def cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 if the issue's confidence and outcome scores meet thresholds.

    Reads thresholds from ll-config.json (commands.confidence_gate), falling
    back to the values supplied via --readiness / --outcome CLI args so callers
    can pass loop-context defaults without special-casing the config file.
    Requires both thresholds and ignores `enabled` — unchanged behavior,
    reimplemented over `readiness_status()`.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id, .readiness, .outcome

    Returns:
        0 if both thresholds are met, 1 otherwise
    """
    status = readiness_status(
        config,
        args.issue_id,
        default_readiness=args.readiness,
        default_outcome=args.outcome,
    )
    if status is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    return 0 if (status.meets_readiness and status.meets_outcome) else 1
