"""assess_candidates / generate_candidates: eligibility, gates, scoring, ranking (FEAT-3561 D)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from little_loops.next_arena.actions import (
    action_fingerprint,
    parse_slash,
    render_slash,
    slash_spec_for,
)
from little_loops.next_arena.candidates import (
    Candidate,
    CandidateAssessment,
    GateResult,
    assess_candidates,
    assessments_for_target,
    candidates_from_assessments,
    generate_candidates,
)
from little_loops.next_arena.registry import registered_verbs, verbs_in_domain
from tests.next_arena_candidates_support import (
    FORMAT_ENTRY,
    READY,
    VERIFY_ENTRY,
    get,
    issue,
    project,
    ready_issue,
)
from tests.next_arena_support import assert_resolver_parity

IMPL = "implement-issue"
REFINE = "refine-issue"
BLOCKER = "resolve-blocker"
#: Verbs whose candidates are issue targets; ``run-loop`` assesses loop definitions, which the
#: issue-only fixtures below never collect (``loop_definitions is None``).
ISSUE_VERBS = verbs_in_domain("issue")
GATE = {"commands": {"confidence_gate": {"readiness_threshold": 70, "outcome_threshold": 50}}}


def _one(tmp_path: Path, rel: str, text: str, **kw: Any) -> list[CandidateAssessment]:
    return assess_candidates(project(tmp_path, {rel: text}, **kw))


# ------------------------------------------------------------------- coverage of targets


def test_every_target_gets_an_assessment_per_registered_verb(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-a.md": ready_issue(),
        "bugs/P2-BUG-002-done.md": issue({"status": "done"}),
        "epics/P1-EPIC-003-e.md": issue({"status": "open"}),
        "features/P3-FEAT-004-x.md": issue({"status": "deferred"}),
        "enhancements/P3-ENH-005-y.md": issue({"status": "in_progress"}),
    }
    assessments = assess_candidates(project(tmp_path, files))
    assert len(assessments) == 5 * len(ISSUE_VERBS)
    # canonical verb order, then target_key
    verbs = [a.action_type for a in assessments]
    assert verbs == [v for v in ISSUE_VERBS for _ in range(5)]
    for verb in ISSUE_VERBS:
        keys = [a.target_key for a in assessments if a.action_type == verb]
        assert keys == sorted(keys)


@pytest.mark.parametrize(
    ("fm", "codes"),
    [
        ({"status": "done"}, {"terminal_status"}),
        ({"status": "cancelled"}, {"terminal_status"}),
        ({"completed_at": "2026-01-01"}, {"terminal_status"}),
        ({"status": "in_progress"}, {"status_not_actionable"}),
        ({"status": "deferred"}, {"status_not_actionable"}),
        ({"status": "bogus"}, {"status_not_actionable"}),
    ],
)
def test_non_actionable_status_has_assessment_but_no_action(
    tmp_path: Path, fm: dict[str, Any], codes: set[str]
) -> None:
    assessments = _one(tmp_path, "bugs/P2-BUG-001-a.md", ready_issue(fm))
    for verb in ISSUE_VERBS:
        item = get(assessments, verb, "BUG-001")
        assert item.eligible is False
        assert codes <= set(item.exclusion_reasons)
        assert item.gates["lifecycle"].status == "fail"
        assert (item.action_key, item.action_fingerprint, item.action_spec) == (None, None, None)
        assert item.display_command is None
        assert (item.utility, item.selection_score, item.bucket_rank) == (None, None, None)
        assert item.fully_resolved is False


def test_epic_container_is_excluded_from_every_issue_verb(tmp_path: Path) -> None:
    assessments = _one(tmp_path, "epics/P1-EPIC-010-e.md", ready_issue())
    for verb in ISSUE_VERBS:
        item = get(assessments, verb, "EPIC-010")
        assert "epic_container" in item.exclusion_reasons
        assert item.action_spec is None and item.bucket_rank is None


def test_terminal_epic_reports_both_reasons(tmp_path: Path) -> None:
    item = get(
        _one(tmp_path, "epics/P1-EPIC-010-e.md", issue({"status": "done"})), IMPL, "EPIC-010"
    )
    assert {"epic_container", "terminal_status"} <= set(item.exclusion_reasons)


# -------------------------------------------------------------------- implement-issue


@pytest.mark.parametrize(
    ("rel", "issue_id", "key", "words"),
    [
        ("bugs/P2-BUG-007-a.md", "BUG-007", "manage-issue:fix", ["bug", "fix"]),
        (
            "features/P2-FEAT-0042-a.md",
            "FEAT-0042",
            "manage-issue:implement",
            ["feature", "implement"],
        ),
        (
            "enhancements/P2-ENH-120-a.md",
            "ENH-120",
            "manage-issue:improve",
            ["enhancement", "improve"],
        ),
    ],
)
def test_ready_issue_emits_typed_manage_issue_action_with_exact_digits(
    tmp_path: Path, rel: str, issue_id: str, key: str, words: list[str]
) -> None:
    state = project(tmp_path, {rel: ready_issue()})
    item = get(assess_candidates(state), IMPL, issue_id)
    assert item.eligible and item.fully_resolved
    assert item.exclusion_reasons == ()
    assert item.action_key == key
    assert item.target == issue_id
    assert item.target_key == f"issue:{issue_id}"
    assert item.action_spec is not None
    assert list(item.action_spec.args) == [*words, issue_id]
    assert item.action_spec.working_directory == str(state.project_root)
    assert item.action_fingerprint == action_fingerprint(
        slash_spec_for(key, issue_id, "/elsewhere")
    )
    assert item.display_command == f"/ll:manage-issue {' '.join(words)} {issue_id}"
    assert parse_slash(item.display_command) == ("manage-issue", (*words, issue_id))
    assert item.pressure is None


def test_working_directory_is_the_absolute_canonical_root(tmp_path: Path) -> None:
    state = project(tmp_path, {"bugs/P2-BUG-001-a.md": ready_issue()})
    item = get(assess_candidates(state), IMPL, "BUG-001")
    assert item.action_spec is not None
    cwd = Path(item.action_spec.working_directory)
    assert cwd.is_absolute() and cwd == tmp_path.resolve()


def test_emitted_operands_match_the_real_resolver(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-a.md": ready_issue(),
        "features/P2-FEAT-002-b.md": ready_issue({"id": "FEAT-099"}),  # stale frontmatter id
        "enhancements/P3-ENH-003-c.md": ready_issue(),
        "enhancements/P3-ENH-004-d.md": issue({**READY, "status": "done"}),
    }
    state = project(tmp_path, files)
    assessments = assess_candidates(state)
    resolved = [a for a in assessments if a.fully_resolved]
    assert {a.action_type for a in resolved} == {IMPL, REFINE}  # unformatted -> refine too
    assert {a.target for a in resolved} == {"BUG-001", "FEAT-002", "ENH-003"}
    for item in resolved:
        assert item.action_spec is not None
        assert item.action_spec.args[-1] == item.target
        assert_resolver_parity(state, item.target)


def test_blocked_status_vetoes_implementation_but_keeps_refinement(tmp_path: Path) -> None:
    text = ready_issue({"status": "blocked"})
    assessments = _one(tmp_path, "bugs/P2-BUG-001-a.md", text)
    impl = get(assessments, IMPL, "BUG-001")
    assert impl.gates["status_blocked"].status == "fail"
    assert "status_blocked" in impl.exclusion_reasons
    assert impl.eligible is False
    # not formatted/verified under the real templates -> a genuine refine step remains
    refine = get(assessments, REFINE, "BUG-001")
    assert refine.eligible and refine.action_key == "format-issue"


def test_blocked_status_without_unresolved_edge_is_still_vetoed(tmp_path: Path) -> None:
    impl = get(
        _one(tmp_path, "bugs/P2-BUG-001-a.md", ready_issue({"status": "blocked"})), IMPL, "BUG-001"
    )
    assert impl.gates["prerequisites"].status == "pass"
    assert impl.gates["status_blocked"].status == "fail"


# ------------------------------------------------------------------------- readiness gate


def _gates(tmp_path: Path, fm: dict[str, Any], **kw: Any) -> CandidateAssessment:
    text = issue(fm)
    return get(_one(tmp_path, "bugs/P2-BUG-001-a.md", text, **kw), IMPL, "BUG-001")


@pytest.mark.parametrize(
    ("fm", "readiness", "outcome", "eligible"),
    [
        ({"confidence_score": 85, "outcome_confidence": 65}, "pass", "pass", True),
        ({"confidence_score": 84, "outcome_confidence": 65}, "fail", "pass", False),
        ({"confidence_score": 85, "outcome_confidence": 64}, "pass", "fail", False),
        ({"confidence_score": 100, "outcome_confidence": 100}, "pass", "pass", True),
        ({"confidence_score": 0, "outcome_confidence": 0}, "fail", "fail", False),
        ({"confidence_score": "90", "outcome_confidence": "70"}, "pass", "pass", True),
    ],
)
def test_default_threshold_boundaries(
    tmp_path: Path, fm: dict[str, Any], readiness: str, outcome: str, eligible: bool
) -> None:
    item = _gates(tmp_path, fm)
    assert (item.gates["readiness"].status, item.gates["outcome"].status) == (readiness, outcome)
    assert item.eligible is eligible


def test_absent_scores_are_missing_gates_not_zero(tmp_path: Path) -> None:
    item = _gates(tmp_path, {})
    assert item.gates["readiness"].status == "missing"
    assert item.gates["outcome"].status == "missing"
    assert item.gates["readiness"].code == "readiness_score_absent"
    assert {"readiness_score_absent", "outcome_score_absent"} <= set(item.exclusion_reasons)
    assert item.eligible is False


def test_zero_score_is_a_failing_gate_but_a_present_axis(tmp_path: Path) -> None:
    zero = _gates(tmp_path, {"confidence_score": 0, "outcome_confidence": 0})
    assert zero.gates["readiness"].status == "fail"
    assert zero.axes["outcome"].score == pytest.approx(0.2)
    assert zero.axes["outcome"].missing_reason is None
    absent = _gates(tmp_path / "x", {})
    assert absent.axes["outcome"].score is None
    assert absent.axes["outcome"].missing_reason == "outcome_confidence_absent"


@pytest.mark.parametrize(
    "bad", [101, "101", -1, "-5", 85.5, "85.5", "true", "nan", "+90", "ninety", "1e2"]
)
def test_invalid_score_never_passes_the_gate_or_becomes_an_axis(tmp_path: Path, bad: Any) -> None:
    item = _gates(tmp_path, {"confidence_score": bad, "outcome_confidence": bad})
    assert item.gates["readiness"].status == "fail"
    assert item.gates["readiness"].code == "readiness_score_invalid"
    assert item.gates["outcome"].status == "fail"
    assert item.axes["outcome"].score is None
    assert item.axes["outcome"].missing_reason.startswith("outcome_confidence_invalid")  # type: ignore[union-attr]
    assert item.eligible is False


def test_threshold_overrides_come_from_commands_confidence_gate(tmp_path: Path) -> None:
    fm = {"confidence_score": 72, "outcome_confidence": 55}
    assert _gates(tmp_path / "default", fm).eligible is False
    overridden = _gates(tmp_path / "override", fm, config=GATE)
    assert overridden.eligible is True
    assert overridden.evidence["readiness"]["readiness_threshold"] == 70
    assert overridden.evidence["readiness"]["outcome_threshold"] == 50
    stricter = {"commands": {"confidence_gate": {"readiness_threshold": 95}}}
    assert _gates(tmp_path / "strict", {**READY}, config=stricter).eligible is False


def test_disabled_confidence_gate_does_not_make_unassessed_issue_ready(tmp_path: Path) -> None:
    config = {"commands": {"confidence_gate": {"enabled": False}}}
    item = _gates(tmp_path, {}, config=config)
    assert item.eligible is False
    assert item.gates["readiness"].status == "missing"
    on = _gates(
        tmp_path / "on",
        {"confidence_score": 50},
        config={"commands": {"confidence_gate": {"enabled": True}}},
    )
    assert on.gates["readiness"].status == "fail"


@pytest.mark.parametrize(
    ("waiver", "outcome_status"),
    [
        (True, "pass"),
        ("true", "pass"),
        ("TRUE", "pass"),
        ("yes", "fail"),
        (1, "fail"),
        (False, "fail"),
    ],
)
def test_outcome_waiver_is_bool_true_or_string_true_only(
    tmp_path: Path, waiver: Any, outcome_status: str
) -> None:
    fm = {"confidence_score": 90, "outcome_confidence": 40, "outcome_gate_waived": waiver}
    item = _gates(tmp_path, fm)
    assert item.gates["outcome"].status == outcome_status
    assert item.eligible is (outcome_status == "pass")
    if outcome_status == "pass":
        assert item.gates["outcome"].code == "outcome_waived"


def test_waiver_does_not_excuse_a_missing_or_invalid_outcome_score(tmp_path: Path) -> None:
    missing = _gates(tmp_path / "a", {"confidence_score": 90, "outcome_gate_waived": True})
    assert missing.gates["outcome"].status == "missing"
    invalid = _gates(
        tmp_path / "b",
        {"confidence_score": 90, "outcome_confidence": 101, "outcome_gate_waived": True},
    )
    assert invalid.gates["outcome"].status == "fail"
    assert invalid.eligible is False


def test_waiver_never_waives_readiness(tmp_path: Path) -> None:
    item = _gates(
        tmp_path, {"confidence_score": 50, "outcome_confidence": 99, "outcome_gate_waived": True}
    )
    assert item.gates["readiness"].status == "fail"
    assert item.eligible is False


# -------------------------------------------------------------------------- decision gate


def test_decision_needed_true_vetoes_implementation_and_explains_remedy(tmp_path: Path) -> None:
    for value in (True, "true", "TRUE"):
        item = _gates(tmp_path / str(value), {**READY, "decision_needed": value})
        gate = item.gates["decision"]
        assert gate.status == "fail"
        assert gate.code == "decision_unresolved"
        assert "/ll:decide-issue BUG-001" in gate.reason
        assert "decision_unresolved" in item.exclusion_reasons
        assert item.action_spec is None and item.display_command is None


@pytest.mark.parametrize("value", [False, "false", "yes", 1, "1", "maybe"])
def test_other_decision_values_do_not_arm_the_gate(tmp_path: Path, value: Any) -> None:
    item = _gates(tmp_path, {**READY, "decision_needed": value})
    assert item.gates["decision"].status == "pass"
    assert item.eligible is True


def test_absent_decision_flag_does_not_veto(tmp_path: Path) -> None:
    assert _gates(tmp_path, dict(READY)).gates["decision"].status == "pass"


def test_decision_needed_keeps_a_genuine_refine_action_only(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-a.md": ready_issue({"decision_needed": True}),  # unformatted -> format
        "bugs/P2-BUG-002-b.md": issue(
            {**READY, "decision_needed": True},
            sessions=[FORMAT_ENTRY, VERIFY_ENTRY],  # nothing left to refine
        ),
    }
    assessments = assess_candidates(project(tmp_path, files))
    needs = get(assessments, REFINE, "BUG-001")
    assert needs.eligible and needs.action_key == "format-issue"
    assert get(assessments, IMPL, "BUG-001").eligible is False
    quiet = get(assessments, REFINE, "BUG-002")
    assert quiet.eligible is False
    assert quiet.action_spec is None  # no fabricated refinement action
    assert "no_refinement_needed" in quiet.exclusion_reasons
    assert get(assessments, IMPL, "BUG-002").gates["decision"].status == "fail"


# ------------------------------------------------------------------------ prerequisites


def _deps(tmp_path: Path, files: dict[str, str]) -> list[CandidateAssessment]:
    return assess_candidates(project(tmp_path, files))


def test_blocked_by_open_issue_fails_until_the_blocker_is_terminal(tmp_path: Path) -> None:
    open_blocker = _deps(
        tmp_path / "a",
        {
            "bugs/P2-BUG-001-a.md": ready_issue({"blocked_by": ["BUG-002"]}),
            "bugs/P2-BUG-002-b.md": issue({"status": "open"}),
        },
    )
    item = get(open_blocker, IMPL, "BUG-001")
    assert item.gates["prerequisites"].status == "fail"
    assert "BUG-002" in item.gates["prerequisites"].reason
    assert item.evidence["dependencies"]["unresolved"][0]["prerequisite_id"] == "BUG-002"
    for status in ("done", "cancelled"):
        resolved = _deps(
            tmp_path / status,
            {
                "bugs/P2-BUG-001-a.md": ready_issue({"blocked_by": ["BUG-002"]}),
                "bugs/P2-BUG-002-b.md": issue({"status": status}),
            },
        )
        assert get(resolved, IMPL, "BUG-001").eligible is True


@pytest.mark.parametrize("blocker_status", ["deferred", "in_progress", "blocked", "bogus"])
def test_nonterminal_prerequisites_fail_closed(tmp_path: Path, blocker_status: str) -> None:
    files = {
        "bugs/P2-BUG-001-a.md": ready_issue({"depends_on": ["BUG-002"]}),
        "bugs/P2-BUG-002-b.md": issue({"status": blocker_status}),
    }
    assert get(_deps(tmp_path, files), IMPL, "BUG-001").gates["prerequisites"].status == "fail"


def test_unknown_and_external_dependency_ids_fail_closed(tmp_path: Path) -> None:
    for field in ("blocked_by", "depends_on"):
        files = {"bugs/P2-BUG-001-a.md": ready_issue({field: ["BUG-404"]})}
        item = get(_deps(tmp_path / field, files), IMPL, "BUG-001")
        assert item.gates["prerequisites"].status == "fail"
        assert "unknown_issue" in item.gates["prerequisites"].reason


def test_depends_on_must_be_satisfied(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-a.md": ready_issue({"depends_on": ["BUG-002"]}),
        "bugs/P2-BUG-002-b.md": issue({"status": "open"}),
    }
    item = get(_deps(tmp_path / "open", files), IMPL, "BUG-001")
    assert item.gates["prerequisites"].status == "fail"
    files["bugs/P2-BUG-002-b.md"] = issue({"status": "done"})
    assert get(_deps(tmp_path / "done", files), IMPL, "BUG-001").eligible is True


def test_one_sided_blocks_declaration_blocks_the_named_target(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-a.md": ready_issue(),
        "bugs/P2-BUG-002-b.md": issue({"status": "open", "blocks": ["BUG-001"]}),
    }
    item = get(_deps(tmp_path / "open", files), IMPL, "BUG-001")
    assert item.gates["prerequisites"].status == "fail"
    assert item.evidence["dependencies"]["unresolved"][0]["kind"] == "blocks"
    files["bugs/P2-BUG-002-b.md"] = issue({"status": "done", "blocks": ["BUG-001"]})
    assert get(_deps(tmp_path / "done", files), IMPL, "BUG-001").eligible is True


def test_dependency_cycle_fails_with_diagnostic_and_no_invented_root(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-a.md": ready_issue({"blocked_by": ["BUG-002"]}),
        "bugs/P2-BUG-002-b.md": ready_issue({"blocked_by": ["BUG-001"]}),
    }
    state = project(tmp_path, files)
    assessments = assess_candidates(state)
    for issue_id in ("BUG-001", "BUG-002"):
        item = get(assessments, IMPL, issue_id)
        assert item.eligible is False
        assert {"prerequisites_unresolved", "dependency_cycle"} <= set(item.exclusion_reasons)
        assert item.evidence["dependencies"]["in_cycle"] is True
    assert any(d.code == "dependency_cycle" for d in state.diagnostics)


def test_refinement_is_not_blocked_by_unmet_prerequisites(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-a.md": ready_issue({"blocked_by": ["BUG-404"]}),
    }
    item = get(_deps(tmp_path, files), REFINE, "BUG-001")
    assert item.eligible is True  # unformatted -> format-issue
    assert "prerequisites" not in item.gates


# ------------------------------------------------------------------ identity exclusions


def test_duplicate_full_id_is_explainable_without_an_action(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-first.md": ready_issue(),
        "bugs/P2-BUG-001-second.md": ready_issue(),
        "bugs/P2-BUG-002-ok.md": ready_issue(),
    }
    assessments = assess_candidates(project(tmp_path, files))
    for verb in ISSUE_VERBS:
        dup = get(assessments, verb, "BUG-001")
        assert dup.eligible is False
        assert "ambiguous_issue_id" in dup.exclusion_reasons
        assert dup.gates["source_identity"].status == "fail"
        reason = dup.gates["source_identity"].reason
        assert ".issues/bugs/P2-BUG-001-first.md" in reason
        assert ".issues/bugs/P2-BUG-001-second.md" in reason
        assert dup.display_command is None and dup.action_spec is None
        assert all(a.missing_reason == "ambiguous_issue_id" for a in dup.axes.values())
        assert any(d.code == "ambiguous_issue_id" for d in dup.diagnostics)
    assert get(assessments, IMPL, "BUG-002").eligible is True


def test_shared_number_makes_every_affected_issue_ambiguous(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-005-a.md": ready_issue(),
        "features/P2-FEAT-005-b.md": ready_issue({"id": "FEAT-005"}),
        "bugs/P2-BUG-006-c.md": ready_issue(),
    }
    assessments = assess_candidates(project(tmp_path, files))
    for issue_id in ("BUG-005", "FEAT-005"):
        item = get(assessments, IMPL, issue_id)
        assert "ambiguous_issue_id" in item.exclusion_reasons
        assert "005" in item.gates["source_identity"].reason
    assert get(assessments, IMPL, "BUG-006").eligible is True


def test_active_terminal_collision_never_satisfies_an_edge(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-live.md": ready_issue({"blocked_by": ["BUG-002"]}),
        "bugs/P2-BUG-002-open.md": issue({"status": "open"}),
        "completed/P2-BUG-002-old.md": issue({"status": "done"}),
    }
    for order in (list(files), list(reversed(files))):
        state = project(tmp_path / ("fwd" if order == list(files) else "rev"), files, order=order)
        item = get(assess_candidates(state), IMPL, "BUG-001")
        assert item.eligible is False
        assert "ambiguous_issue_id" in item.gates["prerequisites"].reason


def test_unnormalized_filename_is_evidence_only_even_beside_a_canonical_source(
    tmp_path: Path,
) -> None:
    files = {
        "bugs/P3-001-old.md": ready_issue(),
        "features/P3-FEAT-001-new.md": ready_issue(),
    }
    assessments = assess_candidates(project(tmp_path, files))
    old = get(assessments, IMPL, "BUG-001")
    assert old.eligible is False
    assert "unsupported_issue_filename" in old.exclusion_reasons
    assert old.display_command is None
    assert any(d.code == "unsupported_issue_filename" for d in old.diagnostics)
    assert get(assessments, IMPL, "FEAT-001").eligible is True


def test_numberless_source_owns_no_target_but_blocks_named_target(tmp_path: Path) -> None:
    files = {
        "bugs/notes.md": issue({"status": "open", "blocks": ["BUG-002"]}),
        "bugs/P2-BUG-002-a.md": ready_issue(),
        "bugs/P2-BUG-003-b.md": ready_issue(),
    }
    state = project(tmp_path, files)
    assessments = assess_candidates(state)
    assert {a.target for a in assessments} == {"BUG-002", "BUG-003"}
    blocked = get(assessments, IMPL, "BUG-002")
    assert blocked.gates["prerequisites"].status == "fail"
    assert get(assessments, IMPL, "BUG-003").eligible is True
    assert any(d.code == "unsupported_issue_filename" for d in state.diagnostics)


def test_known_terminal_numberless_source_creates_no_blocker(tmp_path: Path) -> None:
    files = {
        "bugs/notes.md": issue({"status": "done", "blocks": ["BUG-002"]}),
        "bugs/P2-BUG-002-a.md": ready_issue(),
    }
    assert get(_deps(tmp_path, files), IMPL, "BUG-002").eligible is True


def test_canonical_filename_in_legacy_directory_is_eligible(tmp_path: Path) -> None:
    files = {"completed/P2-BUG-001-a.md": ready_issue({"status": "open"})}
    state = project(tmp_path, files)
    item = get(assess_candidates(state), IMPL, "BUG-001")
    assert item.eligible is True
    assert_resolver_parity(state, "BUG-001")


def test_reopened_issue_with_stale_completed_at_stays_actionable_and_unresolved(
    tmp_path: Path,
) -> None:
    files = {
        "bugs/P2-BUG-001-dep.md": ready_issue({"blocked_by": ["BUG-002"]}),
        "bugs/P2-BUG-002-reopened.md": ready_issue(
            {"status": "open", "completed_at": "2026-01-01"}
        ),
    }
    assessments = assess_candidates(project(tmp_path, files))
    assert get(assessments, IMPL, "BUG-002").eligible is True
    assert get(assessments, IMPL, "BUG-001").eligible is False


# ------------------------------------------------------------------ scoring & ranking


def _scored(tmp_path: Path, files: dict[str, str], **kw: Any) -> list[CandidateAssessment]:
    return [a for a in assess_candidates(project(tmp_path, files, **kw)) if a.action_type == IMPL]


def test_utility_ranks_within_a_verb_by_selection_score(tmp_path: Path) -> None:
    files = {
        "bugs/P4-BUG-001-low.md": ready_issue(),
        "bugs/P0-BUG-002-high.md": ready_issue(),
        "bugs/P2-BUG-003-mid.md": ready_issue(),
    }
    ranked = sorted(
        (a for a in _scored(tmp_path, files) if a.eligible), key=lambda a: a.bucket_rank or 0
    )
    assert [a.target for a in ranked] == ["BUG-002", "BUG-003", "BUG-001"]
    assert [a.bucket_rank for a in ranked] == [1, 2, 3]
    for item in ranked:
        assert item.utility is not None and item.selection_score == item.utility
        assert 0 < item.utility <= 1
    assert "Rank 1 of 3" in ranked[0].selection_reason


def test_ties_break_by_priority_then_target_key(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-010-b.md": ready_issue(),
        "bugs/P2-BUG-002-a.md": ready_issue(),
        "bugs/P2-BUG-003-c.md": ready_issue(),
    }
    by_rank = sorted(_scored(tmp_path, files), key=lambda a: a.bucket_rank or 0)
    assert [a.target for a in by_rank] == ["BUG-002", "BUG-003", "BUG-010"]  # key asc


def test_zero_dependent_leaf_and_p5_are_ranked_not_vetoed(tmp_path: Path) -> None:
    item = _scored(tmp_path, {"bugs/P5-BUG-001-a.md": ready_issue()})[0]
    assert item.eligible and item.utility is not None
    assert item.axes["leverage"].score == pytest.approx(0.5)
    assert item.axes["leverage"].missing_reason is None
    assert item.axes["priority"].score == pytest.approx(0.2)
    assert item.utility > 0.3


def test_axes_follow_canonical_order_and_effective_weights_renormalize(tmp_path: Path) -> None:
    text = ready_issue(effort=None)  # no effort, no session log -> two missing axes
    item = _scored(tmp_path, {"bugs/P2-BUG-001-a.md": text})[0]
    assert tuple(item.axes) == ("priority", "outcome", "leverage", "effort", "momentum")
    assert item.axes["effort"].score is None
    assert item.axes["momentum"].score is None
    assert item.axes["effort"].effective_weight == 0.0
    assert sum(a.effective_weight for a in item.axes.values()) == pytest.approx(1.0)
    assert (item.resolved_axes, item.applicable_axes, item.coverage) == (3, 5, "3/5")


def test_leverage_counts_downstream_open_dependents(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-root.md": ready_issue(),
        "bugs/P2-BUG-002-a.md": issue({"blocked_by": ["BUG-001"]}),
        "bugs/P2-BUG-003-b.md": issue({"depends_on": ["BUG-001"]}),
    }
    root = get(assess_candidates(project(tmp_path, files)), IMPL, "BUG-001")
    assert root.evidence["leverage"]["count"] == 2
    assert root.axes["leverage"].score is not None and root.axes["leverage"].score > 0.5


def test_leverage_saturation_is_reported_in_evidence(tmp_path: Path) -> None:
    files = {"bugs/P2-BUG-001-root.md": ready_issue()}
    for n in range(2, 14):
        files[f"bugs/P3-BUG-{n:03d}-d.md"] = issue({"blocked_by": ["BUG-001"]})
    root = get(assess_candidates(project(tmp_path, files)), IMPL, "BUG-001")
    lev = root.evidence["leverage"]
    assert (lev["saturated"], lev["count"], lev["count_lower_bound"]) == (True, None, 10)
    assert lev["display"] == "≥10"
    assert root.axes["leverage"].score == pytest.approx(1.0)


def test_weight_overrides_change_axes_and_ranks_only_through_settings(tmp_path: Path) -> None:
    config = {"next": {"verbs": {"implement-issue": {"weights": {"priority": 0.0}}}}}
    files = {"bugs/P5-BUG-001-a.md": ready_issue(), "bugs/P0-BUG-002-b.md": ready_issue()}
    items = _scored(tmp_path, files, config=config)
    for item in items:
        assert item.axes["priority"].configured_weight == 0.0
        assert item.axes["priority"].effective_weight == 0.0
        assert item.axes["priority"].score is not None  # still reported
        assert item.applicable_axes == 4


def test_min_evidence_missing_priority_is_cold_start_with_fallback_rank(tmp_path: Path) -> None:
    files = {
        "bugs/BUG-001-nopriority.md": ready_issue(),  # filename has no P prefix, no frontmatter
        "bugs/P2-BUG-002-scored.md": ready_issue(),
    }
    items = {a.target: a for a in _scored(tmp_path, files)}
    cold, scored = items["BUG-001"], items["BUG-002"]
    assert cold.eligible and cold.utility is None and cold.selection_score is None
    assert cold.axes["priority"].score is None
    assert scored.utility is not None and scored.bucket_rank == 1
    assert cold.bucket_rank == 2  # fallback rank after every scored candidate
    assert cold.cold_start and "cold start" in cold.selection_reason
    assert cold.evidence["scoring"]["mode"] == "cold_start"


def test_min_evidence_requires_a_positive_weight_non_priority_axis(tmp_path: Path) -> None:
    config = {
        "next": {
            "verbs": {
                "implement-issue": {
                    "weights": {"outcome": 0, "leverage": 0, "effort": 0, "momentum": 0}
                }
            }
        }
    }
    item = _scored(tmp_path, {"bugs/P2-BUG-001-a.md": ready_issue()}, config=config)[0]
    assert item.eligible and item.utility is None and item.selection_score is None
    assert item.bucket_rank == 1
    assert item.axes["priority"].score is not None  # priority metadata is valid


def test_cold_start_orders_by_priority_then_target_key(tmp_path: Path) -> None:
    config = {
        "next": {
            "verbs": {
                "implement-issue": {
                    "weights": {"outcome": 0, "leverage": 0, "effort": 0, "momentum": 0}
                }
            }
        }
    }
    files = {
        "bugs/P3-BUG-001-a.md": ready_issue(),
        "bugs/P1-BUG-009-b.md": ready_issue(),
        "bugs/P3-BUG-002-c.md": ready_issue(),
        "bugs/BUG-005-nop.md": ready_issue(),
    }
    ranked = sorted(_scored(tmp_path, files, config=config), key=lambda a: a.bucket_rank or 0)
    assert [a.target for a in ranked] == ["BUG-009", "BUG-001", "BUG-002", "BUG-005"]


def test_ineligible_assessments_are_never_ranked(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-ok.md": ready_issue(),
        "bugs/P0-BUG-002-gated.md": issue({"confidence_score": 10, "outcome_confidence": 10}),
    }
    gated = next(a for a in _scored(tmp_path, files) if a.target == "BUG-002")
    assert gated.eligible is False
    assert (gated.utility, gated.selection_score, gated.bucket_rank) == (None, None, None)
    assert gated.axes["priority"].score is not None  # axis evidence retained for explain
    assert gated.selection_reason.startswith("Excluded:")


# ---------------------------------------------------------------- projection / explain


def test_generate_candidates_projects_only_eligible_fully_resolved(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-ok.md": ready_issue(),
        "bugs/P2-BUG-002-gated.md": issue({"confidence_score": 10, "outcome_confidence": 10}),
        "bugs/P2-BUG-003-done.md": issue({"status": "done"}),
    }
    state = project(tmp_path, files)
    candidates = generate_candidates(state)
    assert all(isinstance(c, Candidate) for c in candidates)
    assessed = {(a.action_type, a.target) for a in assess_candidates(state) if a.fully_resolved}
    assert {(c.action_type, c.target) for c in candidates} == assessed
    for c in candidates:
        assert c.action_key and c.action_fingerprint and c.display_command and c.bucket_rank >= 1
    assert candidates == candidates_from_assessments(assess_candidates(state))


def test_candidate_requires_complete_action_identity(tmp_path: Path) -> None:
    state = project(tmp_path, {"bugs/P2-BUG-001-ok.md": ready_issue()})
    cand = generate_candidates(state)[0]
    fields = {f: getattr(cand, f) for f in cand.__dataclass_fields__}
    for name in (
        "action_key",
        "action_fingerprint",
        "action_spec",
        "display_command",
        "bucket_rank",
    ):
        with pytest.raises(ValueError, match=name):
            Candidate(**{**fields, name: None})
    gated = get(
        assess_candidates(project(tmp_path / "g", {"bugs/P2-BUG-001-a.md": issue()})),
        IMPL,
        "BUG-001",
    )
    with pytest.raises(ValueError, match="not a runnable candidate"):
        Candidate.from_assessment(gated)


def test_alternates_link_every_other_verb_for_the_same_target(tmp_path: Path) -> None:
    state = project(tmp_path, {"bugs/P2-BUG-001-a.md": ready_issue()})
    assessments = assess_candidates(state)
    impl, refine = get(assessments, IMPL, "BUG-001"), get(assessments, REFINE, "BUG-001")
    blocker = get(assessments, BLOCKER, "BUG-001")
    assert [a.action_type for a in impl.alternates] == [REFINE, BLOCKER]
    assert [a.action_type for a in refine.alternates] == [IMPL, BLOCKER]
    assert impl.alternates[0].action_key == refine.action_key == "format-issue"
    assert refine.alternates[0].action_key == impl.action_key
    named, others = assessments_for_target(assessments, "issue:BUG-001", REFINE)
    assert named is refine
    assert others == (impl, blocker)
    assert assessments_for_target(assessments, "issue:BUG-404", IMPL) == (None, ())


def test_each_target_is_assessed_once_even_for_mixed_status_inventory(tmp_path: Path) -> None:
    files = {f"bugs/P2-BUG-{n:03d}-a.md": ready_issue() for n in range(1, 8)}
    assessments = assess_candidates(project(tmp_path, files))
    pairs = [(a.action_type, a.target_key) for a in assessments]
    assert len(pairs) == len(set(pairs)) == 7 * len(ISSUE_VERBS)


# ------------------------------------------------------------------------ serialization


def test_to_dict_is_json_ready_complete_and_stable(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-ok.md": ready_issue(),
        "bugs/P2-BUG-002-gated.md": issue({"confidence_score": "x"}),
        "epics/P1-EPIC-003-e.md": issue(),
    }
    state = project(tmp_path, files)
    first = [a.to_dict() for a in assess_candidates(state)]
    second = [a.to_dict() for a in assess_candidates(state)]
    assert json.dumps(first, allow_nan=False, sort_keys=True) == json.dumps(
        second, allow_nan=False, sort_keys=True
    )
    expected_keys = [
        "target",
        "target_key",
        "action_type",
        "action_key",
        "action_fingerprint",
        "action_spec",
        "display_command",
        "eligible",
        "exclusion_reasons",
        "axes",
        "gates",
        "utility",
        "selection_score",
        "bucket_rank",
        "pressure",
        "selection_reason",
        "resolved_axes",
        "applicable_axes",
        "coverage",
        "alternates",
        "evidence",
        "diagnostics",
    ]
    for item in first:
        assert list(item) == expected_keys
    ok = next(d for d in first if d["target"] == "BUG-001" and d["action_type"] == IMPL)
    assert ok["action_spec"]["variant"] == "slash"
    assert ok["gates"]["readiness"] == {
        "status": "pass",
        "reason": "readiness_ok: 90 >= 85",
        "source": "frontmatter:confidence_score",
    }
    epic = next(d for d in first if d["target"] == "EPIC-003" and d["action_type"] == IMPL)
    assert epic["action_spec"] is None and epic["action_key"] is None
    assert epic["utility"] is None and epic["bucket_rank"] is None
    cand = generate_candidates(state)[0].to_dict()
    assert cand["action_spec"]["working_directory"] == str(state.project_root)
    assert cand["bucket_rank"] == 1
    assert "eligible" not in cand and "exclusion_reasons" not in cand
    json.dumps(cand, allow_nan=False)


def test_gate_result_code_and_dict() -> None:
    gate = GateResult("fail", "decision_unresolved: needs /ll:decide-issue X-1", "frontmatter")
    assert gate.code == "decision_unresolved"
    assert gate.to_dict()["status"] == "fail"
    assert GateResult("pass", "ok", None).code == "ok"


# --------------------------------------------------------------------------- purity


def test_assessment_makes_no_subprocess_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = project(tmp_path, {"bugs/P2-BUG-001-a.md": ready_issue()})

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("subprocess used during assessment")

    for name in ("run", "Popen", "check_output", "check_call", "call"):
        monkeypatch.setattr(subprocess, name, boom)
    assert assess_candidates(state)
    assert generate_candidates(state)


def test_assessment_performs_no_file_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = project(tmp_path, {"bugs/P2-BUG-001-a.md": ready_issue()})
    monkeypatch.chdir("/")
    (tmp_path / ".issues" / "bugs" / "P2-BUG-001-a.md").unlink()
    (tmp_path / ".ll").rename(tmp_path / ".ll-moved")
    items = assess_candidates(state)
    assert get(items, IMPL, "BUG-001").eligible is True


def test_missing_registered_verb_reaches_nothing_beyond_the_registry(tmp_path: Path) -> None:
    state = project(tmp_path, {"bugs/P2-BUG-001-a.md": ready_issue()})
    # run-loop assesses loop definitions, which this issue-only fixture does not collect.
    assert {a.action_type for a in assess_candidates(state)} == set(ISSUE_VERBS)
    # run-sprint/capture-issues likewise assess uncollected (None) sprint/scan domains.
    assert set(registered_verbs()) == set(ISSUE_VERBS) | {
        "run-loop",
        "run-sprint",
        "capture-issues",
    }
    assert (
        render_slash(slash_spec_for("refine-issue", "BUG-001", "/r")) == "/ll:refine-issue BUG-001"
    )
