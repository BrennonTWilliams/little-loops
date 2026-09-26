"""ll-issues next-obligation: report the unmet preparation obligation (ISSUE-ID) (FEAT-3598).

Deterministic per-issue selector that composes the existing readiness gates in the
order ``refine-to-ready-issue`` routes on them. No LLM calls, no file writes.

The child loop's gates form a tree, not a chain, so the selector has three tiers:

1. Pre-score gates, first unmet wins: ``FORMAT``, ``VERIFY``, ``HEDGES``,
   ``PLACEHOLDERS``, ``ACCEPTANCE_CRITERIA``, ``DESIGN``.
2. Scores (``SCORES``): readiness, then outcome. Passing scores return ``NONE`` even
   when ``decision_needed`` / spike flags are set (``check_outcome.on_yes = done``).
3. Low-outcome diagnosis, only when readiness passes and outcome is below threshold:
   ``DECISION``, ``PROOF``, ``ARTIFACTS``; otherwise ``SCORES/outcome_below``.

The selector is stateless: budget counters, attempt counts and one-shot fallbacks
belong to the caller, which passes ``--skip OBLIGATION`` to move past a soft gate.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig


class Obligation(Enum):
    """Unmet preparation obligations, declared in tier/check order.

    Tier 1 (pre-score): FORMAT, VERIFY, HEDGES, PLACEHOLDERS, ACCEPTANCE_CRITERIA,
    DESIGN. Tier 2: SCORES. Tier 3 (low-outcome diagnosis): DECISION, PROOF,
    ARTIFACTS. ``NONE`` means nothing is unmet.

    Known PROOF departure from ``check_spike_needed`` parity: PROOF delegates to
    ``assess_proof`` (ENH-3602), so it also reports ``absent`` for
    ``spike_attempted=true`` without ``spike_completed`` and folds in a
    ``structured_proof`` gate verdict (check-gate, ENH-3575); the child does
    neither, and also spends a ``spike-runs-<ID>`` budget the selector does not.
    """

    FORMAT = "FORMAT"
    VERIFY = "VERIFY"
    HEDGES = "HEDGES"
    PLACEHOLDERS = "PLACEHOLDERS"
    ACCEPTANCE_CRITERIA = "ACCEPTANCE_CRITERIA"
    DESIGN = "DESIGN"
    SCORES = "SCORES"
    DECISION = "DECISION"
    PROOF = "PROOF"
    ARTIFACTS = "ARTIFACTS"
    NONE = "NONE"


class ObligationProbeError(Exception):
    """A fail-closed probe (VERIFY, SCORES) could not assess the issue."""


@dataclass
class ObligationResult:
    """The unmet obligation for one issue, plus how it was reached."""

    issue_id: str
    obligation: Obligation
    sub_reason: str | None = None
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    probe_errors: list[str] = field(default_factory=list)

    def token(self) -> str:
        """``OBLIGATION[:sub_reason]`` — matchable by an FSM ``route:`` table."""
        if self.sub_reason:
            return f"{self.obligation.value}:{self.sub_reason}"
        return self.obligation.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "obligation": self.obligation.value,
            "sub_reason": self.sub_reason,
            "reason": self.reason,
            "evidence": self.evidence,
            "skipped": self.skipped,
            "probe_errors": self.probe_errors,
        }


_TIER1 = (
    Obligation.FORMAT,
    Obligation.VERIFY,
    Obligation.HEDGES,
    Obligation.PLACEHOLDERS,
    Obligation.ACCEPTANCE_CRITERIA,
    Obligation.DESIGN,
)


def select_next_obligation(
    config: BRConfig,
    issue_id: str,
    *,
    skip: Iterable[Obligation] = (),
    readiness_override: int | None = None,
    outcome_override: int | None = None,
    honor_waiver: bool = False,
) -> ObligationResult | None:
    """Return the unmet obligation ``refine-to-ready-issue`` would route on.

    Resolves the issue once. Returns None when *issue_id* can't be resolved. Raises
    :class:`ObligationProbeError` when a fail-closed probe (VERIFY, SCORES) errors.
    A probe error on a fail-open obligation is recorded in ``probe_errors`` and that
    obligation counts as met. Obligations in *skip* are treated as met.

    ``VERIFY`` reflects the last *persisted* ``verify_verdict``; the child clears it
    before every verify, so outside a child run it may be stale.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        return None

    skipped = set(skip)
    skipped_names = [o.value for o in Obligation if o in skipped]
    probe_errors: list[str] = []
    content = path.read_text()
    fm = parse_frontmatter(content, coerce_types=True)
    display_id = str(fm.get("id") or issue_id)

    def result(
        obligation: Obligation,
        sub_reason: str | None = None,
        reason: str = "",
        evidence: list[str] | None = None,
    ) -> ObligationResult:
        return ObligationResult(
            issue_id=display_id,
            obligation=obligation,
            sub_reason=sub_reason,
            reason=reason,
            evidence=evidence or [],
            skipped=skipped_names,
            probe_errors=probe_errors,
        )

    def fail_open(obligation: Obligation, exc: Exception) -> None:
        probe_errors.append(f"{obligation.value}: {type(exc).__name__}: {exc}")

    # Tier 1: pre-score gates.
    for ob in _TIER1:
        if ob in skipped:
            continue
        if ob is Obligation.VERIFY:
            try:
                verdict_class = _verify_class(fm)
            except Exception as exc:  # noqa: BLE001 — fail closed
                raise ObligationProbeError(f"VERIFY: {type(exc).__name__}: {exc}") from exc
            if verdict_class != "VALID":
                return result(
                    ob,
                    verdict_class,
                    f"verify_verdict is {verdict_class}"
                    if verdict_class != "absent"
                    else "no verify_verdict in frontmatter",
                    [f"verify_verdict={fm.get('verify_verdict')!r}"],
                )
            continue
        try:
            unmet = _tier1_probe(ob, path, content)
        except Exception as exc:  # noqa: BLE001 — fail open
            fail_open(ob, exc)
            continue
        if unmet is not None:
            reason, evidence = unmet
            return result(ob, None, reason, evidence)

    # Tier 2: scores.
    if Obligation.SCORES in skipped:
        return result(Obligation.NONE, None, "SCORES skipped")
    from little_loops.cli.issues.check_readiness import readiness_status

    try:
        status = readiness_status(
            config,
            issue_id,
            readiness_override=readiness_override,
            outcome_override=outcome_override,
        )
    except Exception as exc:  # noqa: BLE001 — fail closed
        raise ObligationProbeError(f"SCORES: {type(exc).__name__}: {exc}") from exc
    if status is None:
        return None
    scores = [
        f"confidence={status.confidence} (threshold {status.readiness_threshold})",
        f"outcome={status.outcome} (threshold {status.outcome_threshold})",
    ]
    if status.confidence_absent or status.outcome_absent:
        return result(Obligation.SCORES, "absent", "confidence or outcome score is absent", scores)
    if not status.meets_readiness:
        return result(Obligation.SCORES, "readiness_below", "readiness below threshold", scores)
    outcome_ok = status.meets_outcome_or_waived if honor_waiver else status.meets_outcome
    if outcome_ok:
        return result(Obligation.NONE, None, "scores meet thresholds", scores)

    # Tier 3: low-outcome diagnosis.
    for ob in (Obligation.DECISION, Obligation.PROOF, Obligation.ARTIFACTS):
        if ob in skipped:
            continue
        try:
            unmet3 = _tier3_probe(ob, config, path, fm)
        except Exception as exc:  # noqa: BLE001 — fail open
            fail_open(ob, exc)
            continue
        if unmet3 is not None:
            sub_reason, reason, evidence = unmet3
            return result(ob, sub_reason, reason, evidence)
    return result(
        Obligation.SCORES,
        "outcome_below",
        "outcome below threshold with no decision/proof/artifact explanation",
        scores,
    )


