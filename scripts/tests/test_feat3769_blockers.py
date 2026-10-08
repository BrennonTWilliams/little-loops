"""``resolve-blocker`` generator: root qualification, action precedence, dedup (FEAT-3769)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from little_loops.next_arena.blockers import (
    BLOCKER_SAMPLE_CAP,
    assess_resolve_blockers,
    build_blocker_index,
)
from little_loops.next_arena.candidates import (
    CandidateAssessment,
    assess_candidates,
    candidates_from_assessments,
)
from little_loops.next_arena.graph import OpCounter
from little_loops.next_arena.registry import ArenaSettings
from little_loops.next_arena.selection import bucket_order_for, select_candidates
from tests.next_arena_candidates_support import (
    FORMAT_ENTRY,
    VERIFY_ENTRY,
    get,
    issue,
    project,
    ready_issue,
)
from tests.next_arena_support import memory_state

BLOCKER = "resolve-blocker"
IMPL = "implement-issue"
REFINE = "refine-issue"
DONE = {"status": "done"}


def ready(fm: Mapping[str, Any] | None = None, **kw: Any) -> str:
    """A fully refined, implementable issue (formatted, verified, scored above thresholds)."""
    return ready_issue(fm, sessions=[FORMAT_ENTRY, VERIFY_ENTRY], **kw)


def feat(n: int, prio: int = 2) -> str:
    return f"features/P{prio}-FEAT-{n:03d}-x.md"


def blocker(items: list[CandidateAssessment], issue_id: str) -> CandidateAssessment:
    return get(items, BLOCKER, issue_id)


def summary(item: CandidateAssessment) -> dict[str, Any]:
    out = item.evidence["blocker"]
    assert out is not None
    return dict(out)


# --------------------------------------------------------------------------- qualification


def test_chain_only_the_root_qualifies_and_reachability_is_not_immediate_unlock(
    tmp_path: Path,
) -> None:
    files = {
        feat(1): ready(),
        feat(2): ready({"blocked_by": ["FEAT-001"]}),
        feat(3): ready({"blocked_by": ["FEAT-002"]}),
    }
    items = assess_candidates(project(tmp_path, files))
    root = blocker(items, "FEAT-001")
    assert root.eligible and root.action_key == "manage-issue:implement"
    assert root.display_command == "/ll:manage-issue feature implement FEAT-001"
    info = summary(root)
    assert info["reachable"]["count"] == 2
    assert info["direct_dependents"] == {"count": 1, "sample": ["FEAT-002"]}
    assert info["immediately_unlocked"]["sample"] == ["FEAT-002"]
    # FEAT-003 is reachable but waits on FEAT-002, so completing the root never unlocks it.
    assert "FEAT-003" not in info["immediately_unlocked"]["sample"]
    assert "reachable is affected downstream work" in info["note"]
    # Non-roots are explained exclusions, not invented roots.
    mid = blocker(items, "FEAT-002")
    assert not mid.eligible and "prerequisites_unresolved" in mid.exclusion_reasons
    assert blocker(items, "FEAT-003").eligible is False


def test_diamond_separates_reachability_from_immediate_unlock(tmp_path: Path) -> None:
    files = {
        feat(1): ready(),
        feat(2): ready({"blocked_by": ["FEAT-001"]}),
        feat(3): ready({"blocked_by": ["FEAT-001"]}),
        feat(4): ready({"blocked_by": ["FEAT-002", "FEAT-003"]}),
    }
    root = blocker(assess_candidates(project(tmp_path, files)), "FEAT-001")
    info = summary(root)
    assert info["reachable"]["count"] == 3
    assert info["direct_dependents"]["count"] == 2
    assert info["immediately_unlocked"]["sample"] == ["FEAT-002", "FEAT-003"]
    assert info["multi_blocked"]["count"] == 0  # FEAT-004 is not a direct dependent


def test_multi_blocked_direct_dependent_is_not_immediately_unlocked(tmp_path: Path) -> None:
    files = {
        feat(1): ready(),
        feat(2): ready(),
        feat(3): ready({"blocked_by": ["FEAT-001", "FEAT-002"]}),
        feat(4): ready({"blocked_by": ["FEAT-001"]}),
    }
    items = assess_candidates(project(tmp_path, files))
    info = summary(blocker(items, "FEAT-001"))
    assert info["direct_dependents"]["count"] == 2
    assert info["immediately_unlocked"]["sample"] == ["FEAT-004"]
    assert info["multi_blocked"]["sample"] == ["FEAT-003"]
    # Both roots qualify independently.
    assert blocker(items, "FEAT-002").eligible


def test_duplicate_declarations_count_once_and_depends_on_participates(tmp_path: Path) -> None:
    files = {
        feat(1): ready({"blocks": ["FEAT-002"]}),
        feat(2): ready({"blocked_by": ["FEAT-001"], "depends_on": ["FEAT-001"]}),
    }
    info = summary(blocker(assess_candidates(project(tmp_path, files)), "FEAT-001"))
    assert info["direct_dependents"]["count"] == 1
    assert info["immediately_unlocked"]["count"] == 1


def test_immediately_unlocked_dependent_keeps_its_independent_vetoes(tmp_path: Path) -> None:
    files = {
        feat(1): ready(),
        feat(2): ready({"blocked_by": ["FEAT-001"], "decision_needed": "true"}),
        feat(3): ready({"blocked_by": ["FEAT-001"]}),
    }
    info = summary(blocker(assess_candidates(project(tmp_path, files)), "FEAT-001"))
    unlocked = info["immediately_unlocked"]
    assert unlocked["count"] == 2
    assert unlocked["implementable_sample"] == ["FEAT-003"]
    assert unlocked["vetoed_sample"] == [{"id": "FEAT-002", "vetoes": ["decision_unresolved"]}]


@pytest.mark.parametrize(
    ("dependent", "label"),
    [
        (("done-dep", DONE), "terminal"),
        (("cancelled-dep", {"status": "cancelled"}), "cancelled"),
    ],
)
def test_terminal_only_dependents_do_not_qualify(
    tmp_path: Path, dependent: tuple[str, dict[str, str]], label: str
) -> None:
    files = {feat(1): ready(), feat(2): ready({"blocked_by": ["FEAT-001"], **dependent[1]})}
    item = blocker(assess_candidates(project(tmp_path, files)), "FEAT-001")
    assert not item.eligible, label
    assert "no_downstream_dependents" in item.exclusion_reasons


def test_zero_fan_out_epic_only_and_dangling_only_do_not_qualify(tmp_path: Path) -> None:
    files = {
        feat(1): ready(),  # zero fan-out
        feat(2): ready({"blocks": ["FEAT-999"]}),  # dangling-only declaration
        feat(3): ready(),
        "epics/P2-EPIC-004-e.md": issue({"blocked_by": ["FEAT-003"]}),  # EPIC-only dependent
    }
    items = assess_candidates(project(tmp_path, files))
    for issue_id in ("FEAT-001", "FEAT-002", "FEAT-003"):
        item = blocker(items, issue_id)
        assert not item.eligible, issue_id
        assert item.exclusion_reasons == ("no_downstream_dependents",), issue_id
        assert item.gates["root_qualification"].status == "fail"


def test_ambiguous_only_dependent_does_not_qualify_but_a_known_one_does(tmp_path: Path) -> None:
    ambiguous = {
        feat(1): ready(),
        "bugs/P2-BUG-002-a.md": ready({"blocked_by": ["FEAT-001"]}),
        "bugs/P3-BUG-002-b.md": ready({"blocked_by": ["FEAT-001"]}),
    }
    only = blocker(assess_candidates(project(tmp_path / "amb", ambiguous)), "FEAT-001")
    assert not only.eligible and "no_downstream_dependents" in only.exclusion_reasons
    mixed = {**ambiguous, "features/P2-FEAT-003-known.md": ready({"blocked_by": ["FEAT-001"]})}
    known = blocker(assess_candidates(project(tmp_path / "mix", mixed)), "FEAT-001")
    assert known.eligible
    assert summary(known)["direct_dependents"]["sample"] == ["FEAT-003"]
    assert summary(known)["ambiguous_dependents"]["count"] == 1


def test_ambiguous_prerequisite_cannot_make_a_blocker_look_root(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-a.md": ready(),
        "bugs/P3-BUG-001-b.md": ready(),
        feat(2): ready({"blocked_by": ["BUG-001"]}),
        feat(3): ready({"blocked_by": ["FEAT-002"]}),
    }
    items = assess_candidates(project(tmp_path, files))
    assert not blocker(items, "FEAT-002").eligible  # prerequisite is ambiguous
    assert "ambiguous_issue_id" in blocker(items, "BUG-001").exclusion_reasons


def test_dependency_cycle_yields_diagnostics_not_a_root(tmp_path: Path) -> None:
    files = {
        feat(1): ready({"blocked_by": ["FEAT-002"]}),
        feat(2): ready({"blocked_by": ["FEAT-001"]}),
        feat(3): ready({"blocked_by": ["FEAT-001"]}),
    }
    state = project(tmp_path, files)
    items = assess_candidates(state)
    for issue_id in ("FEAT-001", "FEAT-002"):
        item = blocker(items, issue_id)
        assert not item.eligible and "dependency_cycle" in item.exclusion_reasons
    assert any(d.code == "dependency_cycle" for d in state.diagnostics)


def test_epic_and_terminal_and_unsupported_are_excluded(tmp_path: Path) -> None:
    files = {
        "epics/P2-EPIC-001-e.md": issue(),
        feat(2): ready(DONE),
        feat(3): ready({"blocked_by": ["EPIC-001"]}),
        "features/notes.md": issue(),
    }
    items = assess_candidates(project(tmp_path, files))
    assert "epic_container" in blocker(items, "EPIC-001").exclusion_reasons
    assert "terminal_status" in blocker(items, "FEAT-002").exclusion_reasons


# -------------------------------------------------------------------------- action precedence


def _with_dependent(n: int, text: str) -> dict[str, str]:
    """Root FEAT-*n* plus one ready dependent (FEAT-*n*+50) so the root qualifies."""
    return {feat(n): text, feat(n + 50): ready({"blocked_by": [f"FEAT-{n:03d}"]})}


def test_refinement_adapter_wins_even_when_numeric_scores_pass(tmp_path: Path) -> None:
    # Scores pass the thresholds but the issue was never formatted/verified.
    files = _with_dependent(1, ready_issue())
    item = blocker(assess_candidates(project(tmp_path, files)), "FEAT-001")
    assert item.eligible and item.action_key == "format-issue"
    assert item.display_command == "/ll:format-issue FEAT-001"
    assert item.gates["refinement"].code == "refinement_needed"
    assert "readiness" not in item.gates  # implementation gates are not applied


def test_verify_then_score_steps_are_reused_unchanged(tmp_path: Path) -> None:
    formatted = ready_issue(sessions=[FORMAT_ENTRY])
    unscored = issue({}, sessions=[FORMAT_ENTRY, VERIFY_ENTRY])
    items = assess_candidates(
        project(tmp_path, {**_with_dependent(1, formatted), **_with_dependent(2, unscored)})
    )
    assert blocker(items, "FEAT-001").action_key == "verify-issues"
    assert blocker(items, "FEAT-002").action_key == "confidence-check"


def test_refine_step_applies_for_a_readiness_shortfall(tmp_path: Path) -> None:
    low = issue(
        {"confidence_score": 40, "outcome_confidence": 40}, sessions=[FORMAT_ENTRY, VERIFY_ENTRY]
    )
    item = blocker(assess_candidates(project(tmp_path, _with_dependent(1, low))), "FEAT-001")
    assert item.action_key == "refine-issue" and item.eligible


def test_cap_exhaustion_never_falls_through_to_implementation(tmp_path: Path) -> None:
    refined = [("/ll:refine-issue", f"2026-09-0{i}T10:00:00") for i in range(1, 6)]
    low = issue(
        {"confidence_score": 40, "outcome_confidence": 40},
        sessions=[FORMAT_ENTRY, VERIFY_ENTRY, *refined],
    )
    item = blocker(assess_candidates(project(tmp_path, _with_dependent(1, low))), "FEAT-001")
    assert not item.eligible
    assert item.exclusion_reasons == ("refine_cap_exhausted",)
    assert item.action_key is None and item.display_command is None
    assert "readiness" not in item.gates and "decision" not in item.gates


def test_implementation_gates_apply_when_no_refinement_step_is_needed(tmp_path: Path) -> None:
    items = assess_candidates(project(tmp_path, _with_dependent(1, ready())))
    item = blocker(items, "FEAT-001")
    assert item.action_key == "manage-issue:implement"
    assert [g for g in item.gates if g not in ("source_identity", "lifecycle")] == [
        "prerequisites",
        "root_qualification",
        "refinement",
        "status_blocked",
        "readiness",
        "outcome",
        "decision",
    ]
    assert item.gates["refinement"].code == "no_refinement_needed"


def test_true_decision_needed_vetoes_the_implementation_step(tmp_path: Path) -> None:
    item = blocker(
        assess_candidates(project(tmp_path, _with_dependent(1, ready({"decision_needed": True})))),
        "FEAT-001",
    )
    assert not item.eligible
    assert item.exclusion_reasons == ("decision_unresolved",)
    assert item.action_key is None  # no action is invented


def test_explicit_blocked_status_vetoes_implementation_but_keeps_a_needed_refinement(
    tmp_path: Path,
) -> None:
    blocked_ready = blocker(
        assess_candidates(
            project(tmp_path / "a", _with_dependent(1, ready({"status": "blocked"})))
        ),
        "FEAT-001",
    )
    assert not blocked_ready.eligible and "status_blocked" in blocked_ready.exclusion_reasons
    blocked_unrefined = blocker(
        assess_candidates(
            project(tmp_path / "b", _with_dependent(1, ready_issue({"status": "blocked"})))
        ),
        "FEAT-001",
    )
    assert blocked_unrefined.eligible and blocked_unrefined.action_key == "format-issue"


def test_missing_scores_with_a_refined_issue_route_to_the_score_step(tmp_path: Path) -> None:
    item = blocker(
        assess_candidates(
            project(tmp_path, _with_dependent(1, issue({}, sessions=[FORMAT_ENTRY, VERIFY_ENTRY])))
        ),
        "FEAT-001",
    )
    assert item.action_key == "confidence-check"


def test_epic_dependents_are_not_counted_but_bug_enh_roots_get_their_own_implement_action(
    tmp_path: Path,
) -> None:
    files = {
        "bugs/P1-BUG-001-a.md": ready(),
        "enhancements/P2-ENH-002-b.md": ready({"blocked_by": ["BUG-001"]}),
    }
    item = blocker(assess_candidates(project(tmp_path, files)), "BUG-001")
    assert item.action_key == "manage-issue:fix"
    assert item.display_command == "/ll:manage-issue bug fix BUG-001"


# ------------------------------------------------------------------ ranking, dedup and fill


def test_bucket_rank_follows_weighted_utility_not_fan_out_alone(tmp_path: Path) -> None:
    files = {
        # P0 root with one dependent vs P5 root with many dependents: utility decides.
        feat(1, prio=0): ready(),
        feat(2, prio=0): ready({"blocked_by": ["FEAT-001"]}),
        feat(3, prio=5): ready(),
        **{feat(n, prio=2): ready({"blocked_by": ["FEAT-003"]}) for n in range(10, 22)},
    }
    items = [
        a
        for a in assess_candidates(project(tmp_path, files))
        if a.action_type == BLOCKER and a.fully_resolved
    ]
    items.sort(key=lambda a: a.bucket_rank or 0)
    # The P5 root has far larger fan-out, yet the P0 root's utility ranks first.
    assert [a.target for a in items] == ["FEAT-001", "FEAT-003"]
    assert summary(items[1])["reachable"]["saturated"] is True
    scores = [a.selection_score for a in items]
    assert scores == sorted(scores, reverse=True)  # rank is the utility order


def test_bucket_is_scored_with_leverage_dominant_weight(tmp_path: Path) -> None:
    files = {
        feat(1): ready(),
        feat(2): ready({"blocked_by": ["FEAT-001"]}),
    }
    root = blocker(assess_candidates(project(tmp_path, files)), "FEAT-001")
    assert root.utility is not None and root.bucket_rank == 1
    weights = {name: axis.configured_weight for name, axis in root.axes.items()}
    assert weights == {
        "priority": 0.25,
        "leverage": 0.5,
        "effort": 0.15,
        "staleness": 0.05,
        "momentum": 0.05,
    }
    assert list(root.axes) == ["priority", "leverage", "effort", "staleness", "momentum"]


def test_selected_implement_target_keeps_a_blocker_alternate_instead_of_a_duplicate(
    tmp_path: Path,
) -> None:
    files = {
        feat(1, prio=0): ready(),
        feat(2): ready({"blocked_by": ["FEAT-001"]}),
        feat(3, prio=3): ready(),
        feat(4): ready({"blocked_by": ["FEAT-003"]}),
    }
    state = project(tmp_path, files)
    candidates = candidates_from_assessments(assess_candidates(state))
    chosen = select_candidates(candidates, top=None, bucket_order=bucket_order_for(None), caps={})
    targets = [c.target_key for c in chosen]
    assert len(targets) == len(set(targets))  # target dedup is unchanged
    by_verb = {c.action_type: c for c in chosen}
    implement = by_verb[IMPL]
    assert implement.target == "FEAT-001"
    alt = {a.action_type: a for a in implement.alternates}[BLOCKER]
    assert alt.eligible and alt.blocker is not None
    assert alt.blocker["direct_dependents"]["sample"] == ["FEAT-002"]
    # The blocker bucket continued past the duplicate to its next distinct target.
    assert by_verb[BLOCKER].target == "FEAT-003"
    # JSON and human output carry the bounded summary.
    assert implement.to_dict()["alternates"][-1]["blocker"]["direct_dependents"]["count"] == 1


def test_human_output_carries_the_bounded_blocker_summary_on_the_alternate(
    tmp_path: Path,
) -> None:
    from little_loops.next_arena.render import render_text

    files = {feat(1): ready(), feat(2): ready({"blocked_by": ["FEAT-001"]})}
    state = project(tmp_path, files)
    order = bucket_order_for(None)
    chosen = select_candidates(
        candidates_from_assessments(assess_candidates(state)), top=None, bucket_order=order, caps={}
    )
    text = render_text(project_root=state.project_root, recommendations=chosen, bucket_order=order)
    assert "resolve-blocker: /ll:manage-issue feature implement FEAT-001 [blocker: " in text
    assert "1 direct, 1 immediately unlocked]" in text


def test_blocker_bucket_exhausts_without_a_duplicate_when_every_root_is_taken(
    tmp_path: Path,
) -> None:
    files = {feat(1): ready(), feat(2): ready({"blocked_by": ["FEAT-001"]})}
    state = project(tmp_path, files)
    chosen = select_candidates(
        candidates_from_assessments(assess_candidates(state)),
        top=None,
        bucket_order=bucket_order_for(None),
        caps={},
    )
    assert [c.action_type for c in chosen if c.target == "FEAT-001"] == [IMPL]
    assert BLOCKER not in {c.action_type for c in chosen}
    assert chosen[0].alternates[-1].action_type == BLOCKER


def test_explicit_top_fill_keeps_dedup_and_caps(tmp_path: Path) -> None:
    files = {
        feat(1): ready(),
        feat(2): ready({"blocked_by": ["FEAT-001"]}),
        feat(3): ready(),
        feat(4): ready({"blocked_by": ["FEAT-003"]}),
    }
    state = project(tmp_path, files)
    chosen = select_candidates(
        candidates_from_assessments(assess_candidates(state)),
        top=6,
        bucket_order=bucket_order_for([BLOCKER]),
        caps={BLOCKER: 1},
    )
    assert [c.action_type for c in chosen] == [BLOCKER]


# ------------------------------------------------------------------------ serialization


def test_assessment_and_alternate_serialization_is_json_ready(tmp_path: Path) -> None:
    files = {feat(1): ready(), feat(2): ready({"blocked_by": ["FEAT-001"]})}
    items = assess_candidates(project(tmp_path, files))
    payload = json.dumps([a.to_dict() for a in items], allow_nan=False)
    assert '"blocker"' in payload
    root = blocker(items, "FEAT-001")
    other = next(a for a in get(items, IMPL, "FEAT-001").alternates if a.action_type == BLOCKER)
    assert other.blocker == root.evidence["blocker"]
    # Non-blocker alternates never carry a blocker summary.
    assert all(a.blocker is None for a in get(items, BLOCKER, "FEAT-001").alternates)


def test_samples_are_bounded(tmp_path: Path) -> None:
    files = {
        feat(1): ready(),
        **{feat(n): ready({"blocked_by": ["FEAT-001"]}) for n in range(2, 30)},
    }
    info = summary(blocker(assess_candidates(project(tmp_path, files)), "FEAT-001"))
    assert info["direct_dependents"]["count"] == 28
    assert len(info["direct_dependents"]["sample"]) == BLOCKER_SAMPLE_CAP
    assert info["reachable"]["saturated"] is True
    assert len(info["reachable"]["sample"]) <= BLOCKER_SAMPLE_CAP


# --------------------------------------------------------------------- one-pass structure


def _chain_files(n: int) -> dict[str, str]:
    files = {}
    for i in range(1, n + 1):
        fm: dict[str, Any] = {"blocked_by": [f"FEAT-{i - 1:04d}"]} if i > 1 else {}
        files[f"features/P2-FEAT-{i:04d}-x.md"] = ready(fm)
    return files


def test_blocker_index_is_one_linear_pass_over_the_graph(tmp_path: Path) -> None:
    small = memory_state(tmp_path / "s", _chain_files(200))
    large = memory_state(tmp_path / "l", _chain_files(2000))
    a, b = OpCounter(), OpCounter()
    build_blocker_index(small, a)
    build_blocker_index(large, b)
    assert 0 < a.operations
    assert b.operations / a.operations < 12  # linear (10x input), not quadratic


def test_assessment_builds_the_index_once_and_reuses_shared_contexts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import little_loops.next_arena.blockers as blockers_module

    calls: list[int] = []
    real = blockers_module.build_blocker_index

    def counting(state: Any, counter: Any = None) -> Any:
        calls.append(1)
        return real(state, counter)

    monkeypatch.setattr(blockers_module, "build_blocker_index", counting)
    state = project(tmp_path, {feat(1): ready(), feat(2): ready({"blocked_by": ["FEAT-001"]})})
    settings: ArenaSettings = state.config.next.resolve_arena_settings()
    assess_resolve_blockers(state, settings=settings)
    assert calls == [1]
