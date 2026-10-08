"""Runnable-sprint generator for ``ll-next`` (FEAT-3713).

``assess_run_sprints`` assesses every discovered sprint definition against the captured
:class:`~little_loops.next_arena.state.ProjectState` sprint domain and offers the plain command
``ll-sprint run -- NAME``. It is pure: definitions (read once, hashed from the parsed bytes),
issue sources, the dependency graph, executor-state evidence and the sprint-history snapshot are
all immutable evidence collected earlier.

Because the plain command dispatches **every** declared member that is not exactly
``status: done|cancelled``, the offer is all-or-nothing and fail-closed:

* every declared member (terminal ones included) must resolve through the core's unique,
  anchored issue-source inventory (``ambiguous_issue_id``, ``unsupported_issue_filename``,
  ``missing_issue``, ``epic_member``); this precedes terminal filtering, so a "completed" member
  that the resolver would route to another file cannot be dropped;
* terminal removal must match the executor's exact predicate (``executor_membership_mismatch``)
  and relationship shapes must not hide ordering from it (``executor_dependency_mismatch``);
* every remaining member passes the core implementation gates (status, readiness, outcome or
  waiver, unresolved decision) -- not just the first wave -- and any prerequisite outside the
  remaining members must already be satisfied: waves are built over **only** the remaining
  members, never projected from global waves, which would invent completion of outside work;
* a sprint-state file or unfinished matching invocation is an ``active_state_unknown`` diagnostic,
  never a veto (no liveness signal exists).

Not modeled (disclosed, never vetoed): ``ll-sprint run``'s opt-in learning-test preflight and the
EPIC ``base_branch`` preflight can still abort a run after ``milestone:`` was written to the
member files.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from little_loops.next_arena.actions import (
    FINGERPRINT_SCOPE_V1,
    SPRINT_ACTION_KEY,
    ActionSpecError,
    SprintActionSpec,
    SprintMember,
    action_fingerprint,
    render_sprint,
)
from little_loops.next_arena.axes import (
    AxisScore,
    aggregate_axes,
    axis_missing,
    priority_axis,
    sprint_minimum_evidence_met,
    sprint_priority_axis,
    sprint_ready_share_axis,
    sprint_since_last_run_axis,
)
from little_loops.next_arena.candidates import (
    FAIL,
    PASS,
    CandidateAssessment,
    GateResult,
    _assess_one,
    _build_context,
    _gate,
    sprint_target_key,
)
from little_loops.next_arena.graph import TERMINAL_STATUSES, Prerequisite
from little_loops.next_arena.inputs import Diagnostic, sort_diagnostics
from little_loops.next_arena.registry import ArenaSettings
from little_loops.next_arena.sprint_history import (
    SprintHistoryEvidence,
    sprint_history_evidence,
)
from little_loops.next_arena.sprint_parity import (
    MembershipMismatch,
    OutsideBlocksIndex,
    ShapeFinding,
    dependency_shape_findings,
    membership_mismatch,
    outside_blocks_findings,
    outside_blocks_index,
)
from little_loops.next_arena.sprint_state import (
    STATE_FILENAME,
    SprintDefinition,
    SprintStateEvidence,
    sprint_subject,
)
from little_loops.next_arena.state import (
    ProjectState,
    SourceRecord,
    ambiguous_diagnostic,
    unique_source,
    unsupported_diagnostic,
)

__all__ = ["UNMODELED_PREFLIGHTS_NOTE", "VERB", "assess_run_sprints"]

VERB = "run-sprint"
#: Pre-dispatch gates of ``ll-sprint run`` that the arena does not model (disclosed, no veto).
UNMODELED_PREFLIGHTS_NOTE = (
    "ll-sprint run also has an opt-in learning-test preflight (learning_tests.enabled) and an "
    "EPIC base_branch preflight (parallel.epic_branches.enabled) that can abort a run after "
    "`milestone:` was written to every member's frontmatter; neither is modeled here."
)

# Member / sprint exclusion codes beyond the reused core gate codes.
MISSING_ISSUE = "missing_issue"
EPIC_MEMBER = "epic_member"
MEMBER_GATES_FAILED = "member_gates_failed"
NO_REMAINING_WORK = "no_remaining_work"
OUTSIDE_PREREQ = "outside_prerequisite_unresolved"
DEPENDENCY_CYCLE = "dependency_cycle"
MEMBERSHIP_MISMATCH = "executor_membership_mismatch"
DEPENDENCY_MISMATCH = "executor_dependency_mismatch"
_PREREQ_REASONS = frozenset({"prerequisites_unresolved", "dependency_cycle"})


@dataclass(frozen=True)
class _Member:
    """One distinct declared member with its resolved source (when the identity gate passes)."""

    issue_id: str
    record: SourceRecord | None
    code: str | None
    detail: str
    paths: tuple[str, ...]

    @property
    def terminal(self) -> bool:
        return self.record is not None and self.record.lifecycle_status in TERMINAL_STATUSES

    @property
    def status(self) -> str:
        return self.record.lifecycle_status if self.record is not None else "unknown"


def _resolve_member(state: ProjectState, issue_id: str) -> _Member:
    """Identity of one declared member via the core's inventory (before any terminal filter)."""
    ambiguous = state.identity.ambiguous.get(issue_id)
    if ambiguous is not None:
        extra = f"; shared number {', '.join(ambiguous.numbers)}" if ambiguous.numbers else ""
        return _Member(
            issue_id,
            None,
            "ambiguous_issue_id",
            f"{issue_id} has multiple sources ({', '.join(ambiguous.reasons)}{extra}): "
            + ", ".join(ambiguous.paths),
            ambiguous.paths,
        )
    paths = state.identity.node_paths.get(issue_id, ())
    if not paths:
        return _Member(
            issue_id, None, MISSING_ISSUE, f"{issue_id} has no issue file in the project", ()
        )
    record = unique_source(state, issue_id)
    if record is None:  # defensive: node without a unique source
        return _Member(issue_id, None, MISSING_ISSUE, f"{issue_id} has no unique source", paths)
    if record.rel_path in state.identity.unsupported:
        reason = state.identity.unsupported[record.rel_path].reason
        return _Member(
            issue_id,
            record,
            "unsupported_issue_filename",
            f"{record.rel_path} ({reason}); normalize the filename to P?-TYPE-NNN-slug.md",
            (record.rel_path,),
        )
    if record.is_epic:
        return _Member(
            issue_id,
            record,
            EPIC_MEMBER,
            f"{issue_id} is an EPIC container, not an implementable member",
            (record.rel_path,),
        )
    return _Member(issue_id, record, None, "", (record.rel_path,))