def _verify_class(fm: dict[str, Any]) -> str:
    from little_loops.cli.issues.check_verify_verdict import classify_verify_verdict

    return classify_verify_verdict(fm.get("verify_verdict"))


def _tier1_probe(ob: Obligation, path: Any, content: str) -> tuple[str, list[str]] | None:
    """Return ``(reason, evidence)`` when tier-1 obligation *ob* is unmet, else None."""
    if ob is Obligation.FORMAT:
        from little_loops.issue_parser import check_format_gaps, directive_gaps

        directive = directive_gaps(check_format_gaps(path))
        return ("directive format gaps present", list(directive)) if directive else None
    if ob is Obligation.HEDGES:
        from little_loops.issue_parser import count_open_questions_in_sections

        n = count_open_questions_in_sections(content)
        return (f"{n} unresolved open question(s)", [f"open_questions={n}"]) if n > 0 else None
    if ob is Obligation.PLACEHOLDERS:
        from little_loops.issue_parser import placeholder_count

        n = placeholder_count(path)
        return (f"{n} unfilled template placeholder(s)", [f"placeholders={n}"]) if n > 0 else None
    if ob is Obligation.ACCEPTANCE_CRITERIA:
        from little_loops.cli.issues.check_acceptance_criteria import _find_manual_criteria

        manual = _find_manual_criteria(content)
        return ("acceptance criteria requiring manual verification", manual) if manual else None
    if ob is Obligation.DESIGN:
        from little_loops.issue_parser import check_format_gaps, design_gate_failed

        gaps = check_format_gaps(path)
        if not design_gate_failed(gaps):
            return None
        evidence = list(gaps.program_design_nonspecific)
        if "Program Design" in gaps.missing:
            evidence.append("Program Design section missing")
        if "Program Design" in gaps.empty:
            evidence.append("Program Design section empty")
        return "Program Design gate failed", evidence
    raise ValueError(f"not a tier-1 obligation: {ob}")


