"""Single budget owner for learning-proof evidence (ENH-3602).

``assess_proof`` is the one source of truth for whether an issue's learning
proof — learning-test registry records plus the issue's spike proof — is
sufficient, stale, refuted, or absent, and owns the per-issue attempt-budget
policy. Consumers (confidence-check, ready-issue, the ``ll-auto`` learning
gate) read its verdict and map per-status responses; they do not re-derive
classification.

Proof sources: the registry stores learning-test records keyed by the target
strings from ``learning_tests_required``; the only spike state readable from
the issue file alone is its frontmatter flag set (``spike_attempted`` /
``spike_completed`` / ``spike_refuted``, written by ``/ll:spike``) plus the
``gate:`` entries resolved via ``resolve_gate_verdict`` — which takes
``spike_proven`` as an input, derived here from those flags. The JUnit-XML
spike classifier is deliberately not used: it needs the spike run's report
artifacts, which the issue does not carry.

Budget: the spike/learning attempt *counter* stays run-scoped in the caller's
``run_dir``; only the cap policy lives here. Run-scoped callers pass
``attempts_used`` from their counter (``budget_remaining = max(0, 2 - used)``).
``attempts_used=None`` (standalone skills) means no run-scoped budget applies
— which is not unlimited spend: the policy caps provisioning at one attempt
per unproven target per caller invocation, followed by a re-assessment whose
verdict is final.

All little_loops imports are function-local: this module is imported from
``little_loops.learning_tests.__init__``, which itself loads mid-``little_loops``
package init (via ``issue_manager``), so a module-scope import of anything
that pulls ``little_loops.cli`` would cycle hard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

logger = logging.getLogger(__name__)

ProofStatus = Literal["proven", "stale", "refuted", "absent", "not_required"]

# Worst-status-wins aggregation order. ``refuted`` outranks ``absent``: an
# active disproof is strictly worse evidence than no record (consumers map
# both to provision-once/STOP today, so the tie-break only affects the
# reported reason, but it must be deterministic).
_SEVERITY: dict[str, int] = {"proven": 0, "stale": 1, "absent": 2, "refuted": 3}

# Run-scoped budget cap: at most 2 spike/explore attempts per issue per run.
_MAX_ATTEMPTS = 2


@dataclass
class ProofVerdict:
    """Aggregated proof verdict for one issue.

    ``status`` is the worst status among the declared targets (empty target
    set → ``not_required``). ``targets`` maps each learning-test target (and
    the literal ``spike`` key when a spike requirement exists) to its
    individual status. ``budget_remaining`` is ``None`` for standalone
    (non-run-scoped) callers.
    """

    issue_id: str
    status: ProofStatus
    targets: dict[str, ProofStatus]
    budget_remaining: int | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "issue_id": self.issue_id,
            "status": self.status,
            "targets": dict(self.targets),
            "budget_remaining": self.budget_remaining,
            "reason": self.reason,
        }


def _learning_test_statuses(
    declared: list[str],
    *,
    staleness_enabled: bool,
    stale_after_days: int,
    version_aware: bool,
    backstop_multiplier: int,
    base_dir: Path,
) -> dict[str, tuple[str, str]]:
    """Classify each declared learning-test target against the registry.

    Returns ``{target: (status, staleness detail)}`` where the detail is the
    ``describe_staleness`` render for stale targets and ``""`` otherwise.
    """
    # Function-local: little_loops.learning_tests is mid-init when this
    # package first loads (see module docstring).
    from little_loops.learning_tests import check_learning_test
    from little_loops.learning_tests.gate import describe_staleness, is_record_stale

    statuses: dict[str, tuple[str, str]] = {}
    for target in declared:
        record = check_learning_test(target, base_dir=base_dir)
        if record is None:
            statuses[target] = ("absent", "")
            continue
        if record.status == "refuted":
            statuses[target] = ("refuted", "")
            continue
        if staleness_enabled and is_record_stale(
            record,
            stale_after_days,
            version_aware=version_aware,
            backstop_multiplier=backstop_multiplier,
        ):
            statuses[target] = (
                "stale",
                describe_staleness(
                    record,
                    stale_after_days,
                    version_aware=version_aware,
                    backstop_multiplier=backstop_multiplier,
                )
                or "stale",
            )
            continue
        statuses[target] = ("proven", "")
    return statuses


def _spike_status(frontmatter: dict[str, Any], text: str) -> str | None:
    """Classify the issue's spike proof, or None when no requirement exists.

    A spike requirement exists when any spike flag is set (``spike_needed`` /
    ``spike_attempted`` / ``spike_completed`` / ``spike_refuted``) or the
    structured gate verdict is ``structured_proof`` (an unsatisfied ``proof``
    gate that spike proof would satisfy). A *satisfied* proof gate carries no
    outstanding spike requirement, so it does not add the key.
    """

    def flag(key: str) -> bool:
        return str(frontmatter.get(key, "")).strip().lower() == "true"

    spike_refuted = flag("spike_refuted")
    spike_proven = flag("spike_completed") and not spike_refuted

    gates_declared = any(
        flag(key) for key in ("spike_needed", "spike_attempted", "spike_completed", "spike_refuted")
    )
    if not gates_declared:
        # Function-local import: little_loops.cli's package __init__ imports
        # every CLI main (including cli/auto.py → issue_manager), which is
        # mid-init when this package first loads — a module-scope import
        # would be a hard cycle. check_gate.py itself is stdlib-only.
        from little_loops.cli.issues.check_gate import resolve_gate_verdict

        gate_verdict, _gates = resolve_gate_verdict(frontmatter, text, spike_proven)
        if gate_verdict != "structured_proof":
            return None
    if spike_refuted:
        return "refuted"
    if spike_proven:
        return "proven"
    return "absent"


def assess_proof(
    issue_path: Path,
    *,
    attempts_used: int | None = None,
    stale_after_days: int | None = None,
    cwd: Path | None = None,
    targets: list[str] | None = None,
) -> ProofVerdict:
    """Classify the issue's learning proof and apply the attempt-budget policy.

    Args:
        issue_path: Path to the issue file (must exist and be readable).
        attempts_used: Run-scoped spend already consumed by the caller
            (e.g. a ``${context.run_dir}`` spike counter). ``None`` marks a
            standalone caller: no run-scoped budget, provisioning capped at
            one attempt per unproven target per invocation by policy.
        stale_after_days: Explicit age threshold override. ``None`` resolves
            the ``learning_tests`` config trio (``stale_after_days``,
            ``version_aware_staleness``, ``version_match_backstop_multiplier``
            — the same set the FSM learning state reads); when
            ``learning_tests.enabled`` is false, staleness evaluation is off
            entirely (a proven record counts fresh), matching the executor.
        cwd: Project root for config and registry lookup. Defaults to
            ``Path.cwd()``.
        targets: Caller-resolved learning-test targets that take precedence
            over the issue's ``learning_tests_required`` frontmatter (the
            ENH-2834 registry-resolved shape; also correct for JIT-resolved
            targets where the frontmatter field is absent). ``None`` reads
            the frontmatter.

    Returns:
        A :class:`ProofVerdict` whose ``status`` is the worst status among
        the declared targets (``not_required`` when nothing is declared).
    """
    from little_loops.frontmatter import parse_frontmatter

    working_dir = cwd or Path.cwd()
    text = issue_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text, coerce_types=True)
    issue_id = str(fm.get("id") or issue_path.stem)

    # Staleness knobs: config trio with hard fallbacks (the executor's
    # pattern — a config failure must degrade, never break classification).
    staleness_enabled = False
    effective_days = 30
    version_aware = True
    backstop_multiplier = 12
    try:
        from little_loops.config import BRConfig

        lt_config = BRConfig(working_dir).learning_tests
        staleness_enabled = bool(lt_config.enabled)
        effective_days = int(lt_config.stale_after_days)
        version_aware = bool(lt_config.version_aware_staleness)
        backstop_multiplier = int(lt_config.version_match_backstop_multiplier)
    except Exception:  # noqa: BLE001 — config failure degrades to staleness-off
        logger.debug("learning_tests config unavailable for %s", issue_path, exc_info=True)
    if stale_after_days is not None:
        effective_days = stale_after_days

    if targets is not None:
        declared = [str(t) for t in targets if str(t).strip()]
    else:
        value = fm.get("learning_tests_required")
        declared = [str(t) for t in value if str(t).strip()] if isinstance(value, list) else []

    target_statuses: dict[str, ProofStatus] = {}
    reasons: list[str] = []
    for target, (status, detail) in _learning_test_statuses(
        declared,
        staleness_enabled=staleness_enabled,
        stale_after_days=effective_days,
        version_aware=version_aware,
        backstop_multiplier=backstop_multiplier,
        base_dir=working_dir / ".ll" / "learning-tests",
    ).items():
        target_statuses[target] = status  # type: ignore[assignment]
        if status != "proven":
            reasons.append(f"{target}={status}" + (f" ({detail})" if detail else ""))

    spike = _spike_status(fm, text)
    if spike is not None:
        target_statuses["spike"] = spike  # type: ignore[assignment]
        if spike != "proven":
            reasons.append(f"spike={spike}")

    if not target_statuses:
        overall_status: ProofStatus = "not_required"
        reason = "no proof requirements declared"
    else:
        overall_status = max(target_statuses.values(), key=lambda s: _SEVERITY[s])
        reason = "; ".join(reasons) if reasons else "all proof targets proven"

    budget_remaining = None if attempts_used is None else max(0, _MAX_ATTEMPTS - attempts_used)
    return ProofVerdict(
        issue_id=issue_id,
        status=cast(ProofStatus, overall_status),
        targets=target_statuses,
        budget_remaining=budget_remaining,
        reason=reason,
    )
