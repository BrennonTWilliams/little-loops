"""ll-issues check-gate: structured-first policy-gate probe (ENH-3575).

Autodev used to grep the whole issue file for gate phrases in two places
(``check_gate_at_dequeue`` and ``recheck_after_size_review``). This module is the
single home of that detection plus the structured ``gate`` frontmatter field
that supersedes it. When ``gate`` is present it alone decides; the prose regex
is only the fallback for issues without the field.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from little_loops.config import BRConfig

GateVerdict = Literal[
    "structured_open", "structured_proof", "structured_satisfied", "prose", "none"
]

GATE_KINDS = ("external", "manual", "proof")

# Verdicts that mean a gate is in force (exit 0); everything else exits 1.
_IN_FORCE = ("structured_open", "structured_proof", "prose")

_PROSE_GATE_RE = re.compile(
    r"do not start otherwise|measurement \(gate\)|pre-implementation measurement"
    r"|⚠ Gated|do not implement before|evidence gate|gate opens|is explicitly gated",
    re.IGNORECASE,
)

_NULL_STRINGS = ("", "null", "~", "none")


@dataclass
class GateSpec:
    """One normalized entry of the ``gate`` frontmatter field."""

    kind: Literal["external", "manual", "proof"]
    satisfied: bool
    evidence: str | None = None
    owner: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "satisfied": self.satisfied,
            "evidence": self.evidence,
            "owner": self.owner,
        }


def _opt_str(value: Any) -> str | None:
    """Normalize a nested scalar: null-ish strings become None."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in _NULL_STRINGS else text


def _parse_entry(raw: Any) -> GateSpec:
    """Normalize one gate mapping; malformed data fails toward parking (manual, unsatisfied)."""
    if not isinstance(raw, dict):
        return GateSpec(kind="manual", satisfied=False)
    kind = str(raw.get("kind") or "").strip().lower()
    satisfied = str(raw.get("satisfied") or "").strip().lower() == "true"
    if kind not in GATE_KINDS:
        return GateSpec(
            kind="manual",
            satisfied=False,
            evidence=_opt_str(raw.get("evidence")),
            owner=_opt_str(raw.get("owner")),
        )
    return GateSpec(
        kind=kind,  # type: ignore[arg-type]
        satisfied=satisfied,
        evidence=_opt_str(raw.get("evidence")),
        owner=_opt_str(raw.get("owner")),
    )


def parse_gate(frontmatter: dict[str, Any]) -> list[GateSpec] | None:
    """Normalize the ``gate`` field (lone mapping or list of mappings).

    Returns ``None`` when the field is absent and ``[]`` when present but empty
    (``gate: []``); the precedence rule keys on presence, not entry count.
    """
    if "gate" not in frontmatter:
        return None
    raw = frontmatter["gate"]
    if raw is None or (isinstance(raw, str) and raw.strip().lower() in ("", "[]", "null", "~")):
        return []
    if isinstance(raw, dict):
        return [_parse_entry(raw)]
    if isinstance(raw, list):
        return [_parse_entry(item) for item in raw]
    return [GateSpec(kind="manual", satisfied=False)]


def detect_prose_gate(text: str) -> bool:
    """True when *text* contains any of the legacy prose gate phrases."""
    return _PROSE_GATE_RE.search(text) is not None


def resolve_gate_verdict(
    frontmatter: dict[str, Any], text: str, spike_proven: bool
) -> tuple[GateVerdict, list[GateSpec]]:
    """Apply the structured-first, prose-fallback decision rules.

    Returns the verdict and the parsed gate entries (empty for prose/none).
    """
    gates = parse_gate(frontmatter)
    if gates is None:
        return ("prose" if detect_prose_gate(text) else "none"), []
    if any(g.kind in ("external", "manual") and not g.satisfied for g in gates):
        return "structured_open", gates
    if any(g.kind == "proof" and not g.satisfied for g in gates) and not spike_proven:
        return "structured_proof", gates
    return "structured_satisfied", gates


def add_check_gate_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the check-gate subparser on *subs* (ENH-3575)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "check-gate",
        help=(
            "Print the policy-gate verdict for an issue; exit 0 if a gate is in force, "
            "1 if not, 2 if unresolvable (ENH-3575)"
        ),
    )
    p.set_defaults(command="check-gate")
    p.add_argument("issue_id", help="Issue ID (e.g., 3575, ENH-3575, P3-ENH-3575)")
    p.add_argument("--json", "-j", action="store_true", help="Output as JSON object")
    add_config_arg(p)
    return p


def cmd_check_gate(config: BRConfig, args: argparse.Namespace) -> int:
    """Print the gate verdict token; exit 0 if a gate is in force, 1 if not, 2 if not found."""
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    text = path.read_text()
    fm = parse_frontmatter(text, coerce_types=True)
    spike_proven = (
        str(fm.get("spike_completed")).lower() == "true"
        and str(fm.get("spike_refuted")).lower() != "true"
    )
    verdict, gates = resolve_gate_verdict(fm, text, spike_proven)

    if getattr(args, "json", False):
        print(json.dumps({"verdict": verdict, "gates": [g.to_dict() for g in gates]}))
    else:
        print(verdict)
    return 0 if verdict in _IN_FORCE else 1