def _tier3_probe(
    ob: Obligation, config: BRConfig, path: Any, fm: dict[str, Any]
) -> tuple[str | None, str, list[str]] | None:
    """Return ``(sub_reason, reason, evidence)`` when tier-3 obligation *ob* is unmet."""
    if ob is Obligation.DECISION:
        if str(fm.get("decision_needed")).lower() == "true":
            return None, "decision_needed is true", ["decision_needed=true"]
        return None
    if ob is Obligation.PROOF:
        from little_loops.learning_tests import assess_proof

        verdict = assess_proof(path, cwd=config.project_root)
        if verdict.status in ("absent", "stale", "refuted"):
            evidence = [f"{t}={s}" for t, s in verdict.targets.items()]
            return verdict.status, verdict.reason or f"proof is {verdict.status}", evidence
        return None
    if ob is Obligation.ARTIFACTS:
        if str(fm.get("missing_artifacts")).lower() == "true":
            return None, "missing_artifacts is true", ["missing_artifacts=true"]
        return None
    raise ValueError(f"not a tier-3 obligation: {ob}")


def add_next_obligation_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the next-obligation subparser on *subs* (FEAT-3598)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "next-obligation",
        help=(
            "Print the unmet preparation obligation for an issue (exit 0 on any assessment, "
            "2 if unresolvable or a fail-closed probe errors) (FEAT-3598)"
        ),
    )
    p.set_defaults(command="next-obligation")
    p.add_argument("issue_id", help="Issue ID (e.g., 3598, FEAT-3598, P3-FEAT-3598)")
    p.add_argument(
        "--format",
        choices=["text", "json", "token"],
        default="text",
        help="Output format; 'token' prints only OBLIGATION[:sub_reason] (default: text)",
    )
    p.add_argument(
        "--skip",
        action="append",
        default=[],
        choices=[o.value for o in Obligation if o is not Obligation.NONE],
        metavar="OBLIGATION",
        help="Treat OBLIGATION as met (repeatable); the caller's budget state decides",
    )
    p.add_argument("--readiness-threshold", type=int, default=None, metavar="N")
    p.add_argument("--outcome-threshold", type=int, default=None, metavar="N")
    p.add_argument(
        "--honor-waiver",
        action="store_true",
        help="Count a waived outcome shortfall (outcome_gate_waived) as met",
    )
    add_config_arg(p)
    return p


def cmd_next_obligation(config: BRConfig, args: argparse.Namespace) -> int:
    """Print the unmet obligation; exit 0 on any assessment, 2 on a read error."""
    from little_loops.cli.output import print_json

    try:
        res = select_next_obligation(
            config,
            args.issue_id,
            skip=[Obligation(s) for s in getattr(args, "skip", None) or []],
            readiness_override=getattr(args, "readiness_threshold", None),
            outcome_override=getattr(args, "outcome_threshold", None),
            honor_waiver=getattr(args, "honor_waiver", False),
        )
    except ObligationProbeError as exc:
        print(f"Error: could not assess '{args.issue_id}': {exc}", file=sys.stderr)
        return 2
    if res is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    fmt = getattr(args, "format", "text")
    if fmt == "json":
        print_json(res.to_dict())
    elif fmt == "token":
        print(res.token())
    else:
        line = res.token()
        if res.reason:
            line += f" — {res.reason}"
        print(f"{res.issue_id}: {line}")
        for item in res.evidence:
            print(f"  - {item}")
        for err in res.probe_errors:
            print(f"  ! probe error: {err}", file=sys.stderr)
    return 0
