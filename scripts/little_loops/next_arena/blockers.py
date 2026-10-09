"""Root-blocker generator for ``ll-next`` (FEAT-3769).

``resolve-blocker`` recommends the *action that moves a root blocker forward*: an actionable
non-EPIC issue whose own prerequisites are satisfied and that has at least one proven
reachable remaining ``open``/``blocked`` non-EPIC dependent. The action comes from the core's
unchanged adapters -- the ordered per-issue refinement steps first
(:func:`~little_loops.next_arena.candidates.next_refine_step`), otherwise the complete
implementation gates -- so this module defines no second meaning of "unready".

Fan-out is *affected downstream reachability*, not proof that completing the target makes
every descendant implementable. :func:`build_blocker_index` therefore builds, in a single
pass over the graph (never a full-project scan per root), the bounded direct-dependent
summaries: a direct dependent is *immediately unlocked* by a target only when its distinct
unresolved prerequisite set equals ``{target}`` with no unknown/ambiguous prerequisite and no
relevant cycle. Independent status/readiness/decision vetoes of a dependent are reported
beside, never folded into, that fact.

Pure: everything comes from the injected :class:`ProjectState`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from little_loops.next_arena.actions import (
    ActionSpec,
    ActionSpecError,
    action_fingerprint,
    render_slash,
    slash_spec_for,
)
from little_loops.next_arena.axes import (
    aggregate_axes,
    leverage_evidence,
    minimum_evidence_met,
    waiver_true,
)
from little_loops.next_arena.candidates import (
    FAIL,
    IMPLEMENT_ACTION_KEYS,
    PASS,
    CandidateAssessment,
    GateResult,
    _build_context,
    _gate,
    _lifecycle_gate,
    _prerequisites_gate,
    _readiness_evidence,
    _score_gate,
    _source_evidence,
    _TargetContext,
    next_refine_step,
    target_key_for,
)
from little_loops.next_arena.graph import LEVERAGE_COUNTED_STATUSES, OpCounter
from little_loops.next_arena.inputs import Diagnostic, sort_diagnostics
from little_loops.next_arena.registry import ArenaSettings
from little_loops.next_arena.state import ProjectState

__all__ = [
    "BLOCKER_SAMPLE_CAP",
    "BlockerIndex",
    "assess_resolve_blockers",
    "blocker_summary",
    "build_blocker_index",
]

VERB = "resolve-blocker"
#: Maximum IDs listed in any blocker sample (counts stay exact).
BLOCKER_SAMPLE_CAP = 5
_SHARED_GATES = frozenset({"source_identity", "lifecycle"})


@dataclass(frozen=True)
class BlockerIndex:
    """Per-prerequisite direct-dependent summaries built in one graph pass.

    All sequences are sorted. ``direct`` holds every distinct counted dependent that still
    waits on the key; ``immediate`` those whose unresolved prerequisite set is exactly the
    key; ``multi_blocked`` the remainder (other, unknown or anonymous prerequisites, or a
    cycle); ``vetoes`` maps an immediate dependent to its independent vetoes.
    """

    direct: Mapping[str, tuple[str, ...]]
    immediate: Mapping[str, tuple[str, ...]]
    multi_blocked: Mapping[str, tuple[str, ...]]
    ambiguous_dependents: Mapping[str, tuple[str, ...]]
    vetoes: Mapping[str, tuple[str, ...]]


def _independent_vetoes(state: ProjectState, issue_id: str) -> tuple[str, ...]:
    """Status/decision/readiness vetoes of dependent *issue_id*, apart from prerequisites."""
    record = state.sources_for(issue_id)
    if len(record) != 1:
        return ()
    rec = record[0]
    found: list[str] = []
    if rec.lifecycle_status == "blocked":
        found.append("status_blocked")
    if rec.decision_needed:
        found.append("decision_unresolved")
    thresholds = state.thresholds
    waived = waiver_true(rec.outcome_gate_waived_raw)
    for gate in (
        _score_gate(
            "readiness", "confidence_score", rec.confidence_score_raw, thresholds.readiness, False
        ),
        _score_gate(
            "outcome", "outcome_confidence", rec.outcome_confidence_raw, thresholds.outcome, waived
        ),
    ):
        if gate.status != PASS:
            found.append(gate.code)
    return tuple(found)


def build_blocker_index(state: ProjectState, counter: OpCounter | None = None) -> BlockerIndex:
    """Build the direct-dependent index in one pass over the graph's unresolved edges.

    Only counted dependents (unique, ``open``/``blocked``, non-EPIC) contribute. Duplicate
    declarations count once (the graph already stores prerequisite sets). *counter* ticks
    once per node and per unresolved edge, so tests can assert the pass is linear.
    """
    graph = state.graph
    direct: dict[str, list[str]] = defaultdict(list)
    immediate: dict[str, list[str]] = defaultdict(list)
    multi: dict[str, list[str]] = defaultdict(list)
    for node in graph.node_status:
        if counter is not None:
            counter.tick()
        if (
            graph.node_status[node] not in LEVERAGE_COUNTED_STATUSES
            or graph.node_types.get(node) == "EPIC"
        ):
            continue
        unresolved = graph.unresolved_for(node)
        if not unresolved:
            continue
        ids = {p.prerequisite_id for p in unresolved}
        known = {i for i in ids if i is not None}
        # Immediately unlocked: the distinct unresolved prerequisite set equals {target}
        # (no unknown/anonymous companion, no relevant cycle). Duplicates count once.
        exclusive = len(known) == 1 and None not in ids and node not in graph.cyclic_ids
        for prereq in sorted(known):
            if counter is not None:
                counter.tick()
            direct[prereq].append(node)
            if exclusive:
                immediate[prereq].append(node)
            else:
                multi[prereq].append(node)
    ambiguous_dependents: dict[str, list[str]] = defaultdict(list)
    for node in graph.ambiguous:
        for prereq in graph.blocked_by.get(node, ()) + graph.depends_on.get(node, ()):
            ambiguous_dependents[prereq].append(node)
    vetoes: dict[str, tuple[str, ...]] = {}
    for dependents in immediate.values():
        for node in dependents:
            if node not in vetoes:
                vetoes[node] = _independent_vetoes(state, node)
    return BlockerIndex(
        direct=MappingProxyType({k: tuple(sorted(v)) for k, v in direct.items()}),
        immediate=MappingProxyType({k: tuple(sorted(v)) for k, v in immediate.items()}),
        multi_blocked=MappingProxyType({k: tuple(sorted(v)) for k, v in multi.items()}),
        ambiguous_dependents=MappingProxyType(
            {k: tuple(sorted(set(v))) for k, v in ambiguous_dependents.items()}
        ),
        vetoes=MappingProxyType(vetoes),
    )


def _sample(items: Sequence[str]) -> list[str]:
    return list(items[:BLOCKER_SAMPLE_CAP])


def blocker_summary(
    index: BlockerIndex, issue_id: str, leverage: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Bounded blocker significance of *issue_id* (``None`` when nothing waits on it).

    ``leverage`` is :func:`~little_loops.next_arena.axes.leverage_evidence` output. The
    reachable block reports affected downstream work (possibly saturated); the direct block
    separates dependents this target would immediately unlock from multi-blocked ones.
    """
    direct = index.direct.get(issue_id, ())
    reachable_sample = leverage.get("sample") or []
    if not direct and not reachable_sample:
        return None
    immediate = index.immediate.get(issue_id, ())
    implementable = [d for d in immediate if not index.vetoes.get(d)]
    vetoed = [{"id": d, "vetoes": list(index.vetoes[d])} for d in immediate if index.vetoes.get(d)]
    multi = index.multi_blocked.get(issue_id, ())
    return {
        "reachable": {
            "status": leverage.get("status"),
            "count": leverage.get("count"),
            "count_lower_bound": leverage.get("count_lower_bound"),
            "saturated": leverage.get("saturated"),
            "display": leverage.get("display"),
            "sample": list(reachable_sample)[:BLOCKER_SAMPLE_CAP],
        },
        "direct_dependents": {"count": len(direct), "sample": _sample(direct)},
        "immediately_unlocked": {
            "count": len(immediate),
            "sample": _sample(immediate),
            "implementable_count": len(implementable),
            "implementable_sample": _sample(implementable),
            "vetoed_count": len(vetoed),
            "vetoed_sample": vetoed[:BLOCKER_SAMPLE_CAP],
        },
        "multi_blocked": {"count": len(multi), "sample": _sample(multi)},
        "ambiguous_dependents": {
            "count": len(index.ambiguous_dependents.get(issue_id, ())),
            "sample": _sample(index.ambiguous_dependents.get(issue_id, ())),
        },
        "note": (
            "reachable is affected downstream work, not proof that completing this target "
            "immediately makes every descendant implementable"
        ),
    }