def _internal_prerequisites(
    state: ProjectState, issue_id: str, remaining: Sequence[str]
) -> tuple[list[Prerequisite], list[Prerequisite]]:
    """Split a member's unresolved prerequisites into ``(internal, outside)``."""
    inside = set(remaining)
    internal: list[Prerequisite] = []
    outside: list[Prerequisite] = []
    for prereq in state.graph.unresolved_for(issue_id):
        if prereq.prerequisite_id in inside and prereq.reason == "not_terminal":
            internal.append(prereq)
        else:
            outside.append(prereq)
    return internal, outside


def _prereq_text(owner: str, prereq: Prerequisite) -> str:
    who = prereq.prerequisite_id or "unanchored source"
    status = f", status {prereq.status}" if prereq.status else ""
    paths = f" [{', '.join(prereq.source_paths)}]" if prereq.source_paths else ""
    return f"{owner} {prereq.kind} {who} ({prereq.reason}{status}){paths}"


def _history_axis(history: SprintHistoryEvidence) -> AxisScore:
    raw = history.to_dict()
    if history.witness is None:
        return sprint_since_last_run_axis(None, raw=raw, missing_reason=history.missing_reason)
    return sprint_since_last_run_axis(history.witness.age_days, raw=raw, missing_reason=None)


@dataclass
class _Outcome:
    """Mutable accumulation for one definition's assessment."""

    gates: dict[str, GateResult]
    reasons: list[str]
    diagnostics: list[Diagnostic]
    evidence: dict[str, Any]

    def fail(self, name: str, code: str, detail: str, source: str) -> None:
        self.gates[name] = _gate(FAIL, code, detail, source)
        if code not in self.reasons:
            self.reasons.append(code)


