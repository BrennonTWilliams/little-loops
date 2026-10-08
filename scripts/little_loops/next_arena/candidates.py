"""Candidate assessment and generation for ``ll-next`` (FEAT-3561 phase D).

``assess_candidates`` is the **single** scoring path: it assesses every discovered inventory
target (all statuses, EPICs, ambiguous and unsupported sources included) for every registered
verb, evaluates tri-state gates, computes bounded axes, the weighted geometric utility,
coverage and the within-verb rank once, and retains exclusion reasons for ineligible targets.
``generate_candidates`` merely projects the eligible, fully resolved assessments;
``--explain`` renders the same assessments. Each registered verb routes to its own candidate
domain: ``implement-issue``/``refine-issue`` assess issue targets here, ``resolve-blocker``
(:mod:`~little_loops.next_arena.blockers`) assesses issue roots and ``run-loop``
(:mod:`~little_loops.next_arena.loop_candidates`) assesses captured loop definitions, so no
verb acquires phantom cross-domain assessments. Nothing here reads the clock, cwd, environment,
files, git or the history DB: all evidence comes from the injected :class:`ProjectState`.

Ordering contract: assessments are returned in canonical verb order, then ``target_key``
ascending; rank within a verb is ``selection_score`` descending (scored candidates first),
then valid priority ascending (missing/invalid last), then ``target_key`` ascending. Utility is
never compared across verbs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from little_loops.next_arena.actions import (
    ActionSpec,
    ActionSpecError,
    action_fingerprint,
    render_slash,
    scan_scope_hash,
    slash_spec_for,
    spec_to_dict,
)
from little_loops.next_arena.axes import (
    AxisScore,
    aggregate_axes,
    axis_missing,
    compute_issue_axes,
    leverage_evidence,
    minimum_evidence_met,
    validate_score,
    waiver_true,
)
from little_loops.next_arena.graph import TERMINAL_STATUSES
from little_loops.next_arena.inputs import Diagnostic, is_formatted_from_state, sort_diagnostics
from little_loops.next_arena.registry import (
    CANONICAL_VERB_ORDER,
    ArenaSettings,
    get_verb,
    registered_verbs,
)
from little_loops.next_arena.state import (
    ProjectState,
    SourceRecord,
    downstream_leverage,
    identity_issues_for,
    unique_source,
)

if TYPE_CHECKING:
    from little_loops.next_arena.graph import Leverage

__all__ = [
    "IMPLEMENT_ACTION_KEYS",
    "alternates_for",
    "PASS",
    "FAIL",
    "MISSING",
    "Alternate",
    "Candidate",
    "CandidateAssessment",
    "GateResult",
    "RefineStep",
    "assess_candidates",
    "assessments_for_target",
    "candidates_from_assessments",
    "generate_candidates",
    "loop_target_key",
    "next_refine_step",
    "scan_target_key",
    "sprint_target_key",
    "target_key_for",
]

PASS = "pass"
FAIL = "fail"
MISSING = "missing"

#: Issue type prefix -> implement-issue ``action_key``.
IMPLEMENT_ACTION_KEYS: Mapping[str, str] = MappingProxyType(
    {"BUG": "manage-issue:fix", "FEAT": "manage-issue:implement", "ENH": "manage-issue:improve"}
)

#: Session Log commands the refinement adapter inspects (as legacy ``next-action`` does).
VERIFY_COMMAND = "/ll:verify-issues"
REFINE_COMMAND = "/ll:refine-issue"

_SHARED_GATES = frozenset({"source_identity", "lifecycle"})
_ACTIONABLE_STATUSES = frozenset({"open", "blocked"})
_LEGACY_STEP = {
    "format-issue": "NEEDS_FORMAT",
    "verify-issues": "NEEDS_VERIFY",
    "confidence-check": "NEEDS_SCORE",
    "refine-issue": "NEEDS_REFINE",
}


def target_key_for(issue_id: str) -> str:
    """Namespaced identity of an issue target (``issue:FEAT-123``)."""
    return f"issue:{issue_id}"


def loop_target_key(target: str) -> str:
    """Namespaced identity of a loop target (``loop:NAME``; *target* is the exact operand)."""
    return f"loop:{target}"


def sprint_target_key(name: str) -> str:
    """Namespaced identity of a sprint target (``sprint:NAME``; *name* is the file stem)."""
    return f"sprint:{name}"


def scan_target_key(focus_dirs: Sequence[str], exclude_patterns: Sequence[str]) -> str:
    """Namespaced identity of the scan target (``scan:SCOPE_HASH`` of the configured scope)."""
    return f"scan:{scan_scope_hash(focus_dirs, exclude_patterns)}"


# ----------------------------------------------------------------------------- records


@dataclass(frozen=True)
class GateResult:
    """One tri-state gate outcome.

    ``reason`` starts with a stable code (``"decision_unresolved: ..."``); everything after
    the first ``:`` is explanatory text. ``source`` names the evidence consulted.
    """

    status: str
    reason: str
    source: str | None

    @property
    def code(self) -> str:
        """The stable reason code (the text before the first ``:``)."""
        return self.reason.split(":", 1)[0]

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping."""
        return {"status": self.status, "reason": self.reason, "source": self.source}


