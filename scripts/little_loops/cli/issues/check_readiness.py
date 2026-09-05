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
    # BUG-3390: per-issue escalation valve stamped by /ll:go-no-go on a GO
    # verdict over an `oversized_atomic` deferral (BUG-2734). Read from raw
    # frontmatter so the CLI gate and autodev's inline gates agree.
    outcome_gate_waived: bool = False

    @property
    def meets_readiness(self) -> bool:
        """Mirrors manage-issue Phase 2.5 — readiness only."""
        return self.confidence >= self.readiness_threshold

    @property
    def meets_outcome(self) -> bool:
        return self.outcome >= self.outcome_threshold

    @property
    def meets_outcome_or_waived(self) -> bool:
        """Outcome half of the gate with the BUG-2734 waiver honored.

        Kept separate from `meets_outcome` so the `ll-auto` pre-Phase-1 gate
        (readiness-only) and any caller that must ignore the waiver are
        unaffected (BUG-3390).
        """
        return self.outcome_gate_waived or self.meets_outcome


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
    readiness_override: int | None = None,
    outcome_override: int | None = None,
) -> ReadinessStatus | None:
    """Resolve an issue's readiness status, or None if the issue can't be found.

    Threshold resolution stays the absence-sensitive raw-JSON read this
    replaces (moved verbatim, not re-sourced from `config.commands.confidence_gate`):
    `default_readiness`/`default_outcome` win only when the `commands.confidence_gate`
    keys are absent from `ll-config.json`. `ConfidenceGateConfig` always populates
    non-None defaults, so it cannot express "absent" and would break the
    `--readiness`/`--outcome` CLI fallback the `autodev.yaml` call sites depend on.

    BUG-3390: `readiness_override`/`outcome_override`, when not None, win over
    both config and defaults. This is how an *explicit* `--readiness N` on the
    CLI is distinguished from the argparse default — previously config silently
    overrode an explicit per-run threshold, so autodev's `--context
    readiness_threshold=NN` was honored by its inline-python gates but ignored
    by its `check-readiness`-based gates.

    Args:
        config: Project configuration
        issue_id: Issue ID or path to resolve
        default_readiness: Fallback readiness threshold when unset in config
        default_outcome: Fallback outcome threshold when unset in config
        readiness_override: Explicit readiness threshold that beats config
        outcome_override: Explicit outcome threshold that beats config

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
    if readiness_override is not None:
        readiness = readiness_override
    if outcome_override is not None:
        outcome = outcome_override

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        return None

    fm = parse_frontmatter(path.read_text(), coerce_types=True)
    raw_confidence = _coerce_optional_int(fm.get("confidence_score"))
    raw_outcome = _coerce_optional_int(fm.get("outcome_confidence"))
    confidence = int(fm.get("confidence_score") or 0)
    outcome_val = int(fm.get("outcome_confidence") or 0)
    waived = str(fm.get("outcome_gate_waived")).lower() == "true"

    return ReadinessStatus(
        confidence=confidence,
        outcome=outcome_val,
        readiness_threshold=readiness,
        outcome_threshold=outcome,
        enabled=enabled,
        raw_confidence=raw_confidence,
        raw_outcome=raw_outcome,
        outcome_gate_waived=waived,
    )


def cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 if the issue's confidence and outcome scores meet thresholds.

    Thresholds: an explicit `--readiness` / `--outcome` wins; otherwise the
    ll-config.json `commands.confidence_gate` values; otherwise 85 / 65
    (BUG-3390 — previously config silently overrode explicit CLI values).
    Requires both thresholds and ignores `enabled`.

    `--honor-waiver` treats the outcome half as met when the issue carries
    `outcome_gate_waived: true` (the BUG-2734 escalation valve stamped by
    /ll:go-no-go); readiness is still enforced.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id, .readiness, .outcome, .honor_waiver

    Returns:
        0 if both thresholds are met, 1 otherwise, 2 if the issue is unresolvable
    """
    status = readiness_status(
        config,
        args.issue_id,
        readiness_override=getattr(args, "readiness", None),
        outcome_override=getattr(args, "outcome", None),
    )
    if status is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    outcome_ok = (
        status.meets_outcome_or_waived
        if getattr(args, "honor_waiver", False)
        else status.meets_outcome
    )
    return 0 if (status.meets_readiness and outcome_ok) else 1