def _state_diagnostics(
    state_evidence: SprintStateEvidence | None, name: str, history: SprintHistoryEvidence
) -> list[Diagnostic]:
    """``active_state_unknown`` notes: evidence of possible activity, never a veto."""
    out: list[Diagnostic] = []
    subject = sprint_subject(name)
    if state_evidence is not None and state_evidence.exists:
        owner = state_evidence.sprint_name
        if state_evidence.error:
            about = f"an unreadable state file ({state_evidence.error})"
        elif owner == name:
            about = "a state file for this sprint"
        else:
            about = f"a state file for sprint {owner!r}" if owner else "a state file"
        out.append(
            Diagnostic(
                "active_state_unknown",
                f"{name}: {state_evidence.path} exists ({about}); there is no liveness signal, "
                "so it neither proves nor excludes a running sprint. The plain command deletes "
                "any old state, including another sprint's, when it reaches fresh-start "
                f"initialization; use --resume (not recommended here) to keep {STATE_FILENAME}",
                (),
                subject,
            )
        )
    if history.unfinished:
        out.append(
            Diagnostic(
                "active_state_unknown",
                f"{name}: {history.unfinished} matching `ll-sprint run` invocation(s) have no "
                "recorded end; they may still be running or may have been interrupted",
                (),
                subject,
            )
        )
    return out


def assess_run_sprints(
    state: ProjectState, *, settings: ArenaSettings
) -> list[CandidateAssessment]:
    """Assess each discovered sprint definition for ``run-sprint`` (``target_key`` order).

    Returns ``[]`` when the sprint domain was not collected (``sprint_definitions is None``).
    The shared ``assess_candidates`` pass assigns within-verb ranks.
    """
    definitions = state.sprint_definitions
    if definitions is None:
        return []
    from little_loops.issue_parser import IssueParser

    parser = IssueParser(state.config)
    blocks_index = outside_blocks_index(state)
    ordered = sorted(definitions, key=lambda d: sprint_target_key(d.name))
    return [_assess_definition(state, settings, d, parser, blocks_index) for d in ordered]