def _qualification_gate(ctx: _TargetContext, summary: dict[str, Any] | None) -> GateResult:
    lev = ctx.leverage
    if lev.sample:
        shown = leverage_evidence(lev).get("display") or str(len(lev.sample))
        return _gate(
            PASS,
            "reachable_dependents",
            f"{shown} reachable open/blocked non-EPIC dependent(s)",
            "dependency_graph",
        )
    if lev.status == "missing" and lev.missing_reason:
        why = lev.missing_reason
    elif lev.missing_ids:
        why = "dangling-only declarations"
    else:
        why = "zero, terminal-only or EPIC-only dependents"
    return _gate(FAIL, "no_downstream_dependents", why, "dependency_graph")


def _assess_root(
    state: ProjectState,
    settings: ArenaSettings,
    ctx: _TargetContext,
    index: BlockerIndex,
) -> CandidateAssessment:
    issue_id = ctx.issue_id
    record = ctx.record
    gates: dict[str, GateResult] = {"source_identity": ctx.source_gate}
    reasons: list[str] = []
    diagnostics: list[Diagnostic] = list(ctx.identity_diagnostics)
    leverage = leverage_evidence(ctx.leverage)
    summary = blocker_summary(index, issue_id, leverage)
    evidence: dict[str, Any] = {
        "source": _source_evidence(ctx),
        "leverage": leverage,
        "blocker": summary,
    }
    action_key: str | None = None

    if ctx.source_gate.status != PASS:
        reasons.append(ctx.source_gate.code)
    if record is not None:
        diagnostics.extend(record.diagnostics)
        lifecycle, lifecycle_codes = _lifecycle_gate(record, VERB)
        gates["lifecycle"] = lifecycle
        reasons.extend(lifecycle_codes)
        evidence["readiness"] = _readiness_evidence(record, state)
        prereq_gate, dependencies = _prerequisites_gate(state, issue_id)
        evidence["dependencies"] = dependencies
        gates["prerequisites"] = prereq_gate
        gates["root_qualification"] = _qualification_gate(ctx, summary)
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
            # Cap exhaustion never falls through to implementation.
            gates["refinement"] = _gate(
                FAIL,
                "refine_cap_exhausted",
                f"/ll:refine-issue ran {step.refine_count} of {step.refine_cap} times",
                "session_log",
            )
        else:
            gates["refinement"] = _gate(
                PASS,
                step.reason,
                "no refinement step applies; the implementation gates decide",
                "next_action_checks",
            )
            thresholds = state.thresholds
            waived = waiver_true(record.outcome_gate_waived_raw)
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
            if action_key is None:
                gates["implementation"] = _gate(
                    FAIL,
                    "unsupported_issue_type",
                    f"issue type {record.issue_type!r} has no implement action",
                    "issue_type",
                )
        for name, gate in gates.items():
            if name not in _SHARED_GATES and gate.status != PASS:
                reasons.append(gate.code)
        if dependencies["in_cycle"]:
            reasons.append("dependency_cycle")

    reasons_unique = tuple(dict.fromkeys(reasons))
    eligible = record is not None and not reasons_unique and action_key is not None

    spec: ActionSpec | None = None
    fingerprint: str | None = None
    display: str | None = None
    if eligible and action_key is not None:
        try:
            spec = slash_spec_for(action_key, issue_id, str(state.project_root))
            fingerprint = action_fingerprint(spec)
            display = render_slash(spec)  # type: ignore[arg-type]
        except ActionSpecError as exc:
            eligible = False
            spec = fingerprint = display = None
            reasons_unique = (*reasons_unique, "unrepresentable_action")
            diagnostics.append(
                Diagnostic("unrepresentable_action", f"{issue_id}: {exc}", (), issue_id)
            )
    if not eligible:
        action_key = None

    aggregate = aggregate_axes(VERB, settings.weights[VERB], ctx.results)
    scoring: dict[str, Any] = {"mode": "unranked", "minimum_evidence": None}
    utility: float | None = None
    if eligible:
        enough = minimum_evidence_met(aggregate.axes)
        scoring = {"mode": "scored" if enough else "cold_start", "minimum_evidence": enough}
        utility = aggregate.utility if enough else None
    evidence["scoring"] = scoring

    reason = (
        "eligible; awaiting rank"
        if eligible
        else "Excluded: " + (", ".join(reasons_unique) or "no applicable action")
    )
    return CandidateAssessment(
        target=issue_id,
        target_key=target_key_for(issue_id),
        action_type=VERB,
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


def assess_resolve_blockers(
    state: ProjectState,
    *,
    settings: ArenaSettings,
    contexts: Sequence[_TargetContext] | None = None,
    counter: OpCounter | None = None,
) -> list[CandidateAssessment]:
    """Assess every inventory target as a root-blocker candidate (``target_key`` order).

    Retains eligibility, gate and affected-dependent evidence for selection and ``--explain``.
    Within-verb ranks are assigned by the shared ``assess_candidates`` pass. *contexts* lets
    that pass share the per-target contexts it already built; omitted, they are built here.
    """
    if contexts is None:
        targets = sorted(state.identity.node_paths, key=target_key_for)
        contexts = [_build_context(state, issue_id) for issue_id in targets]
    index = build_blocker_index(state, counter)
    return [_assess_root(state, settings, ctx, index) for ctx in contexts]