@dataclass(frozen=True)
class Alternate:
    """Summary of another registered verb's assessment of the same target."""

    action_type: str
    eligible: bool
    action_key: str | None
    action_fingerprint: str | None
    display_command: str | None
    bucket_rank: int | None
    utility: float | None
    exclusion_reasons: tuple[str, ...]
    selection_reason: str
    #: Bounded blocker significance (``resolve-blocker`` alternates only; else ``None``).
    blocker: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping."""
        return {
            "action_type": self.action_type,
            "eligible": self.eligible,
            "action_key": self.action_key,
            "action_fingerprint": self.action_fingerprint,
            "display_command": self.display_command,
            "bucket_rank": self.bucket_rank,
            "utility": self.utility,
            "exclusion_reasons": list(self.exclusion_reasons),
            "selection_reason": self.selection_reason,
            "blocker": dict(self.blocker) if self.blocker is not None else None,
        }


def _alternate_from(item: CandidateAssessment | Candidate) -> Alternate:
    eligible = isinstance(item, Candidate) or item.eligible
    return Alternate(
        action_type=item.action_type,
        eligible=eligible,
        action_key=item.action_key,
        action_fingerprint=item.action_fingerprint,
        display_command=item.display_command,
        bucket_rank=item.bucket_rank,
        utility=item.utility,
        exclusion_reasons=() if isinstance(item, Candidate) else item.exclusion_reasons,
        selection_reason=item.selection_reason,
        blocker=item.evidence.get("blocker") if item.action_type == "resolve-blocker" else None,
    )


def _axes_dict(axes: Mapping[str, AxisScore]) -> dict[str, Any]:
    return {name: item.to_dict() for name, item in axes.items()}


def _gates_dict(gates: Mapping[str, GateResult]) -> dict[str, Any]:
    return {name: item.to_dict() for name, item in gates.items()}


def _spec_dict(spec: ActionSpec | None) -> dict[str, Any] | None:
    return None if spec is None else spec_to_dict(spec)


@dataclass(frozen=True)
class CandidateAssessment:
    """The full assessment of one ``(action_type, target)`` pair (eligible or not).

    Action identity (``action_key``, ``action_fingerprint``, ``action_spec``,
    ``display_command``) is ``None`` unless the pair is eligible and fully resolved; likewise
    ``utility``/``selection_score``/``bucket_rank`` are ``None`` for an ineligible pair.
    Eligible cold-start pairs have ``None`` utility/selection score but a fallback
    ``bucket_rank``. ``evidence`` is per-verb typed evidence (leverage, readiness, ...).
    """

    target: str
    target_key: str
    action_type: str
    action_key: str | None
    action_fingerprint: str | None
    action_spec: ActionSpec | None
    display_command: str | None
    eligible: bool
    exclusion_reasons: tuple[str, ...]
    axes: Mapping[str, AxisScore]
    gates: Mapping[str, GateResult]
    utility: float | None
    selection_score: float | None
    bucket_rank: int | None
    pressure: None
    selection_reason: str
    resolved_axes: int
    applicable_axes: int
    alternates: tuple[Alternate, ...]
    evidence: Mapping[str, Any]
    diagnostics: tuple[Diagnostic, ...]
    priority_int: int | None = field(default=None, repr=False)

    @property
    def coverage(self) -> str:
        """Display string ``"resolved/applicable"`` (reported, never multiplied)."""
        return f"{self.resolved_axes}/{self.applicable_axes}"

    @property
    def fully_resolved(self) -> bool:
        """Eligible with a complete, runnable action identity."""
        return (
            self.eligible
            and self.action_key is not None
            and self.action_fingerprint is not None
            and self.action_spec is not None
            and self.display_command is not None
        )

    @property
    def cold_start(self) -> bool:
        """Eligible but without numeric utility (fallback ordering)."""
        return self.eligible and self.utility is None

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-ready mapping (``None`` for every unresolved value)."""
        return {
            "target": self.target,
            "target_key": self.target_key,
            "action_type": self.action_type,
            "action_key": self.action_key,
            "action_fingerprint": self.action_fingerprint,
            "action_spec": _spec_dict(self.action_spec),
            "display_command": self.display_command,
            "eligible": self.eligible,
            "exclusion_reasons": list(self.exclusion_reasons),
            "axes": _axes_dict(self.axes),
            "gates": _gates_dict(self.gates),
            "utility": self.utility,
            "selection_score": self.selection_score,
            "bucket_rank": self.bucket_rank,
            "pressure": self.pressure,
            "selection_reason": self.selection_reason,
            "resolved_axes": self.resolved_axes,
            "applicable_axes": self.applicable_axes,
            "coverage": self.coverage,
            "alternates": [a.to_dict() for a in self.alternates],
            "evidence": dict(self.evidence),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


@dataclass(frozen=True)
class Candidate:
    """A runnable recommendation: projection of an eligible, fully resolved assessment.

    Construction enforces complete action identity and a bucket rank, so a ``Candidate``
    can never carry a null action.
    """

    action_type: str
    action_key: str
    action_fingerprint: str
    action_spec: ActionSpec
    target: str
    target_key: str
    display_command: str
    axes: Mapping[str, AxisScore]
    gates: Mapping[str, GateResult]
    utility: float | None
    selection_score: float | None
    bucket_rank: int
    pressure: None
    selection_reason: str
    resolved_axes: int
    applicable_axes: int
    alternates: tuple[Alternate, ...]
    evidence: Mapping[str, Any]
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        missing = [
            name
            for name in (
                "action_key",
                "action_fingerprint",
                "action_spec",
                "display_command",
                "bucket_rank",
            )
            if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(
                f"Candidate requires complete action identity; null fields: {', '.join(missing)}"
            )

    @property
    def coverage(self) -> str:
        """Display string ``"resolved/applicable"``."""
        return f"{self.resolved_axes}/{self.applicable_axes}"

    @classmethod
    def from_assessment(cls, item: CandidateAssessment) -> Candidate:
        """Project *item*; raises ``ValueError`` unless it is eligible and fully resolved."""
        if not item.fully_resolved:
            raise ValueError(f"{item.action_type} {item.target_key} is not a runnable candidate")
        assert item.action_key and item.action_fingerprint and item.action_spec
        assert item.display_command and item.bucket_rank is not None
        return cls(
            action_type=item.action_type,
            action_key=item.action_key,
            action_fingerprint=item.action_fingerprint,
            action_spec=item.action_spec,
            target=item.target,
            target_key=item.target_key,
            display_command=item.display_command,
            axes=item.axes,
            gates=item.gates,
            utility=item.utility,
            selection_score=item.selection_score,
            bucket_rank=item.bucket_rank,
            pressure=item.pressure,
            selection_reason=item.selection_reason,
            resolved_axes=item.resolved_axes,
            applicable_axes=item.applicable_axes,
            alternates=item.alternates,
            evidence=item.evidence,
            diagnostics=item.diagnostics,
        )

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-ready mapping (complete action identity, never null)."""
        return {
            "action_type": self.action_type,
            "action_key": self.action_key,
            "action_fingerprint": self.action_fingerprint,
            "action_spec": spec_to_dict(self.action_spec),
            "target": self.target,
            "target_key": self.target_key,
            "display_command": self.display_command,
            "axes": _axes_dict(self.axes),
            "gates": _gates_dict(self.gates),
            "utility": self.utility,
            "selection_score": self.selection_score,
            "bucket_rank": self.bucket_rank,
            "pressure": self.pressure,
            "selection_reason": self.selection_reason,
            "resolved_axes": self.resolved_axes,
            "applicable_axes": self.applicable_axes,
            "coverage": self.coverage,
            "alternates": [a.to_dict() for a in self.alternates],
            "evidence": dict(self.evidence),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


# --------------------------------------------------------------------- refinement adapter


@dataclass(frozen=True)
class RefineStep:
    """Outcome of the pure per-issue ``cmd_next_action`` adapter.

    ``action_key`` is the replacing action (``format-issue``, ``verify-issues``,
    ``confidence-check`` or ``refine-issue``) or ``None`` when no step applies (``reason``
    then says why: ``no_refinement_needed``, ``refine_cap_exhausted`` or ``threshold_invalid``).
    """

    action_key: str | None
    legacy_step: str | None
    reason: str
    capped: bool
    refine_count: int
    refine_cap: int
    formatted: bool
    verified: bool
    scores_valid: bool

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping."""
        return {
            "action_key": self.action_key,
            "legacy_step": self.legacy_step,
            "reason": self.reason,
            "capped": self.capped,
            "refine_count": self.refine_count,
            "refine_cap": self.refine_cap,
            "formatted": self.formatted,
            "verified": self.verified,
            "scores_valid": self.scores_valid,
        }


def next_refine_step(record: SourceRecord, state: ProjectState, refine_cap: int) -> RefineStep:
    """Reproduce ``cmd_next_action``'s ordered checks for one issue, purely.

    Order: format (captured policy via ``is_formatted_from_state``) -> verify (``/ll:verify-issues``
    in the Session Log) -> score (either score absent/invalid -> ``confidence-check``) ->
    refine (``/ll:refine-issue`` runs below *refine_cap* and a readiness shortfall). Two
    intentional differences from the legacy command: scores are validated strictly
    (``0..100`` integers; ``101`` requests a confidence check), and a valid outcome waiver
    removes the outcome shortfall. A capped refine produces no step (never a repeat).
    """
    formatted = is_formatted_from_state(record, state.formatting_policy)
    verified = VERIFY_COMMAND in record.session_commands
    count = record.session_command_counts.get(REFINE_COMMAND, 0)
    cs, _ = validate_score(record.confidence_score_raw)
    oc, _ = validate_score(record.outcome_confidence_raw)
    scores_valid = cs is not None and oc is not None

    def step(key: str | None, reason: str, *, capped: bool = False) -> RefineStep:
        return RefineStep(
            action_key=key,
            legacy_step=_LEGACY_STEP.get(key) if key else None,
            reason=reason,
            capped=capped,
            refine_count=count,
            refine_cap=refine_cap,
            formatted=formatted,
            verified=verified,
            scores_valid=scores_valid,
        )

    if not formatted:
        return step("format-issue", "needs_format")
    if not verified:
        return step("verify-issues", "needs_verify")
    if cs is None or oc is None:
        return step("confidence-check", "needs_score")
    ready_threshold = state.thresholds.readiness
    outcome_threshold = state.thresholds.outcome
    if ready_threshold is None or outcome_threshold is None:
        return step(None, "threshold_invalid")
    waived = waiver_true(record.outcome_gate_waived_raw)
    shortfall = cs < ready_threshold or (oc < outcome_threshold and not waived)
    if not shortfall:
        return step(None, "no_refinement_needed")
    if count >= refine_cap:
        return step(None, "refine_cap_exhausted", capped=True)
    return step("refine-issue", "needs_refine")


# ------------------------------------------------------------------------------- gates


def _gate(status: str, code: str, detail: str = "", source: str | None = None) -> GateResult:
    return GateResult(status, f"{code}: {detail}" if detail else code, source)


def _source_identity_gate(
    state: ProjectState, issue_id: str, record: SourceRecord | None
) -> GateResult:
    amb = state.identity.ambiguous.get(issue_id)
    if amb is not None:
        extra = f"; shared number {', '.join(amb.numbers)}" if amb.numbers else ""
        return _gate(
            FAIL,
            "ambiguous_issue_id",
            f"{issue_id} has multiple sources ({', '.join(amb.reasons)}{extra}): "
            + ", ".join(amb.paths),
            "identity_inventory",
        )
    if record is not None and record.rel_path in state.identity.unsupported:
        reason = state.identity.unsupported[record.rel_path].reason
        return _gate(
            FAIL,
            "unsupported_issue_filename",
            f"{record.rel_path} ({reason}); normalize the filename to P?-TYPE-NNN-slug.md",
            "identity_inventory",
        )
    return _gate(PASS, "unique_anchored_source", source="identity_inventory")


def _lifecycle_gate(record: SourceRecord, verb: str) -> tuple[GateResult, tuple[str, ...]]:
    codes: list[str] = []
    if record.is_epic:
        codes.append("epic_container")
    if record.lifecycle_status in TERMINAL_STATUSES:
        codes.append("terminal_status")
    elif record.lifecycle_status not in _ACTIONABLE_STATUSES:
        codes.append("status_not_actionable")
    if verb == "implement-issue" and not record.is_epic:
        if record.issue_type not in IMPLEMENT_ACTION_KEYS:
            codes.append("unsupported_issue_type")
    source = f"frontmatter:status ({record.status_provenance})"
    if codes:
        return _gate(FAIL, codes[0], f"status {record.lifecycle_status}", source), tuple(codes)
    return _gate(PASS, "actionable_leaf", f"status {record.lifecycle_status}", source), ()


def _prerequisites_gate(state: ProjectState, issue_id: str) -> tuple[GateResult, dict[str, Any]]:
    graph = state.graph
    unresolved = graph.unresolved_for(issue_id)
    cyclic = issue_id in graph.cyclic_ids
    satisfied = graph.prerequisites_satisfied(issue_id) and not cyclic
    evidence = {
        "satisfied": satisfied,
        "in_cycle": cyclic,
        "unresolved": [
            {
                "kind": p.kind,
                "prerequisite_id": p.prerequisite_id,
                "reason": p.reason,
                "status": p.status,
                "source_paths": list(p.source_paths),
            }
            for p in unresolved
        ],
    }
    if satisfied:
        return _gate(PASS, "prerequisites_satisfied", source="dependency_graph"), evidence
    parts = [
        f"{p.kind} {p.prerequisite_id or 'unanchored source'} ({p.reason}"
        + (f", status {p.status}" if p.status else "")
        + ")"
        for p in unresolved
    ]
    if cyclic:
        parts.append("dependency cycle")
    if not parts:
        parts.append("issue is not a known graph node")
    return _gate(FAIL, "prerequisites_unresolved", "; ".join(parts), "dependency_graph"), evidence


def _score_gate(
    label: str,
    field_name: str,
    raw: Any,
    threshold: int | None,
    waived: bool,
) -> GateResult:
    source = f"frontmatter:{field_name}"
    value, reason = validate_score(raw)
    if value is None:
        if reason == "absent":
            return _gate(MISSING, f"{label}_score_absent", field_name, source)
        return _gate(FAIL, f"{label}_score_invalid", f"{field_name} {reason}", source)
    if threshold is None:
        return _gate(MISSING, "threshold_invalid", f"{label} threshold", "commands.confidence_gate")
    if value >= threshold:
        return _gate(PASS, f"{label}_ok", f"{value} >= {threshold}", source)
    if waived:
        return _gate(
            PASS,
            f"{label}_waived",
            f"{value} < {threshold} but outcome_gate_waived is true",
            source,
        )
    return _gate(FAIL, f"{label}_below_threshold", f"{value} < {threshold}", source)


def _readiness_evidence(record: SourceRecord, state: ProjectState) -> dict[str, Any]:
    def side(raw: Any) -> dict[str, Any]:
        value, reason = validate_score(raw)
        return {"value": value, "status": reason}

    return {
        "readiness_score": side(record.confidence_score_raw),
        "outcome_score": side(record.outcome_confidence_raw),
        "readiness_threshold": state.thresholds.readiness,
        "outcome_threshold": state.thresholds.outcome,
        "outcome_gate_waived": waiver_true(record.outcome_gate_waived_raw),
        "confidence_gate_enabled": state.thresholds.enabled,
    }


# -------------------------------------------------------------------------- target context


@dataclass(frozen=True)
class _TargetContext:
    issue_id: str
    record: SourceRecord | None
    source_paths: tuple[str, ...]
    identity_diagnostics: tuple[Diagnostic, ...]
    leverage: Leverage
    results: Mapping[str, AxisScore]
    source_gate: GateResult
    priority_int: int | None


def _build_context(state: ProjectState, issue_id: str) -> _TargetContext:
    record = unique_source(state, issue_id)
    leverage = downstream_leverage(state, issue_id)
    if record is None:
        results: Mapping[str, AxisScore] = {
            axis: axis_missing("", "ambiguous_issue_id")
            for axis in (
                "priority",
                "outcome",
                "readiness_gap",
                "leverage",
                "effort",
                "staleness",
                "momentum",
            )
        }
    else:
        results = compute_issue_axes(
            record,
            leverage=leverage,
            as_of=state.as_of,
            readiness_threshold=state.thresholds.readiness,
            outcome_threshold=state.thresholds.outcome,
        )
    return _TargetContext(
        issue_id=issue_id,
        record=record,
        source_paths=tuple(state.identity.node_paths.get(issue_id, ())),
        identity_diagnostics=identity_issues_for(state, issue_id),
        leverage=leverage,
        results=results,
        source_gate=_source_identity_gate(state, issue_id, record),
        priority_int=record.priority_int if record is not None else None,
    )


def _source_evidence(ctx: _TargetContext) -> dict[str, Any]:
    record = ctx.record
    if record is None:
        return {"paths": list(ctx.source_paths), "lifecycle_status": None, "priority": None}
    return {
        "paths": list(ctx.source_paths),
        "lifecycle_status": record.lifecycle_status,
        "status_provenance": record.status_provenance,
        "issue_type": record.issue_type,
        "priority": record.priority,
        "priority_source": record.priority_source,
        "priority_disagreement": list(record.priority_conflict)
        if record.priority_conflict
        else None,
    }


# ------------------------------------------------------------------------ per-verb assess


def _assess_one(
    state: ProjectState, settings: ArenaSettings, verb: str, ctx: _TargetContext
) -> CandidateAssessment:
    issue_id = ctx.issue_id
    record = ctx.record
    gates: dict[str, GateResult] = {"source_identity": ctx.source_gate}
    reasons: list[str] = []
    diagnostics: list[Diagnostic] = list(ctx.identity_diagnostics)
    evidence: dict[str, Any] = {
        "source": _source_evidence(ctx),
        "leverage": leverage_evidence(ctx.leverage),
    }
    action_key: str | None = None
    cycle_reasons: list[str] = []

    if ctx.source_gate.status != PASS:
        reasons.append(ctx.source_gate.code)
    if record is not None:
        diagnostics.extend(record.diagnostics)
        lifecycle, lifecycle_codes = _lifecycle_gate(record, verb)
        gates["lifecycle"] = lifecycle
        reasons.extend(lifecycle_codes)
        evidence["readiness"] = _readiness_evidence(record, state)
        if verb == "implement-issue":
            prereq_gate, dependencies = _prerequisites_gate(state, issue_id)
            evidence["dependencies"] = dependencies
            gates["prerequisites"] = prereq_gate
            if dependencies["in_cycle"]:
                cycle_reasons.append("dependency_cycle")
            gates["status_blocked"] = (
                _gate(
                    FAIL,
                    "status_blocked",
                    "frontmatter status is blocked; resolve the blocker before implementing",
                    "frontmatter:status",
                )
                if record.lifecycle_status == "blocked"
                else _gate(PASS, "status_not_blocked", source="frontmatter:status")
            )
            thresholds = state.thresholds
            waived = waiver_true(record.outcome_gate_waived_raw)
            gates["readiness"] = _score_gate(
                "readiness",
                "confidence_score",
                record.confidence_score_raw,
                thresholds.readiness,
                False,
            )
            gates["outcome"] = _score_gate(
                "outcome",
                "outcome_confidence",
                record.outcome_confidence_raw,
                thresholds.outcome,
                waived,
            )
            gates["decision"] = (
                _gate(
                    FAIL,
                    "decision_unresolved",
                    f"decision_needed is true; resolve it with /ll:decide-issue {issue_id}",
                    "frontmatter:decision_needed",
                )
                if record.decision_needed
                else _gate(PASS, "no_pending_decision", source="frontmatter:decision_needed")
            )
            action_key = IMPLEMENT_ACTION_KEYS.get(record.issue_type or "")
        else:
            step = next_refine_step(record, state, settings.refine_cap)
            evidence["refinement"] = step.to_dict()
            if step.action_key is not None:
                gates["refinement"] = _gate(
                    PASS,
                    "refinement_needed",
                    f"{step.action_key} ({step.legacy_step})",
                    "next_action_checks",
                )
                action_key = step.action_key
            elif step.capped:
                gates["refinement"] = _gate(
                    FAIL,
                    "refine_cap_exhausted",
                    f"/ll:refine-issue ran {step.refine_count} of {step.refine_cap} times",
                    "session_log",
                )
                diagnostics.append(
                    Diagnostic(
                        "refine_cap_exhausted",
                        f"{issue_id}: /ll:refine-issue ran {step.refine_count} of "
                        f"{step.refine_cap} times; the step is not repeated",
                        (record.rel_path,),
                        issue_id,
                    )
                )
            elif step.reason == "threshold_invalid":
                gates["refinement"] = _gate(
                    MISSING, "threshold_invalid", "confidence_gate", "commands.confidence_gate"
                )
            else:
                gates["refinement"] = _gate(
                    FAIL,
                    "no_refinement_needed",
                    "formatted, verified, scored and at or above the thresholds",
                    "next_action_checks",
                )
        for name, gate in gates.items():
            if name not in _SHARED_GATES and gate.status != PASS:
                reasons.append(gate.code)
        reasons.extend(cycle_reasons)

    reasons_unique = tuple(dict.fromkeys(reasons))
    eligible = record is not None and not reasons_unique and action_key is not None

    spec: ActionSpec | None = None
    fingerprint: str | None = None
    display: str | None = None
    if eligible and action_key is not None:
        try:
            spec = slash_spec_for(action_key, issue_id, str(state.project_root))
            fingerprint = action_fingerprint(spec)
            display = render_slash(spec)
        except ActionSpecError as exc:
            eligible = False
            spec = fingerprint = display = None
            reasons_unique = (*reasons_unique, "unrepresentable_action")
            diagnostics.append(
                Diagnostic("unrepresentable_action", f"{issue_id}: {exc}", (), issue_id)
            )
    if not eligible:
        action_key = None

    aggregate = aggregate_axes(verb, settings.weights[verb], ctx.results)
    scoring: dict[str, Any] = {"mode": "unranked", "minimum_evidence": None}
    utility: float | None = None
    if eligible:
        enough = minimum_evidence_met(aggregate.axes)
        scoring = {"mode": "scored" if enough else "cold_start", "minimum_evidence": enough}
        utility = aggregate.utility if enough else None
    evidence["scoring"] = scoring

    if eligible:
        reason = "eligible; awaiting rank"
    else:
        reason = "Excluded: " + (", ".join(reasons_unique) or "no applicable action")
    return CandidateAssessment(
        target=issue_id,
        target_key=target_key_for(issue_id),
        action_type=verb,
        action_key=action_key,
        action_fingerprint=fingerprint,
        action_spec=spec,
        display_command=display,
        eligible=eligible,
        exclusion_reasons=reasons_unique if not eligible else (),
        axes=aggregate.axes,
        gates=MappingProxyType(gates),
        utility=utility,
        selection_score=utility,
        bucket_rank=None,
        pressure=None,
        selection_reason=reason,
        resolved_axes=aggregate.resolved_axes,
        applicable_axes=aggregate.applicable_axes,
        alternates=(),
        evidence=MappingProxyType(evidence),
        diagnostics=sort_diagnostics(diagnostics),
        priority_int=ctx.priority_int,
    )


# --------------------------------------------------------------------------- ranking


def _rank_key(item: CandidateAssessment) -> tuple[Any, ...]:
    priority = (0, item.priority_int) if item.priority_int is not None else (1, 0)
    if item.selection_score is not None:
        return (0, -item.selection_score, priority, item.target_key)
    return (1, 0.0, priority, item.target_key)


def _rank_verb(items: list[CandidateAssessment], verb: str) -> list[CandidateAssessment]:
    ranked_pool = sorted((i for i in items if i.fully_resolved), key=_rank_key)
    total = len(ranked_pool)
    ranks = {}
    for position, item in enumerate(ranked_pool, start=1):
        if item.selection_score is not None:
            why = f"utility {item.selection_score:.3f}, coverage {item.coverage}"
        elif get_verb(verb).evidence_only and "activity" in item.gates:
            why = (
                f"evidence-only (no scored axes, coverage {item.coverage}); "
                f"activity gate passed: {item.gates['activity'].reason}"
            )
        else:
            why = (
                f"cold start (insufficient scoring evidence, coverage {item.coverage}); "
                f"ordered by {get_verb(verb).cold_start_order}"
            )
        ranks[item.target_key] = replace(
            item,
            bucket_rank=position,
            selection_reason=f"Rank {position} of {total} eligible {verb} candidates: {why}",
        )
    return [ranks.get(i.target_key, i) for i in items]


def _assess_verb(
    state: ProjectState,
    settings: ArenaSettings,
    verb: str,
    contexts: Sequence[_TargetContext],
) -> list[CandidateAssessment]:
    """Route *verb* to its own candidate source (issue targets, issue roots, loops, sprints, scan)."""
    if verb in ("implement-issue", "refine-issue"):
        return [_assess_one(state, settings, verb, ctx) for ctx in contexts]
    if verb == "resolve-blocker":
        from little_loops.next_arena.blockers import assess_resolve_blockers

        return assess_resolve_blockers(state, settings=settings, contexts=contexts)
    if verb == "run-loop":
        from little_loops.next_arena.loop_candidates import assess_run_loops

        return assess_run_loops(state, settings=settings)
    if verb == "run-sprint":
        from little_loops.next_arena.sprint_candidates import assess_run_sprints

        return assess_run_sprints(state, settings=settings)
    if verb == "capture-issues":
        from little_loops.next_arena.scan_candidates import assess_capture_scope

        scan = assess_capture_scope(state, settings=settings)
        return [] if scan is None else [scan]
    raise KeyError(f"no generator is wired for registered verb {verb!r}")


# ---------------------------------------------------------------------------- public API


def assess_candidates(
    state: ProjectState, *, settings: ArenaSettings | None = None
) -> list[CandidateAssessment]:
    """Assess every discovered inventory target for every registered verb.

    Args:
        state: The captured snapshot (no live I/O happens here).
        settings: Resolved ``next.verbs`` settings; defaults to
            ``state.config.next.resolve_arena_settings()`` (raises ``NextConfigError`` on
            invalid consumed config -- the CLI maps that to exit 2).

    Returns:
        One :class:`CandidateAssessment` per ``(verb, target)`` in canonical verb order then
        ``target_key`` ascending. Ineligible targets (terminal, EPIC, ambiguous, unsupported,
        gate-failed, ...) are included with exclusion reasons and null action identity.
        Within-verb ranks, utility and coverage are computed once here for eligible, fully
        resolved assessments; alternates link each target's assessments across verbs.
    """
    resolved = settings if settings is not None else state.config.next.resolve_arena_settings()
    targets = sorted(state.identity.node_paths, key=target_key_for)
    contexts = [_build_context(state, issue_id) for issue_id in targets]
    by_verb: dict[str, list[CandidateAssessment]] = {}
    for verb in registered_verbs():
        assessed = _assess_verb(state, resolved, verb, contexts)
        by_verb[verb] = _rank_verb(assessed, verb)

    grouped: dict[str, list[CandidateAssessment]] = {}
    for verb in registered_verbs():
        for item in by_verb[verb]:
            grouped.setdefault(item.target_key, []).append(item)
    result: list[CandidateAssessment] = []
    for verb in registered_verbs():
        for item in by_verb[verb]:
            others = tuple(
                _alternate_from(o) for o in grouped[item.target_key] if o.action_type != verb
            )
            result.append(replace(item, alternates=others))
    return result


def assessments_for_target(
    assessments: Iterable[CandidateAssessment], target_key: str, action_type: str
) -> tuple[CandidateAssessment | None, tuple[CandidateAssessment, ...]]:
    """Return ``(assessment, alternates)`` for ``--explain VERB TARGET``.

    ``assessment`` is the named verb's assessment of *target_key* (``None`` when the target
    does not exist); ``alternates`` are the other registered verbs' full assessments for the
    same target in canonical verb order.
    """
    named: CandidateAssessment | None = None
    others: list[CandidateAssessment] = []
    for item in assessments:
        if item.target_key != target_key:
            continue
        if item.action_type == action_type:
            named = item
        else:
            others.append(item)
    others.sort(key=lambda a: CANONICAL_VERB_ORDER.index(a.action_type))
    return named, tuple(others)


def candidates_from_assessments(assessments: Iterable[CandidateAssessment]) -> list[Candidate]:
    """Project eligible, fully resolved assessments (canonical verb order, then ``bucket_rank``)."""
    projected = [Candidate.from_assessment(a) for a in assessments if a.fully_resolved]
    projected.sort(key=lambda c: (CANONICAL_VERB_ORDER.index(c.action_type), c.bucket_rank))
    return projected


def generate_candidates(
    state: ProjectState, *, settings: ArenaSettings | None = None
) -> list[Candidate]:
    """Project the eligible, fully resolved assessments of *state* into runnable candidates."""
    return candidates_from_assessments(assess_candidates(state, settings=settings))


def alternates_for(items: Sequence[CandidateAssessment | Candidate]) -> tuple[Alternate, ...]:
    """Alternates (canonical verb order) summarizing *items*."""
    ordered = sorted(items, key=lambda i: CANONICAL_VERB_ORDER.index(i.action_type))
    return tuple(_alternate_from(i) for i in ordered)