def _assess_definition(
    state: ProjectState,
    settings: ArenaSettings,
    definition: SprintDefinition,
    parser: Any,
    blocks_index: OutsideBlocksIndex,
) -> CandidateAssessment:
    name = definition.name
    history = sprint_history_evidence(state.sprint_history, name, state.as_of)
    out = _Outcome(
        gates={},
        reasons=[],
        diagnostics=list(definition.diagnostics),
        evidence={},
    )
    sprint_ev: dict[str, Any] = {
        "name": name,
        "definition_source": definition.source,
        "definition_digest": definition.digest,
        "fingerprint_scope": FINGERPRINT_SCOPE_V1,
        "definition_path": str(definition.path),
        "digest_label": "sprint definition bytes",
        "declared_name": definition.declared_name,
        "description": definition.description,
        "created": definition.created_raw,
        "options": definition.options.to_dict(),
        "ignored_option_keys": list(definition.ignored_option_keys),
        "declared_members": list(definition.members),
        "normalized_repeats": list(definition.repeated),
        "history": history.to_dict(),
        "command_note": (
            "`ll-sprint run -- NAME` loads the definition current when it runs; the digest and "
            "members recorded here describe the offer as assessed and cannot freeze that later "
            "execution."
        ),
        "unmodeled_preflights": UNMODELED_PREFLIGHTS_NOTE,
        "concurrency": (
            "Recommendations cannot prevent concurrent duplicate sprint work; the sprint-state "
            "file and unfinished invocations are only evidence."
        ),
    }
    out.evidence["sprint"] = sprint_ev

    members: list[_Member] = []
    remaining_members: list[_Member] = []
    waves: list[list[str]] = []
    ready: list[str] = []
    member_priorities: list[AxisScore] = []

    if not definition.valid:
        out.fail(
            "definition",
            definition.exclusion or "invalid_definition",
            definition.exclusion_detail or "",
            "sprint_definition",
        )
    else:
        out.gates["definition"] = _gate(PASS, "valid_definition", source="sprint_definition")
        members = [_resolve_member(state, mid) for mid in definition.members]
        _check_members(state, settings, out, members)

    if definition.valid and not out.reasons:
        remaining_members = [m for m in members if not m.terminal]
        _check_executor_parity(state, out, parser, blocks_index, members, remaining_members)
        _check_remaining(state, settings, out, remaining_members)
        if not out.reasons:
            waves, ready = _member_waves(state, out, remaining_members)
        member_priorities = [
            priority_axis(m.record.priority_int, m.record.priority, m.record.priority_source)
            for m in remaining_members
            if m.record is not None
        ]

    eligible = definition.valid and not out.reasons
    sprint_ev["members"] = [
        {
            "issue_id": m.issue_id,
            "status": m.status,
            "paths": list(m.paths),
            "problem": m.code,
            "detail": m.detail or None,
        }
        for m in members
    ]
    sprint_ev["remaining"] = [m.issue_id for m in remaining_members]
    sprint_ev["terminal_removed"] = [m.issue_id for m in members if m.terminal]
    sprint_ev["waves"] = waves
    sprint_ev["ready_now"] = ready

    spec: SprintActionSpec | None = None
    fingerprint: str | None = None
    display: str | None = None
    if eligible and definition.source and definition.digest:
        try:
            spec = SprintActionSpec(
                target=name,
                definition_source=definition.source,
                definition_digest=definition.digest,
                fingerprint_scope=FINGERPRINT_SCOPE_V1,
                working_directory=str(state.project_root),
                members=tuple(SprintMember(m.issue_id, m.status) for m in members),
            )
            fingerprint = action_fingerprint(spec)
            display = render_sprint(spec)
        except ActionSpecError as exc:
            eligible = False
            out.reasons.append("unrepresentable_action")
            out.diagnostics.append(
                Diagnostic("unrepresentable_action", f"{name}: {exc}", (), sprint_subject(name))
            )
    elif eligible:
        eligible = False
        out.reasons.append("definition_source_outside_project")

    if eligible:
        out.diagnostics.extend(_state_diagnostics(state.sprint_state, name, history))
        axes_in = {
            "ready_share": sprint_ready_share_axis(len(ready), len(remaining_members)),
            "priority": sprint_priority_axis(member_priorities),
            "since_last_run": _history_axis(history),
        }
    else:
        reason = "definition_invalid" if not definition.valid else "sprint_excluded"
        axes_in = {
            axis: axis_missing("", reason, source="sprint_definition")
            for axis in ("ready_share", "priority", "since_last_run")
        }
    aggregate = aggregate_axes(VERB, settings.weights[VERB], axes_in)
    scoring: dict[str, Any] = {"mode": "unranked", "minimum_evidence": None}
    utility: float | None = None
    if eligible:
        enough = sprint_minimum_evidence_met(aggregate.axes)
        scoring = {"mode": "scored" if enough else "cold_start", "minimum_evidence": enough}
        utility = aggregate.utility if enough else None
    out.evidence["scoring"] = scoring
    out.evidence["state"] = (
        {
            "path": state.sprint_state.path,
            "exists": state.sprint_state.exists,
            "sprint_name": state.sprint_state.sprint_name,
            "completed_issues": list(state.sprint_state.completed_issues),
            "error": state.sprint_state.error,
        }
        if state.sprint_state is not None
        else None
    )

    reasons = tuple(dict.fromkeys(out.reasons))
    selection_reason = (
        "eligible; awaiting rank"
        if eligible
        else "Excluded: " + (", ".join(reasons) or "no applicable action")
    )
    return CandidateAssessment(
        target=name,
        target_key=sprint_target_key(name),
        action_type=VERB,
        action_key=SPRINT_ACTION_KEY if eligible else None,
        action_fingerprint=fingerprint if eligible else None,
        action_spec=spec if eligible else None,
        display_command=display if eligible else None,
        eligible=eligible,
        exclusion_reasons=reasons if not eligible else (),
        axes=aggregate.axes,
        gates=MappingProxyType(out.gates),
        utility=utility,
        selection_score=utility,
        bucket_rank=None,
        pressure=None,
        selection_reason=selection_reason,
        resolved_axes=aggregate.resolved_axes,
        applicable_axes=aggregate.applicable_axes,
        alternates=(),
        evidence=MappingProxyType(out.evidence),
        diagnostics=sort_diagnostics(out.diagnostics),
        priority_int=None,
    )


# ------------------------------------------------------------------------------ the gates


def _check_members(
    state: ProjectState, settings: ArenaSettings, out: _Outcome, members: Sequence[_Member]
) -> None:
    """Identity/existence of **every** declared member, before any terminal filtering."""
    bad = [m for m in members if m.code is not None]
    if not members:
        out.fail(
            "members", NO_REMAINING_WORK, "the definition declares no members", "sprint_definition"
        )
        return
    if not bad:
        out.gates["members"] = _gate(
            PASS, "members_resolved", f"{len(members)} distinct member(s)", "identity_inventory"
        )
        return
    for member in bad:
        if member.code == "ambiguous_issue_id" and member.issue_id in state.identity.ambiguous:
            out.diagnostics.append(ambiguous_diagnostic(state.identity.ambiguous[member.issue_id]))
        elif member.code == "unsupported_issue_filename" and member.record is not None:
            src = state.identity.unsupported.get(member.record.rel_path)
            if src is not None:
                out.diagnostics.append(unsupported_diagnostic(src))
    detail = "; ".join(f"{m.code}: {m.detail}" for m in bad)
    codes = list(dict.fromkeys(m.code for m in bad if m.code))
    out.fail("members", codes[0], detail, "identity_inventory")
    for code in codes[1:]:
        out.reasons.append(code)


def _check_executor_parity(
    state: ProjectState,
    out: _Outcome,
    parser: Any,
    blocks_index: OutsideBlocksIndex,
    members: Sequence[_Member],
    remaining: Sequence[_Member],
) -> None:
    mismatches: list[MembershipMismatch] = []
    for member in members:
        if member.terminal and member.record is not None:
            found = membership_mismatch(member.record)
            if found is not None:
                mismatches.append(found)
    if mismatches:
        out.fail(
            "executor_membership",
            MEMBERSHIP_MISMATCH,
            "; ".join(m.message() for m in mismatches),
            "executor_parity",
        )
        out.evidence["executor_membership_mismatches"] = [m.to_dict() for m in mismatches]
    else:
        out.gates["executor_membership"] = _gate(
            PASS, "terminal_removal_matches_executor", source="executor_parity"
        )

    remaining_ids = {m.issue_id for m in remaining}
    findings: list[ShapeFinding] = []
    for member in remaining:
        if member.record is not None:
            findings.extend(dependency_shape_findings(member.record, remaining_ids, parser))
    findings.extend(outside_blocks_findings(state, blocks_index, remaining_ids))
    if findings:
        out.fail(
            "executor_dependencies",
            DEPENDENCY_MISMATCH,
            "; ".join(f.message() for f in findings),
            "executor_parity",
        )
        out.evidence["executor_dependency_findings"] = [f.to_dict() for f in findings]
    else:
        out.gates["executor_dependencies"] = _gate(
            PASS, "relationship_shapes_match_executor", source="executor_parity"
        )


def _check_remaining(
    state: ProjectState, settings: ArenaSettings, out: _Outcome, remaining: Sequence[_Member]
) -> None:
    """Every remaining member's own gates, then outside prerequisites and cycles."""
    if not remaining:
        out.fail(
            "remaining_work",
            NO_REMAINING_WORK,
            "every declared member is already done or cancelled",
            "identity_inventory",
        )
        return
    out.gates["remaining_work"] = _gate(
        PASS, "remaining_work", f"{len(remaining)} remaining member(s)", "identity_inventory"
    )
    ids = [m.issue_id for m in remaining]
    member_failures: list[str] = []
    per_member: dict[str, dict[str, Any]] = {}
    for member in remaining:
        ctx = _build_context(state, member.issue_id)
        assessed = _assess_one(state, settings, "implement-issue", ctx)
        codes = [c for c in assessed.exclusion_reasons if c not in _PREREQ_REASONS]
        per_member[member.issue_id] = {
            "eligible_now": assessed.eligible,
            "failing": codes,
            "gates": {n: g.to_dict() for n, g in assessed.gates.items() if g.status != PASS},
        }
        for code in codes:
            member_failures.append(f"{member.issue_id}: {code}")
            if code not in out.reasons:
                out.reasons.append(code)
    out.evidence["member_assessments"] = per_member
    if member_failures:
        out.fail(
            "member_gates",
            MEMBER_GATES_FAILED,
            "; ".join(member_failures)
            + " (every remaining member must pass, not only the first wave)",
            "implement_gates",
        )
    else:
        out.gates["member_gates"] = _gate(
            PASS, "member_gates_passed", f"{len(ids)} member(s)", "implement_gates"
        )

    outside_text: list[str] = []
    cyclic = sorted(set(ids) & state.graph.cyclic_ids)
    for member in remaining:
        _internal, outside = _internal_prerequisites(state, member.issue_id, ids)
        for prereq in outside:
            outside_text.append(_prereq_text(member.issue_id, prereq))
            if prereq.reason == "ambiguous_issue_id" and "ambiguous_issue_id" not in out.reasons:
                out.reasons.append("ambiguous_issue_id")
    if outside_text:
        out.fail(
            "prerequisites",
            OUTSIDE_PREREQ,
            "; ".join(outside_text)
            + " (the executor drops outside edges, so a ready first wave cannot make a later "
            "externally blocked wave safe)",
            "dependency_graph",
        )
    if cyclic:
        out.fail(
            "dependency_cycle",
            DEPENDENCY_CYCLE,
            "remaining members are in a dependency cycle: " + ", ".join(cyclic),
            "dependency_graph",
        )
    if not outside_text and not cyclic:
        out.gates["prerequisites"] = _gate(
            PASS,
            "outside_prerequisites_satisfied",
            "all outside prerequisites are known, unique and done/cancelled",
            "dependency_graph",
        )


def _member_waves(
    state: ProjectState, out: _Outcome, remaining: Sequence[_Member]
) -> tuple[list[list[str]], list[str]]:
    """Sprint-local waves over **only** the remaining members; the ready set is wave 1.

    Built with the runtime's own ``DependencyGraph`` over the captured, core-normalized edges
    (the parity gates above already excluded every shape on which that differs from the
    executor's parsed view). Outside prerequisites are proven satisfied, so they are dropped
    exactly as the executor drops them -- global waves are never projected here.
    """
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.issue_parser import IssueInfo

    infos = []
    for member in remaining:
        record = member.record
        assert record is not None
        priority = record.priority if record.priority and record.priority.startswith("P") else "P5"
        infos.append(
            IssueInfo(
                path=Path(record.rel_path),
                issue_type=record.issue_type or "",
                priority=priority,
                issue_id=member.issue_id,
                title=record.title,
                blocked_by=list(record.blocked_by),
                blocks=list(record.blocks),
                depends_on=list(record.depends_on),
            )
        )
    graph = DependencyGraph.from_issues(infos, all_known_ids=set(state.identity.node_paths))
    try:
        waves = [[i.issue_id for i in wave] for wave in graph.get_execution_waves()]
    except ValueError as exc:
        out.fail("dependency_cycle", DEPENDENCY_CYCLE, str(exc), "dependency_graph")
        return [], []
    if not waves or not waves[0]:
        out.fail("first_wave", DEPENDENCY_CYCLE, "the first sprint-local wave is empty", "waves")
        return waves, []
    out.gates["first_wave"] = _gate(
        PASS, "nonempty_first_wave", f"wave 1: {', '.join(waves[0])}", "waves"
    )
    return waves, list(waves[0])
